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
- `npm run test:browser`：**60 passed**（42.9s），含 /support 与 /desk 的桌面/手机 axe 无障碍检查，以及交付就绪专题的未知组件、越权动作、过期 revision、过期时间与降级用例。

本机 Playwright 浏览器原本下载不通（40 分钟只留下 `__dirlock`）。改用国内镜像后完成安装，未改动任何测试代码：

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST='https://cdn.npmmirror.com/binaries/playwright'
npm exec playwright install chromium
```

### 真实浏览器端到端（live）

在独立数据库 `serviceos_dev`（本地全新迁移 + `bootstrap_local` 播种）上执行，不触碰体验库 `serviceos_demo_20261014_delivery`：

- `npm run test:live`：**6 passed**（52.1s）。覆盖持久会话与人工接管、PUBLIC/INTERNAL 隔离、跨客户/跨租户拒绝、模拟动作申请→主管审批→Worker 回执→客户投影、客户同意后的回访排期、事实核验后归档、图片上传→检查→授权预览。
- Worker 子进程通过 `env: process.env` 继承环境，因此 `SERVICEOS_DATABASE_URL` 等变量必须一并导出，否则 Worker 会连到默认库而测试库里看不到回执。
- 本次以 `SERVICEOS_LIVE_EXTERNAL=1` 自行托管 API/Vite，原因见下方环境说明。

### 运行时联调（真实进程，非测试替身）

- `POST /api/v1/local-auth/login`（customer-a）：200；`GET /api/v1/conversations`：200，返回既有会话。
- `POST /api/v1/local-auth/login`（staff）：200；`GET /api/v1/skills`：200，返回 `diagnose-no-charge` 1.0.0（AVAILABLE）与 `emotion-assessment` 1.0.0（PREPARED）及各自 input/output Schema。
- 客户身份（customer-a）访问 `GET /api/v1/skills`：403，未登录：401，均不泄露内部 Skill 目录。

### 全量回归（T028）

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 后端 | `pytest backend/tests --require-postgres -q`（`SERVICEOS_ENV=test`、`SERVICEOS_AUTH_MODE=disabled`，与 CI 一致） | **168 passed**，24.88s |
| 迁移 | 对全新空库 `serviceos_dev` 执行 `alembic -c backend/alembic.ini upgrade head` 后 `bootstrap_local` | 0001→0013 全部应用，样例身份 2 客服 / 3 客户 |
| 前端契约 | `export_openapi --check`、`sync_implemented.py --check`、`check:api`、`typecheck`、`build` | 全部通过，无漂移 |
| 浏览器 | `npm run test:browser` | **60 passed**，42.9s |
| 真实端到端 | `npm run test:live`（`SERVICEOS_LIVE_EXTERNAL=1`，独立库） | **6 passed**，52.1s |
| 部署配置 | `docker compose ... config -q` × 3、`unittest discover -s deploy -p test_preflight.py` | 通过，10 tests OK |

**未测项（不得视为通过）**：模型首 token 时延、工具耗时、进程强制中断后的多轮恢复、Provider 异常退避；托管模式 live（见下）；容器构建与运行演练结果见下节。

#### 响应耗时（T028 要求的分位数）

数据来自上面那次真实端到端运行时 API 进程的结构化日志，用仓库自带的采集工具统计，**不是生产负载也不是压测**：

```powershell
python -m serviceos_api.operations metrics --log <http.completed 日志>
```

| 指标 | 样本 | P50 | P95 |
| --- | --- | --- | --- |
| `http_request_ms` | 992 | 12.29 ms | 33.89 ms |
| `http_accept_ms`（消息受理 202 路径） | 6 | 17.21 ms | 22.05 ms |

`error_rate` 为 0.0。工具同时明确列出**无法从日志测量**的指标：`queue_delay_ms`、`agent_first_progress_ms`、`model_ttft_ms`、`tool_latency_ms`、`ui_action_completion_ms`——这些要么需要真实模型调用，要么需要在 Worker 侧埋点，当前没有数据。

### 容器与部署配置

- `docker compose --env-file deploy/local/.env.example -f compose.yaml --profile seed --profile agent config -q`：通过。
- `docker compose --env-file deploy/test/.env.example -f deploy/compose.test.yaml config -q`：通过。
- `docker compose --env-file deploy/production/.env.example -f compose.production.yaml --profile agent config -q`：通过。
- 缺失必填密码/数据库配置时必须失败的负向断言仍由 CI 的 delivery-config 作业执行，本地只验证了正向 config。

### 容器构建与运行演练（T012）

按 CI `container-smoke` 的同一序列在本地容器里实跑，全部通过：

| 步骤 | 结果 |
| --- | --- |
| 构建 `serviceos-backend:local`（445 MB）与 `serviceos-web:local`（93.3 MB） | 成功 |
| `up -d --no-build --wait --wait-timeout 240` | postgres / migrate（退出码 0）/ api / web / inspection / actions / followups / outbox 全部 Healthy |
| `--profile seed run --rm --no-deps seed` | 样例身份初始化完成 |
| `exec -T web nginx -t` | 语法与配置校验通过 |
| 经 Web 访问 `http://127.0.0.1:8080/api/v1/readiness` 与 `/support` | 均 200，就绪报告 database/schema ready |
| `exec -T api` 非 root 校验并写入共享卷 | uid 10001，写入 `/data/evidence` 成功 |
| `restart postgres api inspection` 后重新 `up --wait` | 全部恢复 Healthy，`/data/evidence` 内容仍在，就绪仍 200 |
| 生产 HTTPS 模板 + 一次性自签证书 `nginx -t` | 通过（`SERVICEOS_PUBLIC_HOSTNAME` 环境变量替换生效） |

演练后按 CI 的做法 `down --volumes --remove-orphans` 清理本栈，未触碰体验库 `serviceos_demo_20261014_delivery`。

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
6. **客户可见的发言策略文案缺失**：客户面改用独立的协助区块后，策略行丢了「发言策略：」标签，而 live 验收断言钉着这段措辞。该标签本身是客户需要的信息——它说明是 AI 自动回复还是仅人工回复。由真实浏览器端到端发现（补齐 Playwright 之后才跑得起来），已恢复。
7. **容器内就绪检查永远失败**：`api/health.py` 用 `Path(__file__).parents[2]` 推断 `alembic.ini`，但镜像里包是**非可编辑安装**进 venv 的，该路径落在 `site-packages`，那里没有配置文件；`ScriptDirectory.from_config` 抛出的 `CommandError` 又不在捕获列表内，于是就绪接口返回 **500** 而不是"未就绪"。后果是 API 容器永远不健康、`docker compose up --wait` 与 CI 的容器冒烟必然失败。改为向上查找配置文件（非可编辑布局下项目根在更靠上的层级）并支持 `SERVICEOS_ALEMBIC_CONFIG` 显式覆写，同时把 `CommandError`/`OSError` 纳入捕获，配置缺失时如实报告未就绪。**这个缺陷只有真正把容器跑起来才会暴露**——`config -q` 校验和本机源码运行都看不出来。

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

- **Playwright 托管 webServer 在本机不稳定**：`npm run test:live` 不设 `SERVICEOS_LIVE_EXTERNAL` 时，它自己拉起的 `npm run dev`（npm→node→vite 三层进程树）会中途不可达，本轮三次托管运行里有两次出现 `ERR_CONNECTION_REFUSED:5173`；同一时间 uvicorn 全程存活、无关停日志，说明只有 vite 掉了。改为 `SERVICEOS_LIVE_EXTERNAL=1` 自托管 API/Vite 后 6/6 稳定通过。CI 运行的是托管模式（Linux runner），本机未复现 CI 的条件，因此**不能**用本地结论替代 CI 结果。
- **容器构建的镜像来源在本网络不可用**：`docker compose build` 默认要回源 Docker Hub 解析基础镜像，本机直连超时；`uv sync --locked` 也**不能**改用镜像源（实测传入 `--index-url` 后 uv 会判定锁文件过期并直接失败）。因此上面的演练使用了本机已有的 DaoCloud 基础镜像与引导安装镜像（仅本地构建，交付默认值不变）。在正常网络下按文档 `docker compose build` 即可，本机只是绕过了拉取环节。
- **生产身份源**：未接入。生产配置拒绝本地开发登录，`production_ready` 恒为 false。
- **受控对象存储**：S3 适配器与部署策略已就位但未对接真实存储桶；生产配置下不静默回退本地磁盘，接口返回不可用。
- **云上能力**：EC2/RDS/Nginx/HTTPS 仅到可复现配置与模板校验，未创建任何云资源，未做真实 HTTPS 握手。
- **真实 Anker 外部接口**：不存在，现有回执均带 `MOCK` 标识，不代表真实售后结果。
