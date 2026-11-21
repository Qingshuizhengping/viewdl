# ViewDL

粘贴链接 → 解析 → 挑文件与清晰度 → 下载。本地运行。

## 启动

双击 `start.bat`，打开 http://127.0.0.1:8770

```
.venv\Scripts\python.exe app.py   # 手动启动
downloads/                        # 下载产出
cookies.txt                       # 可选：B站/YouTube 高清、登录内容
```

## 平台

| 平台 | 内容 |
|---|---|
| 抖音 | 视频（多档无水印）/ 图集 / 音乐 |
| 快手 | 短视频（多档） |
| 小红书 | 视频笔记 / 图集 / 实况图（照片 + MOV） |
| 微博 | 视频（多档）/ 多图 |
| 公众号 | 文章图片 |
| B站 / YouTube / TikTok / X / Instagram 等 | yt-dlp 全站通用 |

## 接口

`POST /api/parse {text}` → `POST /api/download {platform,title,raw_url,items[]}` → `GET /api/jobs` / `GET /api/history` / `GET /api/file?name=` / `POST /api/open-folder`
