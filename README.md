# PBOS — Personal Brand Operating System

PBOS là hệ điều hành cá nhân phục vụ quản trị sự nghiệp, năng lực, dự án, nội dung và portfolio dài hạn của Phan Van Ngoc.

## Cấu trúc

```text
PBOS
├── index.html
├── assets
│   ├── css/style.css
│   └── js/app.js
├── data
│   ├── kpi.json
│   ├── projects.json
│   ├── learning.json
│   ├── content.json
│   ├── portfolio.json
│   └── career.json
└── docs
    └── operating-guide.md
```

## Cách cập nhật

Không sửa dữ liệu trực tiếp trong HTML.

Sửa các file trong thư mục `data/`:

- KPI: `data/kpi.json`
- Dự án: `data/projects.json`
- Học tập: `data/learning.json`
- Nội dung: `data/content.json`
- Portfolio: `data/portfolio.json`
- Lộ trình sự nghiệp: `data/career.json`

## Deploy

Dùng GitHub Pages:

Settings → Pages → Deploy from a branch → main → /root → Save.

Website sẽ chạy tại:

`https://vanngocphann97.github.io/Pbos/`
