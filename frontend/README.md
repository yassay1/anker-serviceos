# Web 前端开发指南

本目录是售后通的单一 React + TypeScript + Vite 应用。客户视图和客服视图共用应用与 API Client；产品范围见[产品定义](../docs/product-definition.md)，整体启动顺序见[仓库 README](../README.md)。

## 本地运行

在仓库根目录先按整体启动说明准备 PostgreSQL、迁移、开发身份和 API，然后另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

Vite 在 `http://127.0.0.1:5173` 启动，`/support` 是客户入口，`/desk` 是客服入口；`/api` 代理到 `http://127.0.0.1:8000`。预览构建使用 4173。实际端口和代理以 [`vite.config.ts`](vite.config.ts) 为准。前端独立启动只会显示连接状态；需要业务数据时仍须启动 API 和数据库。

## 代码入口与数据流

| 位置 | 职责 |
|---|---|
| `src/main.tsx` | React、Router、TanStack Query 初始化 |
| `src/App.tsx` | 当前客户与客服页面、会话和消息交互 |
| `src/UIDocumentRenderer.tsx` | 工作区中的受控 UI 文档渲染实现；验收状态以开发计划为准 |
| `src/styles.css` | 当前全局视觉样式和响应式规则 |
| `src/api/client.ts` | 类型化请求封装与错误处理 |
| `src/api/schema.d.ts` | 从仓库根目录的 `contracts/openapi.json` 生成的类型 |

页面显示服务器保存的消息和授权可见数据。Case、Device、Conversation 是不同对象；界面不能根据 Agent 文案推断业务已完成，也不能将内部备注显示给客户。工作区可能包含未提交的阶段 3 功能；[开发计划](../docs/development-plan.md)和对应验收记录决定已交付范围，代码存在本身不代表已验收。

## API 契约变更

前端调用以真实 FastAPI 路由和生成类型为准。需要新接口时，按[协作开发指南](../docs/contributing.md)先与后端约定请求、响应、错误、权限和版本；后端实现并导出 OpenAPI 后，在仓库根目录与本目录依次执行：

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
```

这些命令检查 API 类型同步、TypeScript 和生产构建；业务流程、权限隔离与移动端交互仍须按受影响功能实际验收。

## 视觉设计入口

五张 Web 图在[设计参考目录](../docs/design-references/README.md)；[界面设计指南](../docs/ui-design-guidelines.md)将图片拆成可实现的样式、页面和状态要求。截图是视觉参考，截图中的设备、数字、诊断和服务进度不是业务数据。
