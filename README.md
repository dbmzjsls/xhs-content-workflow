# XHS Content Workflow

小红书内容生产工作台，把 Cathoven 小红书写作与图片生成方法论产品化成可审计的顺序工作流。

## What It Does

- 不是简单把主题丢给 AI 生成文案。
- 推文生成遵守 `小红书推文写作工作流.md`：情绪价值、痛点场景、黄金叙事弧线、发现式产品植入、去 AI 味、品牌名和标签硬规则。
- 图片生成遵守 `Cathoven生成图片工作流.md`：先判断图片任务，再选参考图，再改写 prompt；不默认生成桌面实拍和产品屏幕。
- 无模型 key 时使用 mock provider，仍能完整跑通：文案、图片 prompt、SVG fallback、质检、人工审核、发布包导出。

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[dev]
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8090
```

前端：

```powershell
cd frontend
npm install
npx vite --host 127.0.0.1 --port 5174
```

默认后端地址：`http://127.0.0.1:8090`  
默认前端地址：`http://127.0.0.1:5174`

## Optional Model Settings

```env
LLM_PROVIDER=openai
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
OPENAI_COMPATIBLE_MODEL=gpt-4o-mini
IMAGE_API_KEY=...
IMAGE_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-1
```

未配置时自动使用 mock。

参考图目录和 API 访问令牌可选配置：

```env
CATHOVEN_COVER_REFERENCE_DIR=./references/covers
CATHOVEN_PRODUCT_REFERENCE_DIR=./references/product
API_TOKEN=change-me
```

如果设置了 `API_TOKEN`，前端需要配置同值：

```env
VITE_API_TOKEN=change-me
```

## Migrations

项目提供 Alembic 初始迁移：

```powershell
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

默认使用 SQLite，设置 `DATABASE_URL=postgresql+psycopg://...` 后可迁移到 PostgreSQL。
