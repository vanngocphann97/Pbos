# -*- coding: utf-8 -*-
"""Portable, offline document intake. No QR processing."""
from pathlib import Path
import csv, datetime as dt, getpass, hashlib, json, os, queue, re, shutil, subprocess, sys, threading, time, unicodedata, uuid
import tkinter as tk
from tkinter import ttk, messagebox
import pymupdf as fitz
from PIL import Image, ImageTk

APP_VERSION = '2.3.0 Agent #01 (2026-09-23)'
AUTO_THRESHOLD = 90
WATCH_INTERVAL_MS = 2500
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

def confidence(m):
    """Conservative confidence score: auto-complete only when core metadata is strong."""
    score=0; reasons=[]
    if valid_date(m.get('date','')): score+=30
    else: reasons.append('thiếu/ngày không hợp lệ')
    n=token(m.get('number',''))
    if n and n!='KSO': score+=25
    elif n=='KSO': score+=12; reasons.append('không có số')
    else: reasons.append('thiếu số')
    t=token(m.get('type',''))
    known={short for _,short in TYPES}|{'HS'}
    if t and t in known and t!='HS': score+=20
    elif t: score+=8; reasons.append('loại hồ sơ chưa chắc chắn')
    else: reasons.append('thiếu loại')
    summary=(m.get('summary') or '').strip()
    if len(summary)>=12: score+=25
    elif len(summary)>=5: score+=12; reasons.append('nội dung quá ngắn')
    else: reasons.append('thiếu nội dung')
    return min(score,100), reasons

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
        os.environ['OMP_THREAD_LIMIT'] = '1'
        self.runtime_checked=False
        try:
            self.user = getpass.getuser()
        except Exception:
            self.user = 'unknown'

    def check_runtime(self):
        if self.runtime_checked: return 'eng vie'
        for p in [self.exe, self.tessdata/'vie.traineddata', self.tessdata/'eng.traineddata']:
            if not p.is_file():
                raise RuntimeError('Thiếu thành phần đi kèm: '+str(p)+'. Hãy giải nén lại toàn bộ ZIP.')
        result = subprocess.run([str(self.exe), '--tessdata-dir', str(self.tessdata), '--list-langs'], cwd=self.exe.parent,
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not {'eng','vie'}.issubset(set(result.stdout.split())):
            raise RuntimeError('OCR runtime không hoạt động: '+result.stderr)
        self.runtime_checked=True
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

    def file_hash(self,p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        return h.hexdigest()

    def duplicate_of(self,p):
        digest=self.file_hash(p)
        index=self.root/'data'/'hash_index.json'
        try: db=json.loads(index.read_text('utf-8')) if index.exists() else {}
        except Exception: db={}
        old=db.get(digest)
        return digest, old

    def register_hash(self,p,digest=None):
        digest=digest or self.file_hash(p); index=self.root/'data'/'hash_index.json'
        try: db=json.loads(index.read_text('utf-8')) if index.exists() else {}
        except Exception: db={}
        db[digest]=str(p.relative_to(self.root)); tmp=index.with_suffix('.tmp')
        tmp.write_text(json.dumps(db,ensure_ascii=False,indent=2),'utf-8'); tmp.replace(index)

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
        old=self.load(p)
        if old.get('analyzed') and not force:return old
        out=[]; first_ocr=''
        with fitz.open(stream=p.read_bytes(),filetype='pdf') as doc:
            if doc.needs_pass:raise ValueError('PDF được mã hóa bằng mật khẩu.')
            if not len(doc):raise ValueError('PDF không có trang.')
            total=len(doc)
            for i,page in enumerate(doc):
                if progress:progress(f'{p.name} • đọc trang {i+1}/{total}')
                native=page.get_text('text').strip()
                # Fast path: PDF có text layer thì không OCR.
                if len(native)>=80 and not force:
                    text=native
                else:
                    # 1.65x đủ cho hồ sơ A4 phổ biến, nhanh hơn đáng kể so với 2.5x.
                    scale=min(1.65,2200/max(page.rect.width,page.rect.height))
                    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False)
                    image=Image.frombytes('L',[pix.width,pix.height],pix.samples)
                    text=self.ocr_image(image,6 if i==0 else 3)
                    if i==0:first_ocr=text
                out.append(text)
                # Metadata cần chủ yếu ở trang đầu. Không OCR lại header lần hai.
                if i==0:
                    probe=metadata(text)
                    if probe.get('date') and probe.get('number') and probe.get('summary') and not force:
                        # Các trang sau có text layer vẫn lấy text; trang scan sau không OCR nếu không cần metadata.
                        pass
        text='\n\n'.join(out)
        if len(text.strip())<10:raise ValueError('Không nhận diện được chữ trong PDF; cần kiểm tra chất lượng scan.')
        # Ưu tiên trang đầu, sau đó bổ sung từ 3 trang đầu nếu thiếu.
        head='\n'.join(out[:3])
        d=metadata(out[0])
        if not d.get('date'):d['date']=extract_date(head)
        if not d.get('number'):d['number']=extract_number(head)
        if not d.get('summary'):d['summary']=extract_summary(head,d.get('type','HS'))
        score,reasons=confidence(d)
        missing=[label for key,label in [('date','ngày'),('number','số/ký hiệu'),('summary','nội dung')] if not d.get(key)]
        status='Đủ điều kiện tự động' if score>=AUTO_THRESHOLD and not missing else ('Thiếu '+', '.join(missing) if missing else 'Cần kiểm tra')
        d.update(text=text,analyzed=True,pages=len(out),confidence=score,confidence_reasons=reasons,status=status)
        self.save(p,d);self.log('OCR',p,detail=f'{len(out)} trang; confidence={score}')
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

    def auto_process(self,p,progress=None):
        digest,old=self.duplicate_of(p)
        if old:
            d=self.load(p); d.update(status='Trùng lặp',duplicate_of=old,file_hash=digest)
            self.log('DUPLICATE',p,detail=old); return self.move(p,'REVIEW',d)
        d=self.analyze(p,progress)
        score=d.get('confidence',0)
        if score>=AUTO_THRESHOLD:
            try:
                out=self.approve(p,d,auto=True); self.register_hash(out,digest); return out
            except ValueError:
                pass
        d=dict(d,status='Cần duyệt',file_hash=digest)
        self.save(p,d); return self.move(p,'REVIEW',d)

    def approve(self,p,d,auto=False):
        validate(d)
        with fitz.open(stream=p.read_bytes(),filetype='pdf') as doc:
            if doc.needs_pass or len(doc)==0:raise ValueError('PDF không thể mở để duyệt.')
        d=dict(d,status='Tự động hoàn tất' if auto else 'Đã duyệt',approved_by='AUTO' if auto else self.user)
        out=self.move(p,'COMPLETED',d,proposed(d))
        self.log('AUTO_APPROVE' if auto else 'APPROVE',p,out,f"confidence={d.get('confidence','')}")
        return out

class App(tk.Tk):
    BG='#f5f7fb'; CARD='#ffffff'; BLUE='#1769e0'; TEXT='#172033'; MUTED='#667085'; GREEN='#159455'; ORANGE='#d97706'; RED='#d92d20'
    def __init__(self,engine=None):
        super().__init__(); self.engine=engine or Engine()
        self.title('Document Intake - Benthanh House'); self.state('zoomed'); self.geometry('1360x820'); self.minsize(1050,650); self.configure(bg=self.BG)
        self.busy=False; self.current=None; self.rows={}; self.events=queue.Queue(); self.entries=[]; self.page_index=0
        self.watch_enabled=tk.BooleanVar(value=True); self.pending={}; self.active_state='REVIEW'
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.vars={k:tk.StringVar() for k in ['date','number','type','summary']}
        self.status=tk.StringVar(value='Sẵn sàng • Tự động theo dõi thư mục hồ sơ mới')
        self.count_vars={k:tk.StringVar(value='0') for k in STATES}
        self._style(); self._build(); self.scan('REVIEW'); self.after(100,self.poll); self.after(WATCH_INTERVAL_MS,self.watch_tick)

    def _style(self):
        s=ttk.Style(self); s.theme_use('clam')
        s.configure('TFrame',background=self.BG); s.configure('Card.TFrame',background=self.CARD)
        s.configure('TLabel',background=self.BG,foreground=self.TEXT,font=('Segoe UI',10))
        s.configure('Card.TLabel',background=self.CARD,foreground=self.TEXT,font=('Segoe UI',10))
        s.configure('Title.TLabel',background=self.BG,foreground=self.TEXT,font=('Segoe UI',22,'bold'))
        s.configure('Sub.TLabel',background=self.BG,foreground=self.MUTED,font=('Segoe UI',10))
        s.configure('Primary.TButton',font=('Segoe UI',10,'bold'),padding=(14,9),background=self.BLUE,foreground='white')
        s.map('Primary.TButton',background=[('active','#1258bd'),('disabled','#9bbce9')])
        s.configure('TButton',font=('Segoe UI',10),padding=(11,8))
        s.configure('Treeview',font=('Segoe UI',10),rowheight=34,background='white',fieldbackground='white',borderwidth=0)
        s.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),padding=8,background='#eef2f7',foreground=self.TEXT)
        s.map('Treeview',background=[('selected','#e8f1ff')],foreground=[('selected',self.TEXT)])
        s.configure('TLabelframe',background=self.CARD); s.configure('TLabelframe.Label',background=self.CARD,font=('Segoe UI',10,'bold'))
        s.configure('TEntry',padding=7)

    def _build(self):
        top=ttk.Frame(self,padding=(22,16)); top.pack(fill='x')
        title=ttk.Frame(top); title.pack(side='left')
        ttk.Label(title,text='DOCUMENT INTAKE',style='Title.TLabel').pack(anchor='w')
        ttk.Label(title,text='Tự động nhận diện • Đổi tên • Phân luồng hồ sơ',style='Sub.TLabel').pack(anchor='w')
        right=ttk.Frame(top); right.pack(side='right')
        self.agent_label=ttk.Label(right,text='●  Tự động đang hoạt động',foreground=self.GREEN,font=('Segoe UI',10,'bold')); self.agent_label.pack(side='left',padx=12)
        ttk.Checkbutton(right,variable=self.watch_enabled,command=self._toggle_agent).pack(side='left')

        summary=ttk.Frame(self,padding=(22,0,22,12)); summary.pack(fill='x')
        cards=[('INBOX','Hồ sơ mới',self.BLUE),('REVIEW','Cần kiểm tra',self.ORANGE),('COMPLETED','Đã xử lý',self.GREEN),('ERROR','Lỗi xử lý',self.RED)]
        for key,label,color in cards:
            box=tk.Frame(summary,bg='white',highlightbackground='#e4e7ec',highlightthickness=1); box.pack(side='left',fill='x',expand=True,padx=(0,10))
            tk.Label(box,textvariable=self.count_vars[key],bg='white',fg=color,font=('Segoe UI',22,'bold')).pack(anchor='w',padx=16,pady=(12,0))
            tk.Label(box,text=label,bg='white',fg=self.TEXT,font=('Segoe UI',10,'bold')).pack(anchor='w',padx=16,pady=(0,12))

        main=ttk.Panedwindow(self,orient='horizontal'); main.pack(fill='both',expand=True,padx=22,pady=(0,10))
        left=ttk.Frame(main,style='Card.TFrame',padding=12); right=ttk.Frame(main,style='Card.TFrame',padding=14)
        main.add(left,weight=7); main.add(right,weight=4)

        nav=ttk.Frame(left,style='Card.TFrame'); nav.pack(fill='x',pady=(0,10))
        self.nav_buttons={}
        for key,label in [('INBOX','Hồ sơ mới'),('REVIEW','Cần kiểm tra'),('COMPLETED','Đã xử lý'),('ERROR','Lỗi xử lý')]:
            b=ttk.Button(nav,text=label,command=lambda k=key:self.scan(k)); b.pack(side='left',padx=(0,6)); self.nav_buttons[key]=b
        ttk.Button(nav,text='+ Thêm PDF',style='Primary.TButton',command=self.add_files).pack(side='right',padx=(6,0))
        ttk.Button(nav,text='Mở thư mục',command=self.open_active_folder).pack(side='right')

        self.tree=ttk.Treeview(left,columns=('file','name','type','date','confidence','status'),show='headings',selectmode='browse')
        cols=[('file','Tên file hiện tại',185),('name','Tên đề xuất',330),('type','Loại',70),('date','Ngày',85),('confidence','Tin cậy',75),('status','Trạng thái',110)]
        for key,label,w in cols:self.tree.heading(key,text=label);self.tree.column(key,width=w,minwidth=55)
        table=ttk.Frame(left,style='Card.TFrame');
        self.tree.pack_forget(); self.tree.pack(in_=table,side='left',fill='both',expand=True); table.pack(fill='both',expand=True)
        y=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview); y.pack(side='right',fill='y'); self.tree.configure(yscrollcommand=y.set); self.tree.bind('<<TreeviewSelect>>',self.pick)

        bottom=ttk.Frame(left,style='Card.TFrame'); bottom.pack(fill='x',pady=(10,0))
        ttk.Button(bottom,text='Xử lý lại OCR',command=self.reocr_current).pack(side='left')
        self.approve_btn=ttk.Button(bottom,text='Duyệt & hoàn tất',style='Primary.TButton',command=self.approve); self.approve_btn.pack(side='right')
        ttk.Button(bottom,text='Đưa về hồ sơ mới',command=lambda:self.transfer('INBOX')).pack(side='right',padx=6)

        ttk.Label(right,text='XEM TRƯỚC & THÔNG TIN',style='Card.TLabel',font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.preview_box=tk.Canvas(right,bg='#eef2f6',height=230,highlightthickness=0); self.preview_box.pack(fill='x',pady=(10,10))
        self.preview_box.bind('<MouseWheel>',lambda e:self.preview_box.yview_scroll(-int(e.delta/120),'units'))

        form=ttk.LabelFrame(right,text='Thông tin trích xuất',padding=10); form.pack(fill='x')
        for i,(key,label) in enumerate([('date','Ngày văn bản'),('number','Số / Ký hiệu'),('type','Loại hồ sơ'),('summary','Nội dung vắn tắt')]):
            ttk.Label(form,text=label,style='Card.TLabel').grid(row=i,column=0,sticky='w',pady=4)
            e=ttk.Entry(form,textvariable=self.vars[key]); e.grid(row=i,column=1,sticky='ew',padx=(10,0),pady=4); self.entries.append(e)
            self.vars[key].trace_add('write',lambda *args:self.preview_name())
        form.columnconfigure(1,weight=1)
        self.confidence_var=tk.StringVar(value='—'); ttk.Label(form,text='Độ tin cậy',style='Card.TLabel').grid(row=4,column=0,sticky='w',pady=4)
        ttk.Label(form,textvariable=self.confidence_var,style='Card.TLabel',font=('Segoe UI',10,'bold')).grid(row=4,column=1,sticky='w',padx=10)
        self.new=tk.StringVar(); ttk.Label(form,textvariable=self.new,style='Card.TLabel',foreground=self.BLUE,wraplength=430).grid(row=5,column=0,columnspan=2,sticky='w',pady=(10,2))

        actions=ttk.Frame(right,style='Card.TFrame'); actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='Lưu chỉnh sửa',command=self.save_current).pack(side='left')
        ttk.Button(actions,text='Mở PDF',command=self.open_pdf).pack(side='left',padx=6)
        ttk.Button(actions,text='Đánh dấu lỗi',command=lambda:self.transfer('ERROR')).pack(side='right')

        self.tabs=ttk.Notebook(right); self.tabs.pack(fill='both',expand=True)
        ocr=ttk.Frame(self.tabs,style='Card.TFrame'); self.tabs.add(ocr,text='Văn bản OCR')
        self.text=tk.Text(ocr,wrap='word',font=('Segoe UI',10),relief='flat',bg='white'); self.text.pack(fill='both',expand=True,padx=4,pady=4)

        foot=tk.Frame(self,bg='white',height=36); foot.pack(fill='x')
        tk.Label(foot,textvariable=self.status,bg='white',fg=self.MUTED,font=('Segoe UI',9)).pack(side='left',padx=22,pady=8)
        tk.Label(foot,text='v2.3 • Agent #01 • OCR nhanh • Ngoại tuyến',bg='white',fg=self.MUTED,font=('Segoe UI',9)).pack(side='right',padx=22)

    def _toggle_agent(self):
        self.agent_label.configure(text='●  Tự động đang hoạt động' if self.watch_enabled.get() else '○  Tự động đang tắt',foreground=self.GREEN if self.watch_enabled.get() else self.MUTED)

    def open_active_folder(self):
        try: os.startfile(self.engine.root/STATES[self.active_state])
        except Exception as exc: messagebox.showerror('Không mở được thư mục',str(exc),parent=self)

    def add_files(self):
        from tkinter import filedialog
        files=filedialog.askopenfilenames(parent=self,title='Chọn hồ sơ PDF',filetypes=[('PDF','*.pdf')])
        if not files:return
        inbox=self.engine.root/STATES['INBOX']; added=0
        for name in files:
            src=Path(name)
            try:
                dst=unique_path(inbox/src.name); shutil.copy2(src,dst); added+=1
            except Exception as exc:self.engine.log('IMPORT_ERROR',src,detail=str(exc))
        self.status.set(f'Đã thêm {added} hồ sơ • Agent sẽ tự xử lý')
        self.scan('INBOX')

    def update_counts(self):
        for k in STATES:
            try:self.count_vars[k].set(str(len(self.engine.scan(k))))
            except Exception:self.count_vars[k].set('—')

    def watch_tick(self):
        try:
            self.update_counts()
            if self.watch_enabled.get() and not self.busy:
                now=time.time(); current=set()
                for p in self.engine.scan('INBOX'):
                    try:
                        key=str(p); sig=(p.stat().st_size,p.stat().st_mtime_ns); current.add(key)
                        old=self.pending.get(key)
                        if old and old[0]==sig: self.pending[key]=(sig,old[1]+1)
                        else:self.pending[key]=(sig,1)
                    except OSError:pass
                for key in list(self.pending):
                    if key not in current:self.pending.pop(key,None)
                ready=[Path(k) for k,(sig,n) in self.pending.items() if n>=2 and Path(k).exists()]
                if ready:
                    for p in ready:self.pending.pop(str(p),None)
                    self.set_busy(True); self.status.set(f'Đang tự động xử lý {len(ready)} hồ sơ...')
                    def run(paths=ready):
                        good=bad=0
                        try:
                            self.engine.check_runtime()
                            for p in paths:
                                try:self.engine.auto_process(p,lambda s:self.events.put(('progress',s)));good+=1
                                except Exception as exc:
                                    bad+=1; d=self.engine.load(p); d.update(status='Lỗi xử lý',error=str(exc),analyzed=False)
                                    self.engine.log('AGENT_ERROR',p,detail=str(exc))
                                    try:self.engine.move(p,'ERROR',d)
                                    except Exception:pass
                            self.events.put(('done',f'Đã xử lý {good} hồ sơ' + (f' • {bad} lỗi' if bad else '')))
                        except Exception as exc:self.events.put(('done','Lỗi: '+str(exc)))
                    threading.Thread(target=run,daemon=True).start()
        finally:self.after(WATCH_INTERVAL_MS,self.watch_tick)

    def values(self):return {k:v.get().strip() for k,v in self.vars.items()}
    def preview_name(self):
        if hasattr(self,'new'):self.new.set(proposed(self.values()))
    def clear(self):
        self.current=None
        for v in self.vars.values():v.set('')
        self.confidence_var.set('—'); self.text.delete('1.0','end'); self.preview_box.delete('all'); self.page_index=0
    def persist(self):
        if self.current and self.current.exists() and not self.busy:
            d=self.engine.load(self.current); d.update(self.values()); self.engine.save(self.current,d)

    def scan(self,state=None):
        if self.busy:return
        if state:self.active_state=state
        self.persist();self.clear();self.tree.delete(*self.tree.get_children());self.rows={};self.update_counts()
        for p in self.engine.scan(self.active_state):
            d=self.engine.load(p); conf=d.get('confidence','')
            iid=self.tree.insert('','end',values=(p.name,proposed(d) if d.get('analyzed') or d.get('date') else '',d.get('type',''),d.get('date',''),(str(conf)+'%') if conf!='' else '—',d.get('status','')))
            self.rows[iid]=p
        labels={'INBOX':'Hồ sơ mới','REVIEW':'Cần kiểm tra','COMPLETED':'Đã xử lý','ERROR':'Lỗi xử lý'}
        self.status.set(f'{labels[self.active_state]}: {len(self.rows)} hồ sơ • Agent tự động: ' + ('BẬT' if self.watch_enabled.get() else 'TẮT'))

    def pick(self,event=None):
        if self.busy:return
        sel=self.tree.selection()
        if not sel:return
        p=self.rows[sel[0]]
        if p==self.current:return
        self.persist();self.current=p;d=self.engine.load(p)
        for k,v in self.vars.items():v.set(d.get(k,''))
        conf=d.get('confidence');self.confidence_var.set((str(conf)+'%') if conf is not None else '—')
        self.text.delete('1.0','end');self.text.insert('1.0',('LỖI: '+d['error']+'\n\n' if d.get('error') else '')+d.get('text',''))
        self.page_index=0;self.render_pdf()

    def render_pdf(self):
        self.preview_box.delete('all')
        if not self.current:return
        try:
            with fitz.open(stream=self.current.read_bytes(),filetype='pdf') as doc:
                page=doc[0]; width=max(360,self.preview_box.winfo_width()-20)
                scale=width/page.rect.width; pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
                self.photo=ImageTk.PhotoImage(Image.frombytes('RGB',[pix.width,pix.height],pix.samples))
                self.preview_box.create_image(10,8,anchor='nw',image=self.photo);self.preview_box.configure(scrollregion=(0,0,pix.width+20,pix.height+16))
        except Exception as exc:self.preview_box.create_text(20,20,anchor='nw',text='Không xem trước được PDF\n'+str(exc),fill=self.RED)

    def save_current(self):
        if not self.current:return
        self.persist();self.engine.log('METADATA',self.current);self.status.set('Đã lưu chỉnh sửa.');self.scan(self.active_state)

    def set_busy(self,flag):
        self.busy=flag
        for e in self.entries:e.configure(state='disabled' if flag else 'normal')

    def reocr_current(self):
        if not self.current or self.busy:return
        if not messagebox.askyesno('Xử lý lại OCR','Đọc lại hồ sơ và thay thế thông tin nhận diện hiện tại?',parent=self):return
        self.ocr_all([self.current],force=True)

    def ocr_all(self,paths,force=False):
        if self.busy or not paths:return
        self.persist();self.set_busy(True)
        def run():
            good=bad=0
            try:
                self.engine.check_runtime()
                for p in paths:
                    try:self.engine.analyze(p,lambda s:self.events.put(('progress',s)),force=force);good+=1
                    except Exception as exc:
                        bad+=1;d=self.engine.load(p);d.update(status='Lỗi OCR',error=str(exc),analyzed=False);self.engine.log('OCR_ERROR',p,detail=str(exc))
                self.events.put(('done',f'OCR xong: {good} thành công, {bad} lỗi'))
            except Exception as exc:self.events.put(('done','Lỗi: '+str(exc)))
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait();self.status.set(value)
                if kind=='done':self.current=None;self.set_busy(False);self.scan('REVIEW' if len(self.engine.scan('REVIEW')) else self.active_state)
        except queue.Empty:pass
        self.after(100,self.poll)

    def approve(self):
        if not self.current or self.busy:return
        try:
            d=self.engine.load(self.current);d.update(self.values());validate(d)
            dst=self.engine.approve(self.current,d);self.current=None;self.scan('REVIEW');self.status.set('Đã hoàn tất: '+dst.name)
        except Exception as exc:messagebox.showerror('Không thể hoàn tất',str(exc),parent=self)

    def transfer(self,state):
        if not self.current or self.busy:return
        try:
            d=self.engine.load(self.current);d.update(self.values());self.engine.move(self.current,state,d);self.current=None;self.scan(state);self.status.set('Đã chuyển hồ sơ.')
        except Exception as exc:messagebox.showerror('Không thể chuyển',str(exc),parent=self)

    def open_pdf(self):
        if self.current:
            try:os.startfile(self.current)
            except Exception as exc:messagebox.showerror('Không mở được PDF',str(exc),parent=self)

    def close(self):
        if self.busy:
            if not messagebox.askyesno('Đang xử lý','Hệ thống đang xử lý hồ sơ. Vẫn đóng ứng dụng?',parent=self):return
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
        check('confidence high',confidence(m)[0]>=AUTO_THRESHOLD,str(confidence(m)))
        check('confidence low',confidence({'date':'','number':'','type':'HS','summary':''})[0]<AUTO_THRESHOLD)
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
        try: print(report['error'], file=sys.stderr, flush=True)
        except Exception: pass
    target=(Path.cwd() if getattr(sys,'frozen',False) else APP_DIR)/'SELF_TEST_RESULT.json'
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