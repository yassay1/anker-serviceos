# 黑客松演示版缺口与本机 UI 预览

日期：2026-10-15。用户确认以“黑客松可提交、可演示版本”为标准。本机预览基于 `adb4610`，分支 `codex/local-ui-preview`；不是生产部署。

## 已启动的真实预览

| 入口 | 地址或状态 |
|---|---|
| 用户服务 | http://127.0.0.1:5173/support |
| 客服工作区 | http://127.0.0.1:5173/desk |
| 服务案例 | http://127.0.0.1:5173/cases |
| 设备档案 | http://127.0.0.1:5173/devices |
| 实际 API 文档 | http://127.0.0.1:8000/docs |
| 依赖就绪检查 | http://127.0.0.1:8000/api/v1/readiness |
| 数据库 | PostgreSQL 17.11，127.0.0.1:55432，仅本机访问 |
| 无模型后台进程 | inspection / actions / followups / outbox 均已启动并通过心跳检查 |
| Agent 模型进程 | 未启动；当前机器未配置 Provider，不生成假回复/假进度 |

前端运行 `npm run dev`，不是静态 preview 构建。浏览器已观察到 `[vite] connected.`；修改 `frontend/src` 的 React/CSS 即可热更新。状态和业务数据仍从实际 API、PostgreSQL 与独立 Worker 获取。

本地开发账号：`customer-a`、`customer-b`、`staff`、`supervisor`、`other-tenant`；此机器使用仓库样例密码 `serviceos_local_only`，仅限本地合成演示。客服与主管是不同身份，模拟动作不能自批。切换身份需退出后重新登录；同一浏览器的标签页共享登录 Cookie。

演示资料通过真实 API 创建并带“演示”“合成”“MOCK”标识：一个待处理案例、一个经模拟审批/Worker 回执/客户确认而解决的案例、关联会话、设备档案、客户同意后的回访预约及归档事实。未导入真实客户信息。服务器保存的内容刷新后仍保留；状态不是前端写死。

资源编号保存在忽略的 `.runtime/preview-demo.json`，后台进程与日志在 `.runtime/preview-*`。数据库文件在 `D:\AnkerServiceOSPreview\data`；ASCII 路径用于规避 PostgreSQL Windows 初始化的中文路径编码问题。引擎来自 Maven Central 的 Zonky Windows PostgreSQL 17.11 运行时，并核对注册表发布的 SHA1；安装包和缓存不入库，不注册系统服务。

## 修改入口

- 全局字体、颜色、基础按钮：`frontend/src/styles/base.css`。
- 页面布局、密度、手机适配：`frontend/src/styles/workspace.css`。
- 顶部导航：`frontend/src/App.tsx`。
- 登录/账号：`frontend/src/app/ServicePage.tsx`。
- 会话列表：`ConversationSidebar.tsx`；聊天和输入：`MessageThread.tsx` / `MessageComposer.tsx`；整体编排：`ConversationWorkspace.tsx`。
- 关联案例、任务/模式/草稿：`ConversationContext.tsx` / `CollaborationPanel.tsx`。
- 动态服务卡片：`UIDocumentRenderer.tsx`，只能渲染后端授权的 Catalog 组件与动作。
- 案例、图片、模拟动作、核验和回访：`frontend/src/features/cases/`。
- 设备与事实审核：`frontend/src/features/devices/`。

每个模块真实对应的请求方法、完整路径、Client 方法及后端处理函数见 [UI 与后端接口对照](ui-backend-map.md)，43 条组件到 Client 的引用均核对了实际 OpenAPI 和路由。搜索/筛选、草稿、移动面板切换等纯前端逻辑单独列出。

## 提交前必须补齐或明确的内容

| 优先级 | 缺口 | 可验收结果 |
|---|---|---|
| P0 | `adb4610` Agent Harness 升级后 CI 后端 197 通过、5 失败 | 修复记忆连续性、旧租约与协作模式执行回归；重新得到全量 CI 通过，不能用上一版全绿替代 |
| P0 | Case 创建及会话/设备关联有后端 API，但当前前端没有完整创建/关联入口，演示资料依赖提前通过 API 准备 | 用户/客服从页面完成新案例与关联，或明确限制演示范围并提供可复现播种说明；完整产品应补页面入口 |
| P0 | 当前机器没有真实模型配置，真实 AI 不能演示；上游只有部分真实模型观察，Harness 又已改动 | 在明确选择的 Provider 上复验多轮排查、人工接管、草稿审阅、异常与恢复；密钥只放本地环境，不能进入前端 |
| P1 | 各功能已有实现，尚需统一用户流程与 UI，验证新手能否知道下一步 | 逐页改版后走通“报障→证据→人工协作→模拟动作→客户核验→事实归档/回访”；成功、拒绝、失败和未知结果均能解释 |
| P1 | 提交包尚未在本任务核对赛事格式 | 按官方要求准备 README/运行说明、架构与接口说明、演示账号/脚本、截图及视频或演示稿；明确 MOCK、模型和图片检查边界 |

图片目前只有本地结构检查，未实现完整恶意内容扫描、多模态理解；回访同意撤回、改期/取消也尚未实现。若提交材料承诺这些能力，必须实现并验收，否则如实列为范围限制。真实售后接口未接入，不能把模拟回执宣传为真实办理结果。

生产身份、真实 S3/HTTPS/云部署和真实 Anker 接口仍待后续工作。如果赛制只要求本地可演示作品，这些不必一概作为本轮 UI 迭代的前置条件，但不得宣称已经上线。

## 本轮实际检查

- 最新依赖恢复成功；前端 `check:api`、`typecheck`、`build` 通过。
- 数据库全新迁移到 `0013`，开发身份初始化成功。
- API health、readiness 和 Vite 页面均返回 200；readiness 如实显示 `production_ready=false`、`provider=not_configured`。
- 通过真实 API 创建合成资料，实际模拟动作 Worker 返回成功回执，经客户确认后案例进入已解决；归档事实可通过授权设备接口读取。
- 四个非模型 Worker 的心跳命令退出码均为 0。
- 本轮没有修改产品源码、修复上游五项失败或重新声称全量测试通过；本轮用途是可持续修改的真实 UI 预览与接口说明。
