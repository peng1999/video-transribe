# Bilibili 转录（FastAPI + React）

前后端分离：FastAPI 后端负责下载/转录/整理；React 前端提供输入、进度展示与历史记录。

## 依赖
- Python 3.10+
- Node 18+
- ffmpeg（yt-dlp 提取音频需要）

## 配置
复制 `backend/.env.example` 到 `backend/.env` 并填入密钥：
```
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 后端运行（uv）
```bash
cd backend
# 安装依赖并生成 .venv
uv sync
# 运行开发服务
uv run uvicorn app.main:app --reload --port 8000
```
> 若 `uv` 不在 PATH，可用 `/home/linuxbrew/.linuxbrew/bin/uv` 调用。

## 前端运行
```bash
cd frontend
npm install
npm run dev -- --host
```
Vite dev server 通过代理将 `/api` 指向 `http://localhost:8000`，WebSocket `/ws` 同理。

## 接口概览
- `POST /jobs` { url } 创建任务并立即后台执行。
- `GET /jobs/{id}` 查询单个任务。
- `GET /jobs` 最近 50 条历史。
- `WS /ws/jobs/{id}` 持续推送阶段、字数和文本增量。

## 流程
1) yt-dlp 下载 Bilibili 音频 (mp3)。
2) OpenAI `gpt-4o-mini-transcribe` 流式转录，实时推送字数+增量文本。
3) DeepSeek Chat 流式格式化，实时推送整理后的增量文本。
4) 结果存储 SQLite，可在历史页查看。

## 注意
- 仅允许 bilibili.com 链接。
- Whisper 文件大小上限 25MB；如需更大，先裁剪或降低音质。
- 临时文件在任务结束后会删除。
- 已下载的音频会按 URL 哈希缓存在 `backend/cache/`，重复请求相同 URL 会复用；可通过 `AUDIO_CACHE_DIR` 自定义位置。

# TODO
- 在前端的首页界面，如果当前的任务失败了，立刻显示错误信息，如同 /?job 界面点进去看到的错误信息一样
- 添加鉴权功能