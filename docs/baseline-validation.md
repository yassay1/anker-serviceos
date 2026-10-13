# 阶段 0 实际验收记录

> 本文记录阶段 0 完成当时的真实文件和命令。2026-10-13 工作区整理后，旧 A1229 原型目录和根级原型测试入口已归档到项目外，不再是当前工程结构；下文对应文件清单与测试仅作为历史验收证据。

日期：2026-10-12。范围：V1 主文档合并、同仓前后端骨架、健康接口、真实契约和生成 Client。本记录不代表后续业务或生产验收。

## 变更文件

- 主入口：根 `README.md`、`AGENTS.md`、`.gitignore`。
- 主基线：`docs/product-definition.md`、`architecture.md`、`domain-and-contracts.md`、`development-plan.md`。
- 衔接/来源：`docs/baseline-integration.md`、`baseline-provenance.json`、`references.md`、本验收记录。
- 新后端：`backend/pyproject.toml`、`uv.lock`、`.python-version`；`backend/serviceos_api/main.py`、`__init__.py`、`api/health.py`、`api/__init__.py`、`export_openapi.py`；`backend/tests/test_api_baseline.py`。
- 新前端：`frontend/package.json`、`package-lock.json`、`.node-version`、`tsconfig.json`、`vite.config.ts`、`index.html`；`frontend/src/main.tsx`、`App.tsx`、`styles.css`、`api/client.ts`、`api/schema.d.ts`；`frontend/scripts/check-api.mjs`。
- 生成契约：`contracts/openapi.json`。
- CI：`.github/workflows/ci.yml`。
- 项目进度：根 `task_plan.md`、`findings.md`、`progress.md`，保留原有历史条目。

## 实际环境

Python 3.12.14、Node 24.16.0、npm 11.13.0、uv 0.12.5。新 backend 和根原型使用独立 Python 环境及锁文件；Web 固定兼容 TypeScript 5.9.3，依赖精确版本和 npm lock。

## 命令与结果

| 实际命令 | 位置 | 结果与范围 |
|---|---|---|
| `uv sync --project backend --python .venv\Scripts\python.exe` | 根目录 | 创建新 backend 环境、生成锁文件并安装；根原型环境保留 |
| `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` | 根目录 | 1 passed；保留的领域验证/事务测试 |
| `uv run --project backend --locked pytest backend/tests -q -p no:cacheprovider` | 根目录 | 2 passed；真实健康接口、OpenAPI 路径及未实现路由拒绝 |
| `uv run --project backend --locked python -m serviceos_api.export_openapi` | 根目录 | 导出实际 schema，只有 `/api/v1/health` |
| `uv run --project backend --locked python -m serviceos_api.export_openapi --check` | 根目录 | 同源契约一致，无写入 |
| `npm install --no-fund` | frontend | 最终成功，生成锁文件；首次 TypeScript 7 peer 冲突已改为 5.9.3 |
| `npm run generate:api` | frontend | 生成 OpenAPI 类型供 openapi-fetch 使用 |
| `npm run check:api` | frontend | 生成类型与契约一致，无写入 |
| `npm run build` | frontend | TypeScript 类型检查与 Vite 构建通过 |
| `npm ci --no-fund`，随后 `npm run check:api`、`npm run build` | frontend | 按锁文件重新安装并重验通过；npm 报告 0 vulnerabilities |
| 本地 Uvicorn + `npm run dev` | 根目录 / frontend | API 与 Web 回环启动，健康 API 实际 HTTP 200 |

FastAPI/Starlette TestClient 在使用当前 httpx 时有 1 条弃用提醒，两个断言均通过；后续测试依赖升级时复核。CI 已加入原型回归、后端测试、契约检查、SDK 检查和构建；当前目录无 Git/远端，本轮未执行远端 CI。

## 浏览器结果

- `/support` 用户入口与 `/desk` 客服入口可切换；导航 `aria-current` 正确。
- 实际健康请求显示“已连接本地服务”。暂停本轮 API 后点击检查，显示“本地服务未连接”；恢复后重试返回已连接。
- 业务按钮保持 disabled，并说明尚未开放；不伪造会话、案件、任务、Agent 进度或服务成功。
- 默认桌面截图与 375×812 窄屏截图已目视检查；375px 视口的文档宽度 360px，812px 横屏的文档宽度 797px，没有横向溢出。
- 键盘 Tab 可聚焦“跳到主要内容”，显示位置 top=8px；导航有当前项标识。页面采用本地字体、清晰文字/聚焦边框和实际加载/失败反馈，无自动动画。
- UI 技能搜索的企业应用轻量风格适用，但默认营销 Hero 模式不适合此工作台；本页按工作区需求采用简洁布局，未把检索输出直接固化为产品设计系统。
- 验收结束已重置临时视口尺寸。

## 保留核查

- `app/`、`tests/`、`specs/`、`service_skills/`、`service_capabilities/`、`.specify/` 下排除字节码后，94 个原文件哈希前后相同，包含演示素材。
- 共享目录五份主基线源文件 SHA256 与 [来源清单](baseline-provenance.json) 一致；共享文件未修改。
- README 与 docs 的相对 Markdown 文件链接检查未发现缺失。

## 后续范围

阶段 1 首先实现 PostgreSQL 模型/迁移、身份与资源授权、Device/Case/Conversation 应用服务及幂等消息；详见 [合并计划](baseline-integration.md)。目前未接入 PostgreSQL、真实 LLM、独立 Worker、SSE、售后业务系统、人机协作或云部署，健康检查仅表示 API 存活。
