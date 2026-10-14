# 阶段五交付准备与集成验收

日期：2026-10-14。基线 main `10fe1fcd60b02c54430df0aa66af784767a3963d`；开发分支 `phase5/delivery-readiness`。不部署上线，不创建云资源。

本文件只记录**实际执行过**的命令与结果。未执行、未通过或无法在本网络复现的项目单列，不得当作已完成。

## 已实际执行

### 代码获取与基线

- Git smart HTTP 直连/代理均失败；改用已授权 gh 只读 Git Data API 取回 25 个新增提交及树/Blob。每个对象按原 SHA 验证，`git fsck --connectivity-only --no-dangling <head>` 通过，main fast-forward 到 10fe1fc，旧图片分支保留。
- 读取用户 8 页 PDF；Poppler 缺失时使用 pypdf 提取 UTF-8 全文。

### 后端

- `SERVICEOS_TEST_DATABASE_URL=<本地PostgreSQL> .venv/Scripts/python.exe -m pytest tests -q`
  - 基线：104 passed
  - 本轮收尾：**168 passed**，25.25s。测试使用独立随机数据库，无 SQLite 回退。
- 本轮由失败测试先复现、后修复的问题（详见下节）。
- `python -m serviceos_api.export_openapi --check`：先报漂移，执行导出后与实现一致。
- `python contracts/proposed/v1/sync_implemented.py --check`：先报漂移，执行同步后一致。
- `python -m unittest discover -s deploy -p test_preflight.py`：10 tests OK。
- `python -m serviceos_api.worker.health --role <role>`：inspection / actions / followups / outbox 四个进程在真实运行中均返回健康（退出码 0）。

### 前端

- `npm run typecheck`：通过（含 `tsconfig.browser-tests.json`）。
- `npm run build`：通过，产物 390.12 kB（gzip 118.57 kB）+ 24.30 kB CSS。
- `npm run check:api`：API types match OpenAPI。
- `npm run generate:api`：`contracts/openapi.json` → `src/api/schema.d.ts` 重新生成，新增 Skill 目录与执行记录接口类型。

### 运行时联调（真实进程，非测试替身）

- `POST /api/v1/local-auth/login`（customer-a）：200；`GET /api/v1/conversations`：200，返回既有会话。
- `POST /api/v1/local-auth/login`（staff）：200；`GET /api/v1/skills`：200，返回 `diagnose-no-charge` 1.0.0（AVAILABLE）与 `emotion-assessment` 1.0.0（PREPARED）及各自 input/output Schema。
- 客户身份（customer-a）访问 `GET /api/v1/skills`：403，未登录：401，均不泄露内部 Skill 目录。

### 容器与部署配置

- `docker compose --env-file deploy/local/.env.example -f compose.yaml --profile seed --profile agent config -q`：通过。
- `docker compose --env-file deploy/test/.env.example -f deploy/compose.test.yaml config -q`：通过。
- `docker compose --env-file deploy/production/.env.example -f compose.production.yaml --profile agent config -q`：通过。
- 缺失必填密码/数据库配置时必须失败的负向断言仍由 CI 的 delivery-config 作业执行，本地只验证了正向 config。

### 本地可用服务（体验环境）

| 服务 | 地址 | 状态 |
| --- | --- | --- |
| 前端 `/support`、`/desk` | http://127.0.0.1:5173 | 200 |
| API 就绪检查 | http://127.0.0.1:8000/api/v1/readiness | ready（database/schema ready，auth local_development，storage local_development，provider configured_unverified） |
| Agent 主 Worker | `python -m serviceos_api.worker.main` | 心跳健康，已用真实 Provider 完成两轮对话 |
| 图片检查 Worker | `python -m serviceos_api.worker.inspection` | 心跳健康 |
| 模拟动作 Worker | `python -m serviceos_api.worker.actions` | 心跳健康 |
| 回访 Worker | `python -m serviceos_api.worker.followups` | 心跳健康 |
| Outbox 派发进程 | `python -m serviceos_api.worker.outbox` | 心跳健康 |
| PostgreSQL | 127.0.0.1:55432 | 运行中 |

## 本轮修复（均有先失败的测试）

1. **核验绕过**：最新动作成功时，只要客户确认 WORKING 就直接 `VERIFIED_RESOLVED`，忽略了同一 Case 上更早的 `WAITING_APPROVAL/APPROVED/EXECUTING/UNKNOWN` 动作仍可能继续执行并改变设备。现要求同一 Case 不存在未决动作才允许解决。
2. **Worker 心跳缺失**：compose 为 inspection/actions/agent 声明了基于心跳的健康检查，但这三个 worker 用自带循环，从不写心跳，容器健康检查必然失败。现统一走 `run_loop`。
3. **Skill 来源围栏测试不可构造**：原用例靠改写客户消息 `visibility` 伪造来源，而数据库约束不允许客户消息非 PUBLIC，测试实际抛 IntegrityError。改为用内部客服备注作为不可授权来源。
4. **测试隔离**：共享会话级数据库里，前序用例遗留的未派发 Outbox 事件会被后序 `claim_batch()` 领取，使既有断言偶发失败。测前统一隔离重置。
5. **Skill 路由未挂载**：`api/skills.py` 写好后没有在 `main.py` 注册，接口在生产与本地都不可达。`test_skills.py` 自行 `include_router` 组装测试应用，所以在单测里看不出问题；`contracts/openapi.json` 也因此一直没有这两个接口。已注册，并补上"每个 `serviceos_api.api.*` 路由模块都必须出现在真实应用 OpenAPI 里"的回归。

### 真实模型 Provider 联调（2026-10-14 晚）

用户在 `backend/.env` 提供 OpenAI 兼容端点（`deepseek-v4-pro`，密钥不入库、`.env` 已被忽略）。执行顺序：

```powershell
uv run --project backend --locked python -m serviceos_api.checkpoints   # 初始化 LangGraph 检查点 schema
uv run --project backend --locked python -m serviceos_api.worker.main   # Agent 主 Worker
```

`GET /api/v1/readiness` 由 `provider: not_configured` 变为 `provider: configured_unverified`。随后用 customer-a 身份发送两条真实消息：

| 观察项 | 结果 |
| --- | --- |
| 首轮 AgentRun | COMPLETED，step_count 10，无错误码 |
| 二轮 AgentRun | COMPLETED，step_count 12，无错误码 |
| 客户可见消息 | `GET .../messages` 返回 CUSTOMER + AGENT 两条 PUBLIC 消息 |
| 进度事件 | `agent.progress` 依 RUNNING → LOOKUP → RUNNING → COMPLETED 发布，visibility 均为 PUBLIC，payload 只含 run_id/stage/summary |
| Generative UI | `GET .../ui-document` 返回 revision 1 的公开 UI Document |
| 回复内容 | 型号未经核验时明确不套用 A1229 规格、先排安全项、给安全可逆步骤并追问缺失信息 |

这证明真实 Provider 链路可跑通，**不等于阶段 2 验收通过**：模型首 token 时延、工具耗时、进程强制中断后的多轮恢复、Provider 异常退避仍未有测量数据。

## 尚未通过或无法在本网络验证的门槛

- **真实模型 Provider 未做完整验收**：本地已跑通两轮真实多轮对话（见上节），但首 token 时延/工具耗时统计与进程中断恢复仍属阶段 2 未验收范围。

- **浏览器端自动化**：本机 Playwright 浏览器未能下载完成，`npm run test:browser` 与 `npm run test:live` **本轮未取得本地结果**，当前状态不能算通过。CI 在 GitHub runner 上执行这两项。
- **容器构建与运行演练**：本网络到 Docker Hub / PyPI 不稳定。镜像构建使用本机已有 DaoCloud 来源与本地点镜像源（仅本地），交付默认镜像来源不变；`docker compose build` + 启动 + 重启 + 卷持久化演练结果见下节。
- **生产身份源**：未接入。生产配置拒绝本地开发登录，`production_ready` 恒为 false。
- **受控对象存储**：S3 适配器与部署策略已就位但未对接真实存储桶；生产配置下不静默回退本地磁盘，接口返回不可用。
- **云上能力**：EC2/RDS/Nginx/HTTPS 仅到可复现配置与模板校验，未创建任何云资源，未做真实 HTTPS 握手。
- **真实 Anker 外部接口**：不存在，现有回执均带 `MOCK` 标识，不代表真实售后结果。
