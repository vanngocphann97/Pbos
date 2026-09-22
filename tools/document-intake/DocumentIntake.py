# -*- coding: utf-8 -*-
"""Portable, offline document intake. No QR processing."""
from pathlib import Path
import csv, datetime as dt, getpass, hashlib, json, os, queue, re, shutil, subprocess, sys, threading, time, unicodedata, uuid
import tkinter as tk
from tkinter import ttk, messagebox
import pymupdf as fitz
from PIL import Image, ImageTk

APP_VERSION = '1.2.0 (2026-09-22)'
COPYRIGHT = 'Bản quyền © 2026 Phan Văn Ngọc'
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR))
ROOT = APP_DIR
STATES = {'INBOX': '01_INBOX', 'REVIEW': '03_REVIEW', 'COMPLETED': '04_COMPLETED', 'ERROR': '05_ERROR'}

def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', (s or '').replace('đ','d').replace('Đ','D')) if unicodedata.category(c) != 'Mn')

def token(s):
    return re.sub(r'[^A-Z0-9]+', '-', fold(s).upper()).strip('-')

def valid_date(s):
    try:
        return len(s) == 8 and s.isdigit() and dt.datetime.strptime(s, '%Y%m%d').strftime('%Y%m%d') == s
    except ValueError:
        return False

def extract_date(text):
    # Only issue-date / signing-date lines; never substitute an event or citation date.
    lines = fold(text).lower().splitlines()
    candidates = [s for i,s in enumerate(lines) if (re.search(r'(?:ngay\s*[:：]|hom nay|tp[., ]|ha noi|ho chi minh|hcm)', s)
                  or (i<15 and re.search(r'ngay\s*\d+\s*thang',s)))
                  and 'ngay' in s and not re.search(r'(can cu|quyet dinh so|thoi gian|thoi han|ky thanh toan|den ngay|thanh toan:)',s)]
    for line in candidates:
        for pat in [r'ngay\s*[:：]?\s*(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*((?:19|20)\d{2})',
                    r'\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*((?:19|20)\d{2})\b']:
            for m in re.finditer(pat, line):
                d, month, year = map(int, m.groups())
                result = f'{year:04d}{month:02d}{d:02d}'
                if valid_date(result):
                    return result
    return ''

def extract_number(text):
    a = fold(text)
    for line in a.splitlines():
        m = re.search(r'\b[Ss][oO0]\s*[:：.]?\s*([0-9][A-Za-z0-9./_ -]*)', line)
        if m:
            value = re.split(r'\s{2,}|\s+(?:ngay|v/v|ve)\b', m.group(1), flags=re.I)[0].strip()
            value = re.sub(r'\s*([/.-])\s*', r'\1', value)
            value = value.split(' ')[0].strip('.-_/')
            if value:
                return value
    return ''

DEFAULT_TYPES = [('BIEN-BAN-THANH-LY','BBTL'), ('DE-NGHI-THANH-TOAN','DNTT'), ('PHIEU-DE-XUAT','PDX'),
         ('TO-TRINH','TTR'), ('QUYET-DINH','QD'), ('CONG-VAN','CV'), ('THONG-BAO','TB'),
         ('THU-THONG-BAO','TB'), ('PHU-LUC','PL'), ('BIEN-BAN','BB'), ('HOP-DONG','HD'), ('HOA-DON','HDON')]

def load_types():
    # Optional override so new document types can be added without rebuilding the EXE.
    # Format: one "Tên loại|MÃ" per line in types.txt beside the executable; '#' comments allowed.
    custom = ROOT/'types.txt'
    if custom.is_file():
        try:
            rows = []
            for raw in custom.read_text('utf-8-sig').splitlines():
                line = raw.strip()
                if not line or line.startswith('#') or '|' not in line:
                    continue
                title, short = line.split('|', 1)
                title, short = token(title.strip()), token(short.strip())
                if title and short:
                    rows.append((title, short))
            if rows:
                return rows
        except OSError:
            pass
    return DEFAULT_TYPES

TYPES = load_types()

def extract_type(text, number):
    # Prefer title on first page, before references in document body.
    for line in text.splitlines()[:35]:
        a = token(line)
        for title, short in TYPES:
            if a == title or (a.startswith(title+'-') and len(a) < 100):
                return short
    n = token(number)
    for short in sorted({short for _, short in TYPES}, key=len, reverse=True):
        if re.search(r'(^|-)'+re.escape(short)+r'(-|$)', n):
            return short
    return 'HS'

PROVIDERS = [('vien thong fpt', 'FPT'), ('viettel', 'Viettel'), ('vnpt', 'VNPT'), (r'\bcmc\b', 'CMC')]

def extract_summary(text, kind):
    lines = [re.sub(r'\s+', ' ', s).strip() for s in text.splitlines() if s.strip()]
    if kind=='TB':
        # Recurring utility notice template (Thư thông báo thanh toán tiền điện/nước):
        # the checkbox on the V/v line OCRs unreliably, so the utility is identified from
        # an accounting line item that only appears in the invoice body for that utility,
        # not from the checkbox glyph itself. Verified against real electricity-notice OCR
        # output; the water pattern is analogous but not yet confirmed on a real sample —
        # recheck once a water notice comes through and adjust the keywords if it misses.
        folded = fold(text).lower()
        if 'dien nang tac dung' in folded:
            return 'Thanh toán tiền điện'
        if re.search(r'\b(?:so|chi so|khoi luong)\s*nuoc\b|nuoc sinh hoat|nuoc thai', folded):
            return 'Thanh toán tiền nước'
    for line in lines[:40]:
        m=re.search(r'(?i)\b(?:TT|thanh toán)\s+cước\s+(.+)',line)
        if m:
            subject=re.split(r'\s+(?:H[ĐD]|hợp đồng)\b',m.group(1),flags=re.I)[0]
            payee=''
            for pat,label in PROVIDERS:
                if re.search(pat,fold(text),re.I):
                    payee=' '+label;break
            return 'Thanh toán cước '+subject.strip()+payee
    for i, line in enumerate(lines[:50]):
        if re.match(r'^[\s\W]*(?:v\s*[/i]\s*[vw]\b|ve viec\b|ve:)', fold(line), re.I):
            out = [re.sub(r'^[\s\W]*(?:v\s*[/i]\s*[vw]\s*[:.]?|về việc\s*:?|về:)\s*', '', line, flags=re.I)]
            for nxt in lines[i+1:i+3]:
                if re.match(r'^(kinh g|can cu|so:|dieu |cong |doc lap|ky thanh toan)', fold(nxt), re.I):
                    break
                if len(' '.join(out)) < 60:
                    out.append(nxt)
            return ' '.join(out).strip(' :.-')[:150]
    for i,line in enumerate(lines[:60]):
        m=re.match(r'^(?:muc dich su dung|noi dung thanh toan|noi dung de xuat)\s*[:：]?\s*(.*)',fold(line),re.I)
        if m:
            # Preserve original Vietnamese spelling after field label.
            suffix=line[m.start(1):].strip()
            if len(suffix)>10:return suffix[:150]
            for nxt in lines[i+1:i+4]:
                if len(nxt)>15 and not re.match(r'^(nguoi|so tien|chung tu|hinh thuc)',fold(nxt),re.I):return nxt[:150]
    for i, line in enumerate(lines[:35]):
        if any(token(line).startswith(title) for title, short in TYPES if short == kind):
            following = lines[i+1:i+4]
            useful = [s for s in following if not re.match(r'^(so\b|kinh gui|can cu|cong hoa|doc lap|hom nay|bo phan|khoan muc|tai khoan)', fold(s), re.I)]
            if useful:
                return useful[0][:150]
    if kind=='BBTL':
        for i,line in enumerate(lines[:30]):
            m=re.search(r'\bvề\s+(.+)',line,re.I)
            if m:return 'Thanh lý: '+m.group(1).strip()[:120]
    return ''

def metadata(text):
    n = extract_number(text)
    t = extract_type(text, n)
    return {'date': extract_date(text), 'number': n, 'type': t, 'summary': extract_summary(text, t)}

def proposed(m):
    return f"{m.get('date') or '00000000'}_{token(m.get('number'))[:45] or 'KSO'}_{token(m.get('type'))[:15] or 'HS'}_{token(m.get('summary'))[:95] or 'HO-SO'}.pdf"

def validate(m):
    if not valid_date(m.get('date', '')):
        raise ValueError('Ngày văn bản phải là ngày hợp lệ, theo YYYYMMDD.')
    if not token(m.get('number')):
        raise ValueError('Nhập Số/ký hiệu; dùng KSO nếu văn bản thực sự không có số.')
    if not token(m.get('type')) or not token(m.get('summary')):
        raise ValueError('Cần nhập Loại hồ sơ và Nội dung vắn tắt.')

class Engine:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        for folder in [*STATES.values(), 'logs', 'data']:
            (self.root/folder).mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            self.exe = BUNDLE_DIR/'runtime'/'tesseract.exe'
            self.tessdata = BUNDLE_DIR/'runtime'/'tessdata'
        else:
            found = shutil.which('tesseract')
            self.exe = Path(found) if found else BUNDLE_DIR/'runtime'/'tesseract'
            candidates = [
                Path(os.environ.get('TESSDATA_PREFIX','')) if os.environ.get('TESSDATA_PREFIX') else None,
                Path('/usr/share/tesseract-ocr/5/tessdata'),
                BUNDLE_DIR/'runtime'/'tessdata'
            ]
            self.tessdata = next((x for x in candidates if x and x.is_dir()), BUNDLE_DIR/'runtime'/'tessdata')
        os.environ['TESSDATA_PREFIX'] = str(self.tessdata)
        os.environ['OMP_THREAD_LIMIT'] = '2'
        try:
            self.user = getpass.getuser()
        except Exception:
            self.user = 'unknown'

    def check_runtime(self):
        for p in [self.exe, self.tessdata/'vie.traineddata', self.tessdata/'eng.traineddata']:
            if not p.is_file():
                raise RuntimeError('Thiếu thành phần đi kèm: '+str(p)+'. Hãy giải nén lại toàn bộ ZIP.')
        result = subprocess.run([str(self.exe), '--tessdata-dir', str(self.tessdata), '--list-langs'], cwd=self.exe.parent,
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not {'eng','vie'}.issubset(set(result.stdout.split())):
            raise RuntimeError('OCR runtime không hoạt động: '+result.stderr)
        return result.stdout

    def ocr_image(self,image,psm):
        # MinGW Tesseract uses narrow paths: use ASCII relative paths within its cwd.
        # Windows/Python still open the Unicode executable and cwd via wide APIs.
        png=self.exe.parent/('ocr-'+uuid.uuid4().hex+'.png')
        try:
            image.save(png)
            result=subprocess.run([str(self.exe),str(png.relative_to(self.exe.parent)),'stdout',
                                   '--tessdata-dir',str(self.tessdata),'-l','vie+eng','--oem','1','--psm',str(psm)],
                                  cwd=self.exe.parent,capture_output=True,timeout=180,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace'))
            return result.stdout.decode('utf-8',errors='replace')
        finally:png.unlink(missing_ok=True)

    def scan(self, state):
        return sorted((self.root/STATES[state]).glob('*.pdf'), key=lambda p: p.name.lower())

    def key(self, p):
        return hashlib.sha256(str(p.relative_to(self.root)).encode('utf-8')).hexdigest()

    def load(self, p):
        f = self.root/'data'/(self.key(p)+'.json')
        if f.exists():
            try:
                d = json.loads(f.read_text('utf-8'))
                stat = p.stat()
                if d.get('size') == stat.st_size and d.get('mtime') == stat.st_mtime_ns:
                    return d
            except (ValueError, OSError):
                pass
        return {'date':'', 'number':'', 'type':'', 'summary':'', 'text':'', 'status':'Chưa OCR'}

    def save(self, p, data):
        d = dict(data)
        stat = p.stat()
        d.update(size=stat.st_size, mtime=stat.st_mtime_ns)
        f = self.root/'data'/(self.key(p)+'.json')
        tmp = f.with_suffix('.tmp')
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), 'utf-8')
        tmp.replace(f)

    def log(self, action, source='', target='', detail=''):
        p = self.root/'logs'/'document_intake.csv'
        exists = p.exists()
        with p.open('a', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(['TIME','USER','ACTION','SOURCE','TARGET','DETAIL'])
            w.writerow([dt.datetime.now().isoformat(timespec='seconds'), self.user, action, str(source), str(target), detail])

    def analyze(self, p, progress=None, force=False):
        old = self.load(p)
        if old.get('analyzed') and not force:
            return old
        out=[];header=''
        # Opening from bytes ensures invalid PDFs cannot retain a Windows file lock.
        with fitz.open(stream=p.read_bytes(), filetype='pdf') as doc:
            if doc.needs_pass:
                raise ValueError('PDF được mã hóa bằng mật khẩu.')
            if not len(doc):
                raise ValueError('PDF không có trang.')
            for i, page in enumerate(doc):
                if progress:
                    progress(f'{p.name} • trang {i+1}/{len(doc)}')
                text=page.get_text().strip()
                if len(text)<120 or force:
                    scale=min(2.5, 3500/max(page.rect.width, page.rect.height))
                    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale), colorspace=fitz.csRGB, alpha=False)
                    image=Image.frombytes('RGB', [pix.width,pix.height], pix.samples)
                    text=self.ocr_image(image,3)
                    if i==0:
                        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=fitz.Rect(0,0,page.rect.width,page.rect.height*.4),colorspace=fitz.csRGB,alpha=False)
                        image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
                        header=self.ocr_image(image,6)
                out.append(text)
        text='\n\n'.join(out)
        if len(text.strip()) < 10:
            raise ValueError('Không nhận diện được chữ trong PDF; cần kiểm tra chất lượng scan.')
        d=metadata(out[0])
        if header:
            d['date']=extract_date(header) or d['date']
            if not d['summary'] or d['type']=='PDX':
                d['summary']=extract_summary(header,d['type']) or d['summary']
            text+='\n\n--- OCR BỔ SUNG VÙNG ĐẦU TRANG ---\n'+header
        d.update(text=text, analyzed=True, pages=len(out), status='Cần duyệt')
        missing=[label for key,label in [('date','ngày'),('number','số'),('summary','nội dung')] if not d[key]]
        if missing:d['status']='Bổ sung '+', '.join(missing)
        self.save(p,d)
        self.log('OCR',p,detail=f'{len(out)} trang')
        return d

    def move(self, p, state, data=None, name=None):
        dest=self.root/STATES[state]/(name or p.name)
        if dest == p:
            if data: self.save(p,data)
            return p
        stem=dest.stem
        # Windows rename refuses existing files, including a concurrent collision.
        index=1
        while True:
            try:
                p.rename(dest)
                break
            except FileExistsError:
                index+=1
                dest=dest.with_name(f'{stem}_{index:02d}.pdf')
        self.log(state,p,dest, 'Trùng tên: thêm hậu tố' if index>1 else '')
        if data is not None:
            self.save(dest,data)
        old=self.root/'data'/(self.key(p)+'.json')
        old.unlink(missing_ok=True)
        return dest

    def approve(self,p,d):
        validate(d)
        with fitz.open(stream=p.read_bytes(),filetype='pdf') as doc:
            if doc.needs_pass or len(doc)==0:raise ValueError('PDF không thể mở để duyệt.')
        d=dict(d,status='Đã duyệt')
        return self.move(p,'COMPLETED',d,proposed(d))

class App(tk.Tk):
    def __init__(self,engine=None):
        super().__init__()
        self.engine=engine or Engine()
        self.title(f'Document Intake • Portable • {APP_VERSION}')
        self.geometry('1260x800'); self.minsize(1000,650)
        self.busy=False; self.current=None; self.rows={}; self.events=queue.Queue();self.entries=[];self.page_index=0
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.vars={k:tk.StringVar() for k in ['date','number','type','summary']}
        self.state=tk.StringVar(value='INBOX'); self.status=tk.StringVar(value='Sẵn sàng')
        ttk.Style(self).theme_use('clam')
        head=ttk.Frame(self,padding=12); head.pack(fill='x')
        ttk.Label(head,text='DOCUMENT INTAKE',font=('Segoe UI',20,'bold')).pack(side='left')
        ttk.Label(head,text=f'OCR tiếng Việt + English • Hoạt động ngoại tuyến • {APP_VERSION}').pack(side='left',padx=20)
        self.controls=[]
        def button(parent,text,fn):
            b=ttk.Button(parent,text=text,command=fn); b.pack(side='left',padx=3); self.controls.append(b); return b
        bar=ttk.Frame(self,padding=(12,0,12,10));bar.pack(fill='x')
        self.combo=ttk.Combobox(bar,textvariable=self.state,values=list(STATES),state='readonly',width=15)
        self.combo.pack(side='left',padx=3);self.combo.bind('<<ComboboxSelected>>',lambda e:self.scan())
        button(bar,'Quét thư mục',self.scan)
        button(bar,'OCR hàng loạt',self.ocr_all)
        button(bar,'OCR lại hồ sơ',self.reocr_current)
        button(bar,'Mở thư mục',lambda:os.startfile(self.engine.root/STATES[self.state.get()]))
        pan=ttk.Panedwindow(self,orient='horizontal');pan.pack(fill='both',expand=True,padx=12)
        left=ttk.Frame(pan); right=ttk.Frame(pan,padding=(12,0)); pan.add(left,weight=3);pan.add(right,weight=2)
        self.tree=ttk.Treeview(left,columns=('file','name','status'),show='headings',selectmode='browse')
        for key,title,width in [('file','PDF gốc',180),('name','Tên đề xuất',340),('status','Trạng thái',110)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width)
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.pick)
        scroll=ttk.Scrollbar(left,orient='horizontal',command=self.tree.xview);scroll.pack(fill='x');self.tree.configure(xscrollcommand=scroll.set)
        form=ttk.LabelFrame(right,text='Kiểm tra và chỉnh sửa metadata',padding=10);form.pack(fill='x')
        for i,(key,label) in enumerate([('date','Ngày (YYYYMMDD)'),('number','Số / ký hiệu'),('type','Loại hồ sơ'),('summary','Nội dung vắn tắt')]):
            ttk.Label(form,text=label).grid(row=i,column=0,sticky='w',pady=5)
            e=ttk.Entry(form,textvariable=self.vars[key],width=38);e.grid(row=i,column=1,sticky='ew',padx=8)
            self.entries.append(e)
            self.vars[key].trace_add('write',lambda *args:self.preview())
        form.columnconfigure(1,weight=1)
        self.new=tk.StringVar();ttk.Label(form,textvariable=self.new,wraplength=440,foreground='#145983').grid(row=5,column=0,columnspan=2,sticky='w',pady=12)
        b=ttk.Frame(right);b.pack(fill='x',pady=10)
        button(b,'Lưu metadata',self.save_current);button(b,'Duyệt & đổi tên',self.approve)
        b2=ttk.Frame(right);b2.pack(fill='x',pady=(0,10))
        button(b2,'→ REVIEW',lambda:self.transfer('REVIEW'));button(b2,'→ ERROR',lambda:self.transfer('ERROR'));button(b2,'→ INBOX',lambda:self.transfer('INBOX'))
        button(b2,'Mở PDF',self.open_pdf)
        ttk.Label(right,text='Loại: HD, BBTL, DNTT, TTR, QD, CV, TB… • Không có số: KSO',wraplength=450).pack(fill='x')
        self.tabs=ttk.Notebook(right);self.tabs.pack(fill='both',expand=True,pady=8)
        box=ttk.Frame(self.tabs);pdfbox=ttk.Frame(self.tabs);self.tabs.add(box,text='Văn bản OCR');self.tabs.add(pdfbox,text='Xem PDF gốc')
        self.text=tk.Text(box,wrap='word',font=('Segoe UI',10));self.text.pack(fill='both',expand=True)
        pdfbar=ttk.Frame(pdfbox);pdfbar.pack(fill='x');self.page_label=tk.StringVar()
        button(pdfbar,'◀',lambda:self.change_page(-1));button(pdfbar,'▶',lambda:self.change_page(1))
        ttk.Label(pdfbar,textvariable=self.page_label).pack(side='left',padx=12)
        self.canvas=tk.Canvas(pdfbox,bg='#e5e7eb',highlightthickness=0)
        yscroll=ttk.Scrollbar(pdfbox,orient='vertical',command=self.canvas.yview);yscroll.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=yscroll.set);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units'))
        self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.render_pdf())
        ttk.Label(self,textvariable=self.status,padding=10).pack(fill='x')
        ttk.Label(self,text=COPYRIGHT,padding=(10,0,10,6),foreground='#6b7280').pack(fill='x')
        self.scan();self.after(100,self.poll)

    def values(self): return {k:v.get().strip() for k,v in self.vars.items()}
    def preview(self):
        if hasattr(self,'new'): self.new.set(proposed(self.values()))
    def clear(self):
        self.current=None
        for v in self.vars.values():v.set('')
        self.text.delete('1.0','end')
        self.canvas.delete('all');self.page_label.set('');self.page_index=0
    def persist(self):
        if self.current and self.current.exists() and not self.busy:
            d=self.engine.load(self.current);d.update(self.values());self.engine.save(self.current,d)
    def scan(self):
        if self.busy:return
        self.persist();self.clear()
        self.tree.delete(*self.tree.get_children());self.rows={}
        for p in self.engine.scan(self.state.get()):
            d=self.engine.load(p)
            iid=self.tree.insert('','end',values=(p.name,proposed(d) if d.get('analyzed') or d.get('date') else '',d['status']))
            self.rows[iid]=p
        self.status.set(f'{len(self.rows)} PDF • {STATES[self.state.get()]} • Đặt PDF mới vào 01_INBOX rồi Quét thư mục')
    def pick(self,event=None):
        if self.busy:return
        sel=self.tree.selection()
        if not sel:return
        p=self.rows[sel[0]]
        if p==self.current:return
        self.persist();self.current=p;d=self.engine.load(p)
        for k,v in self.vars.items():v.set(d.get(k,''))
        self.text.delete('1.0','end');self.text.insert('1.0',('LỖI OCR: '+d['error']+'\n\n' if d.get('error') else '')+d.get('text',''))
        self.page_index=0;self.render_pdf()
    def save_current(self):
        if not self.current:return
        self.persist();self.engine.log('METADATA',self.current);self.status.set('Đã lưu metadata.');self.refresh_row()
    def refresh_row(self):
        for iid,p in self.rows.items():
            if p==self.current:
                d=self.engine.load(p);self.tree.item(iid,values=(p.name,proposed(d),d['status']))
    def set_busy(self,flag):
        self.busy=flag
        for b in self.controls:b.configure(state='disabled' if flag else 'normal')
        for e in self.entries:e.configure(state='disabled' if flag else 'normal')
        self.combo.configure(state='disabled' if flag else 'readonly')
    def reocr_current(self):
        if not self.current or self.busy:return
        if not messagebox.askyesno('OCR lại hồ sơ',
                'OCR lại sẽ đọc lại ảnh trang và thay thế toàn bộ Ngày, Số/ký hiệu, Loại hồ sơ, '
                'Nội dung vắn tắt bằng đề xuất mới — kể cả phần bạn đã sửa tay trước đó.\n\n'
                'Bạn có chắc chắn muốn tiếp tục?',parent=self):return
        self.ocr_all(single=True,force=True)
    def ocr_all(self,single=False,force=False):
        if self.busy:return
        self.persist()
        paths=[self.current] if single and self.current else ([] if single else list(self.rows.values()))
        if not paths:return
        self.set_busy(True)
        def run():
            good=bad=0
            try:
                self.engine.check_runtime()
                for p in paths:
                    try:
                        self.engine.analyze(p,lambda s:self.events.put(('progress',s)),force=force);good+=1
                    except Exception as exc:
                        bad+=1;d=self.engine.load(p);d.update(status='Lỗi OCR',error=str(exc),analyzed=False)
                        self.engine.log('OCR_ERROR',p,detail=str(exc))
                        try:self.engine.move(p,'ERROR',d)
                        except Exception as move_error:self.engine.log('MOVE_ERROR',p,detail=str(move_error))
                self.events.put(('done',f'OCR xong: {good} thành công, {bad} lỗi. Hồ sơ lỗi ở 05_ERROR.'))
            except Exception as exc:self.events.put(('done',str(exc)))
        threading.Thread(target=run,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='done':
                    self.current=None;self.set_busy(False);self.scan()
                self.status.set(value)
        except queue.Empty:pass
        self.after(100,self.poll)
    def approve(self):
        if not self.current or self.busy:return
        try:
            d=self.engine.load(self.current);d.update(self.values());validate(d)
            if not messagebox.askyesno('Duyệt hồ sơ',f'Chuyển vào 04_COMPLETED với tên:\n\n{proposed(d)}\n\nNếu trùng tên sẽ tự thêm _02, _03…',parent=self):return
            dst=self.engine.approve(self.current,d);self.current=None;self.scan();self.status.set('Đã hoàn tất: '+dst.name)
        except Exception as exc:messagebox.showerror('Không thể duyệt',str(exc),parent=self)
    def transfer(self,state):
        if not self.current or self.busy:return
        try:
            d=self.engine.load(self.current);d.update(self.values());self.engine.move(self.current,state,d)
            self.current=None;self.scan();self.status.set('Đã chuyển sang '+state)
        except Exception as exc:messagebox.showerror('Không thể chuyển',str(exc),parent=self)
    def open_pdf(self):
        if self.current:self.tabs.select(1);self.render_pdf()
    def change_page(self,delta):
        self.page_index=max(0,self.page_index+delta);self.render_pdf()
    def render_pdf(self):
        if not self.current or self.tabs.index('current')!=1:return
        self.canvas.delete('all')
        try:
            with fitz.open(stream=self.current.read_bytes(),filetype='pdf') as doc:
                self.page_index=min(self.page_index,len(doc)-1)
                page=doc[self.page_index]
                width=max(420,self.canvas.winfo_width()-22)
                pix=page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),colorspace=fitz.csRGB,alpha=False)
                self.photo=ImageTk.PhotoImage(Image.frombytes('RGB',[pix.width,pix.height],pix.samples))
                self.canvas.delete('all');self.canvas.create_image(0,0,anchor='nw',image=self.photo)
                self.canvas.configure(scrollregion=(0,0,pix.width,pix.height));self.canvas.yview_moveto(0)
                self.page_label.set(f'Trang {self.page_index+1}/{len(doc)}')
        except Exception as exc:self.page_label.set('Không mở được PDF: '+str(exc)[:65])
    def close(self):
        if self.busy:
            messagebox.showinfo('OCR đang chạy','Vui lòng đợi OCR hoàn tất trước khi đóng ứng dụng.',parent=self);return
        self.persist();self.destroy()

def self_test_core():
    """Headless acceptance test embedded in the single source file."""
    import tempfile, traceback
    report={'app_version':APP_VERSION,'checks':[],'passed':False}
    def check(name, condition, detail=''):
        ok=bool(condition); report['checks'].append({'name':name,'passed':ok,'detail':detail})
        if not ok: raise AssertionError(name + (': '+detail if detail else ''))
    try:
        check('valid_date', valid_date('20240229') and not valid_date('20260230') and not valid_date('20261301'))
        m=metadata('CÔNG VĂN\nSố: 123/UBND-VP\nTP. Hồ Chí Minh, ngày 16 tháng 9 năm 2026\nV/v: Triển khai hệ thống\nKính gửi: Các đơn vị')
        check('metadata Vietnamese',m=={'date':'20260916','number':'123/UBND-VP','type':'CV','summary':'Triển khai hệ thống'},str(m))
        check('proposed filename',proposed(m)=='20260916_123-UBND-VP_CV_TRIEN-KHAI-HE-THONG.pdf',proposed(m))
        try: validate({'date':'20260230','number':'1','type':'CV','summary':'x'}); bad=False
        except ValueError: bad=True
        check('invalid date rejected',bad)
        with tempfile.TemporaryDirectory(prefix='document-intake-test-') as td:
            root=Path(td); engine=Engine(root)
            langs=set(engine.check_runtime().split())
            check('OCR languages',{'eng','vie'}.issubset(langs),','.join(sorted(langs)))
            # Create a one-page image-only PDF to force OCR.
            img=Image.new('RGB',(1800,1200),'white')
            from PIL import ImageDraw, ImageFont
            draw=ImageDraw.Draw(img)
            font=None
            for candidate in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf']:
                if Path(candidate).is_file():
                    try: font=ImageFont.truetype(candidate,54); break
                    except Exception: pass
            if font is None: font=ImageFont.load_default()
            lines=['CONG VAN','So: 123/UBND-VP','TP. Ho Chi Minh, ngay 16 thang 9 nam 2026','V/v: Trien khai he thong']
            y=100
            for line in lines:
                draw.text((100,y),line,fill='black',font=font); y+=120
            inbox=root/STATES['INBOX']; pdf=inbox/'sample.pdf'
            doc=fitz.open(); page=doc.new_page(width=595,height=842)
            import io
            b=io.BytesIO(); img.save(b,format='PNG')
            page.insert_image(page.rect,stream=b.getvalue()); doc.save(pdf); doc.close()
            d=engine.analyze(pdf)
            check('OCR analyzed PDF',d.get('analyzed') and len(d.get('text',''))>30,d.get('text','')[:120])
            check('OCR extracted number',token(d.get('number'))=='123-UBND-VP',str(d))
            edited={'date':'20260916','number':'123/UBND-VP','type':'CV','summary':'Kiểm thử hồ sơ'}
            out=engine.approve(pdf,edited)
            check('approval output exists',out.is_file(),str(out))
            check('approval filename',out.name=='20260916_123-UBND-VP_CV_KIEM-THU-HO-SO.pdf',out.name)
            check('audit log',(root/'logs'/'document_intake.csv').is_file())
        report['passed']=True
    except Exception:
        report['error']=traceback.format_exc()
    target=APP_DIR/'SELF_TEST_RESULT.json'
    try: target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    except Exception: pass
    return report

def main():
    try:
        if '--self-test' in sys.argv:
            report=self_test_core()
            print(json.dumps(report,ensure_ascii=False,indent=2))
            raise SystemExit(0 if report.get('passed') else 1)
        engine=Engine();engine.check_runtime();App(engine).mainloop()
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:(APP_DIR/'startup_error.txt').write_text(traceback.format_exc(),'utf-8')
        except Exception:pass
        if '--self-test' not in sys.argv:
            try:messagebox.showerror('Document Intake','Không thể khởi động. Xem startup_error.txt trong thư mục ứng dụng.')
            except Exception:pass
        sys.exit(1)

if __name__=='__main__':main()