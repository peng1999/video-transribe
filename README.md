# Bilibili 转录（FastAPI + React）

前后端分离：FastAPI 后端负责下载/转录/整理；React 前端提供输入、进度展示与历史记录。

## 依赖
- Python 3.13+
- Node 18+
- ffmpeg（yt-dlp 提取音频需要）
- Docker 镜像使用 `python:3.13-slim`（后端）与 `node:20-alpine`（前端构建）

## 配置
复制 `backend/.env.example` 到 `backend/.env` 并填入密钥：
```
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=...                # 阿里百炼
# S3 兼容存储（Garage 或 OSS/S3），path-style
S3_ENDPOINT=http://localhost:8021/
S3_PUBLIC_ENDPOINT=http://your-public-domain/
S3_REGION=garage
S3_BUCKET=transcribe
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
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

运行后端格式化：
```bash
uv run black app
```

## 前端运行
```bash
cd frontend
npm install
npm run dev -- --host
```
Vite dev server 通过代理将 `/api` 指向 `http://localhost:8000`，WebSocket `/ws` 同理。

## 接口概览（均带前缀 /api）
- `POST /api/jobs` { url } 创建任务并立即后台执行。
- `GET /api/jobs/{id}` 查询单个任务。
- `GET /api/jobs` 最近 50 条历史。
- `WS /api/ws/jobs/{id}` 持续推送阶段、字数和文本增量。

## 流程
1) yt-dlp 下载 Bilibili 音频 (mp3)。
2) 前端选择 ASR 提供方：
   - OpenAI `gpt-4o-mini-transcribe` 流式转录。
   - 阿里百炼 `qwen3-asr-flash-filetrans`：音频上传到 OSS，异步轮询结果。
   两种都会实时推送字数/文本增量。
3) DeepSeek Chat 流式格式化。
4) 结果存储 SQLite，可在历史页查看。

## 注意
- 仅允许 bilibili.com 链接。
- OpenAI 模式仍受 Whisper 25MB 上限限制；百炼模式由 OSS/模型限制为可公网获取的音频。
- 临时文件在任务结束后会删除。
- 已下载的音频会按 URL 哈希缓存在 `backend/cache/`，重复请求相同 URL 会复用；可通过 `AUDIO_CACHE_DIR` 自定义位置。

## Docker + Garage（可选本地 S3）
- 追加服务：`docker/docker-compose.yml` 中提供 Garage S3（镜像 `dxflrs/garage:v2.1.0`）。启动：
  ```bash
  cd docker
  docker compose up -d garage
  ./init-garage.sh          # 首次生成 bucket 与访问密钥
  ```
- 脚本会输出 `AWS_ACCESS_KEY_ID/SECRET`, `S3_BUCKET=transcribe`，可供后端使用；`S3_ENDPOINT` 由前端域名的 `/s3/` 反代提供。
- Garage 配置在 `docker/garage.toml`，默认 `rpc_secret` 与 `admin_token` 请按需修改后再启动。若已启动需 `docker compose restart garage` 生效。
- 端口策略：Garage 不暴露外部端口；Nginx 将同域 `/s3/` 代理到 `garage:3900`，签名时需包含 `/s3` 前缀。

# TODO
- 优化移动端显示
  - 让左右的 padding 更小
- 显示详细信息，如视频长度，使用token数，预估花费等
- 允许用户提供校正用的术语
