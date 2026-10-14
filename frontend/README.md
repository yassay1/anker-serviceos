# Web 前端开发指南

本目录是售后通的单一 React + TypeScript + Vite 应用。客户视图和客服视图共用应用与 API Client；产品范围见[产品定义](../docs/product-definition.md)，整体启动顺序见[仓库 README](../README.md)。

## 本地运行

在仓库根目录先按整体启动说明准备 PostgreSQL、迁移、开发身份和 API，然后另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

Vite 在 `http://127.0.0.1:5173` 启动，`/support` 是客户入口，`/desk` 是客服入口，`/cases` 查看案例与模拟动作；`/api` 代理到 `http://127.0.0.1:8000`。预览构建使用 4173。实际端口和代理以 [`vite.config.ts`](vite.config.ts) 为准。前端独立启动只会显示连接状态；需要业务数据时仍须启动 API 和数据库。

## 代码入口与数据流

| 位置 | 职责 |
|---|---|
| `src/main.tsx` | React、Router、TanStack Query 初始化 |
| `src/App.tsx`、`src/app/ServicePage.tsx` | 路由、身份校验与登录状态；失败时提供重试 |
| `src/app/queryKeys.ts` | 按身份、租户和会话划分查询缓存 |
| `src/features/conversation/` | 会话列表、消息收发、乐观状态与 SSE 断线补取 |
| `src/features/collaboration/` | 人工任务、策略切换与草稿审批 |
| `src/features/ui-document/` | 受控 UI 文档渲染与低风险 action intent |
| `src/features/devices/` | 设备档案、已核验事实、关联案例历史和客服事实归档流程 |
| `src/features/cases/` | 案例列表、图片证据上传与检查状态、授权预览、模拟动作请求、主管审批、真实 Mock 回执与客户结果核验；未知提交保留原编号 |
| `src/styles/base.css`、`src/styles/workspace.css` | 基础视觉样式和工作区响应式布局 |
| `src/api/client.ts` | 类型化请求封装与错误处理 |
| `src/api/schema.d.ts` | 从仓库根目录的 `contracts/openapi.json` 生成的类型 |

页面显示服务器保存的消息和授权可见数据。Case、Device、Conversation 是不同对象；界面不能根据 Agent 文案推断业务已完成，也不能将内部备注显示给客户。消息与协作状态由 SSE 事件触发即时刷新，同时每十秒校对服务器快照；消息在断线时每四秒查询。连接建立不代表独立事件调度器已经工作。UI 文档投影在首次打开、事件及快照校对时刷新，后端同签名复用当前 revision。前端本地浏览器复核范围与仍待验的分支见[阶段 3 验收记录](../docs/phase3-validation.md)。下一阶段的功能范围以[开发计划](../docs/development-plan.md)为准。

## API 契约变更

前端调用以真实 FastAPI 路由和生成类型为准。需要新接口时，先与后端按[V1 接口提案](../contracts/proposed/v1/README.md)、[协作开发指南](../docs/contributing.md)及[功能契约模板](../docs/templates/feature-contract.md)共同确认场景、请求、响应、错误、权限、版本和事件。提案中的 `planned` 操作不能调用；接口实现前可并行开发页面结构与状态，但提交操作保持待接入，不显示假成功。后端实现并导出 OpenAPI 后，在仓库根目录与本目录依次执行：

```powershell
uv run --project backend --locked python -m serviceos_api.export_openapi
cd frontend
npm run generate:api
npm run check:api
npm run typecheck
```

生成文件随接口变更一起提交。只在 V1 设计文档中出现、尚无真实路由的能力，不作为可成功提交的页面操作。

## 前端检查

在 `frontend/` 执行：

```powershell
npm run check:api
npm run typecheck
npm run build
npm run test:browser
```

首次执行浏览器回归前运行 `npm exec -- playwright install chromium`。本机已有 Chrome 时，可使用 `$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:browser`。测试自行启动独立的 5174 测试服务，不复用日常 5173 页面。

这些命令检查 API 类型同步、应用及测试的 TypeScript、生产构建和前端冲突恢复。浏览器回归在测试目录内拦截 HTTP，使用当前生成类型构造受控响应；不需要数据库，也不证明真实后端权限、并发或 SSE 恢复已通过。业务流程仍须在真实 API、PostgreSQL 与当前身份下实际验收。

`/desk` 的任务接管、策略切换及草稿审阅收到 HTTP 409 时，保留服务端拒绝原因并重新查询会话、任务、草稿与交互卡，移除已失效的操作。刷新不自动重新提交写请求，403 仍按拒绝展示。适配范围及证据见[前端对接验证](../docs/frontend-integration-validation.md)。

## 视觉设计入口

当前 `/support`、`/desk` 已在现有真实 Client 上适配新布局，手机可切换列表/会话/资料；客户侧标签为“资料与协助”。消息草稿及内部备注选择按会话保存，切换时不互相沿用。会话搜索与状态筛选仅作用于已加载记录。

`/devices` 与 `/devices/:id` 接入真实设备、关联案例和 Case 来源事实接口。客服可保存候选、核验事实，并在来源 Case 解决后归档或撤销；客户只看到可信档案事实。设备身份、已核验事实及案例状态分别展示；无权访问指定 ID 时不替换成另一条记录。

`npm run test:browser` 运行 31 个 HTTP 受控用例，包括六组桌面/手机 axe 检查。`npm run test:live` 使用本机真实 API 与 PostgreSQL；先按根 README 迁移并初始化回环 `serviceos_dev`，保持开发认证与数据库环境变量可被测试进程继承。Live 配置自行启动 API/Vite，拒绝复用已有服务，端口保持 8000/5173；只在隔离测试数据库中执行，不指向生产数据库。CI 在临时 PostgreSQL 中创建该开发库后运行两条真实浏览器路径。它们检查持久消息、人工接管、模式、公开/内部隔离、设备历史与跨客户/租户拒绝；不验证模型、外部 Anker 操作或 SSE 强制断线恢复。当前范围与证据见[完整适配记录](../docs/backend-based-frontend-validation.md)。

五张 Web 图在[设计参考目录](../docs/design-references/README.md)；[界面设计指南](../docs/ui-design-guidelines.md)将图片拆成可实现的样式、页面和状态要求。截图是视觉参考，截图中的设备、数字、诊断和服务进度不是业务数据。

## 逻辑恢复约定

消息 API 按旧到新分页，前端顺序读取到末页；失败停止自动翻页，保留手动重试。初次打开定位最新消息，阅读历史时不强行滚动。账号变化重建工作区，归档会话协作按钮禁用。

人工协助统一使用实际 UI action。未知结果的原请求按 tenant/actor/conversation 在同标签页内存与 sessionStorage 保存，切换会话、设备页和刷新仍可手动重试；回执仅清理匹配请求。明确 4xx 拒绝后允许重新提交新版本，不自动重放业务写入。完整范围和限制见[全面逻辑检查](../docs/comprehensive-logic-audit.md)。
