# Quickstart validation

运行前确认 PostgreSQL 17、Python 3.12、Node24 及 Docker Desktop 已就绪。复制本地 `.env.example` 仅在目标不存在时执行，不覆盖秘密。

```sh
uv sync --project backend --locked
uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
uv run --project backend --locked python -m serviceos_api.bootstrap_local
SERVICEOS_TEST_DATABASE_URL="$SERVICEOS_DATABASE_URL" uv run --project backend --locked pytest backend/tests --require-postgres
uv run --project backend --locked python -m serviceos_api.export_openapi --check
npm --prefix frontend ci
npm --prefix frontend run check:api
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:browser
npm --prefix frontend run test:live
```

交付文件实现后按 `docs/operations.md` 运行 Compose。先执行配置校验和一次性迁移，再启动 API、非模型 Worker 和 Web；只有获准且已配置真实 Provider 才启用模型 Worker。

实测客户咨询→Case关联→证据检查→人工协作→另一主管审批→明确模拟回执→客户核验→跟进→事实核验/归档；另测拒绝、UNKNOWN、重复点击、权限隔离、断网及刷新。没有通过的步骤保持未勾选。对隔离演示数据库演练重启/备份恢复，禁止对用户既有数据执行无确认清理。
