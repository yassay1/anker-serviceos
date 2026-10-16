# 双击体验与热更新

在项目根目录双击 `启动体验.bat`。浏览器自动打开 http://127.0.0.1:5173/；启动窗口会依次显示前端、数据库、API 和各 Worker 状态。完成启动后登录本地客户或客服账号。默认本地样例密码见 `backend/.env.example`；已有 `backend/.env` 时以其中配置为准。

- 前端 React/CSS 修改后自动热更新；API Python 修改后自动重载。
- 保持启动窗口打开。双击 `停止体验.bat` 或在启动窗口按 Ctrl+C 停止本次应用进程。Windows 关闭启动窗口也会结束受管应用子进程。
- 再次双击启动不会重复启动一套服务，会打开已运行的页面。
- 数据库、迁移或后端有问题时保留前端；真实业务功能依赖数据库，不能把仅页面打开当作功能可用。
- 数据库成功连接后启动 inspection/actions/followups/outbox。没有模型时不运行 AI；配置 Provider 后，另在 `backend/.env` 写入 `SERVICEOS_START_AGENT=1` 再重启。
- 需要同时处理多个会话时，在 `backend/.env` 设置 `SERVICEOS_AGENT_WORKERS=3` 后重启；默认 1，可设 1～4。多个 Worker 使用同一 Agent 与数据库队列，不同会话并行，同一会话由现有租约和会话锁串行处理；这不会让单条回复生成得更快。新增进程日志为 `agent-2.log`、`agent-3.log`。
- Worker、依赖或环境配置修改后需停止并重新启动。前端未安装依赖时，先在 `frontend` 执行 `npm ci`；后端使用现有 `backend/.venv`，缺失时按后端 README 恢复。
- 启动器只自动迁移显式开发认证下、回环地址的 `serviceos_dev`，不会重置、清库或自动迁移远程/生产数据库；首次不存在 `.env` 时才复制样例。
- PostgreSQL 启动后保留运行和数据，停止体验只停止本次应用服务，避免影响其他本地数据库使用方。

日志在 `.runtime/dev-launcher/`；启动状态在 http://127.0.0.1:5172/status。失败时查看对应 `frontend.log`、`api.log`、`migrate.log` 或 Worker 日志，日志中可能包含用户输入，分享前应检查。

本机可选 PostgreSQL 配置位于忽略的 `.runtime/launcher-local.json`，字段 `pg_ctl` 为程序路径、`data_dir` 为已有数据目录。启动器不会自动下载或重建数据库。在其他电脑上可自行先启动 PostgreSQL，不需要此文件。

仅看前端可在命令行执行 `启动体验.bat --frontend-only`。默认固定使用 5172（启动管理）、5173（页面）和 8000（API）；其他程序占用端口时会提示，不会杀死其他程序。

## 本机验证（2026-10-16）

- 4 项离线检查通过：已有 `.env` 保留、首次复制样例、拒绝自动迁移远程/非开发数据库、模型默认关闭。
- 实际通过两个 `.bat` 完成启动、停止、仅前端启动、再次完整启动和重复启动复用。
- 本机 PostgreSQL 17.11 保留原数据，正常恢复后迁移至 `0014_experience_candidates`；本地身份初始化成功。
- readiness 返回 200，数据库/Schema/本地身份/存储就绪；Provider 未配置。客户实际登录返回 200，可读取 2 个会话、2 个案例和 1 个设备。
- inspection/actions/followups/outbox 四个 Worker 心跳检查退出码为 0。
- 仅前端模式下网页返回 200、API 8000 端口未运行；停止后能够再次完整启动。
- 触发文件变更后，Vite 实际记录 CSS HMR update，Uvicorn 实际记录 API 文件变更并执行 Reload；没有修改业务源码内容。
- 本机必需的 PostgreSQL 程序已复制到 `.runtime/tools/postgresql`，启动入口不依赖旧 `integration` 工程或其隔离副本。数据目录仍是现有的 `D:\AnkerServiceOSPreview\data`，未重置。
