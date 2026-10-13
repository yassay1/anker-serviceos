# Quickstart

1. 按 README 启动本地 PostgreSQL，运行 `uv run --project backend --locked alembic -c backend/alembic.ini upgrade head`。
2. 设置 `SERVICEOS_TEST_DATABASE_URL`，执行 `uv run --project backend --locked pytest backend/tests --require-postgres -q`。
3. 执行 `uv run --project backend --locked python -m serviceos_api.export_openapi --check`；在 `frontend/` 执行 `npm run check:api`、`npm run typecheck`。
4. 真实 Provider 多轮与杀进程恢复须在有合法模型配置后另行验收，不以测试替身代替。
