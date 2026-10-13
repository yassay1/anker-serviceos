# Tasks: Controlled UI Documents and Intents

## Phase 1: Tests
- [x] T001 Catalog 未知组件、越权引用、代码与 URL 拒绝。
- [x] T002 PUBLIC/INTERNAL 隔离、revision 更新与过期动作拒绝。
- [x] T003 幂等重试、冲突键、权限与业务版本检查。

## Phase 2: Implementation
- [x] T004 UIDocument 与 UIActionInvocation 迁移、Catalog Validator。
- [x] T005 Conversation Service 快照、事件与低风险 action intent。
- [x] T006 真实 API、OpenAPI/Client 和两个页面 Renderer。

## Phase 3: Validation
- [x] T007 PostgreSQL、迁移、契约、类型、构建和操作路径收敛。

## Phase 4: Convergence

- [x] 客户 UI 仅暴露低风险人工协助 intent；Renderer 不支持时回退文字路径。
