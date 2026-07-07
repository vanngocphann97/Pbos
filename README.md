# PBOS v1.3 — Standalone Admin

PBOS v1.3 là website cá nhân độc lập, không cần Python, Excel, Microsoft 365, Notion hoặc Airtable.

## Cấu trúc

```text
Pbos
├── index.html
├── admin.html
├── assets
│   ├── css/style.css
│   └── js
│       ├── app.js
│       └── admin.js
├── data
│   └── pbos-data.json
└── docs
    └── operating-guide.md
```

## Cách cập nhật dữ liệu

1. Mở `admin.html` trên website:
   `https://vanngocphann97.github.io/Pbos/admin.html`
2. Bấm `Load data`.
3. Sửa JSON.
4. Bấm `Validate`.
5. Bấm `Export JSON`.
6. Upload file `pbos-data.json` lên GitHub tại:
   `data/pbos-data.json`
7. Commit changes.
8. Website tự cập nhật.

## Nguyên tắc bảo mật

Repo GitHub Public thì không lưu file mật, hồ sơ nội bộ, hợp đồng, quyết định, CCCD hoặc dữ liệu nhạy cảm.
Chỉ lưu metadata và link riêng tư nếu cần.
