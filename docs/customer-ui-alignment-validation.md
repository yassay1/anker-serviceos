# 客户页面参考图对齐验收

日期：2026-10-17
范围：客户侧 `/support` 会话视图的桌面布局与客户可见信息层级。参考素材及逐图来源见[2026-10-17 客户服务界面参考图](design-references/2026-10-17-customer/README.md)。

## 目标与实现

- 将宽屏客户会话调整为会话历史、当前对话、服务资料三栏；桌面默认显示历史列表，创建新对话后仍保留列表。窄屏保留列表/对话/资料切换。
- 标题与唯一的新会话主入口收敛到页面级；移除列表中重复的新建入口。
- 客户聊天不再将 Agent/Worker 的 `RUNNING`、`LOOKUP`、`COMPLETED`、`WAITING_APPROVAL` 生命周期显示为系统消息卡。后台事件及客服可见进度没有因此删除。
- 客户侧保留有实际服务含义的安全提示、客户待办、证据上传、选项和失败反馈。
- 将真人协助收敛为服务资料区的单一入口；点击后显示补充说明和提交控件，继续使用现有 UI action、服务端授权、幂等标识及未知结果恢复流程。
- 不改变后端路由、数据库、API/OpenAPI、客服页面或 Case/Device/Conversation 业务状态语义；未把截图内的客户、设备、诊断、状态或时间转成业务数据。

## 变更文件

- `frontend/src/features/conversation/ConversationWorkspace.tsx`、`ConversationSidebar.tsx`：桌面优先历史栏、页面级操作、客户消息流过滤与面板状态。
- `frontend/src/features/ui-document/UIDocumentRenderer.tsx`：区分对话交互卡和资料侧栏协助入口，保留已有动作状态处理。
- `frontend/src/styles/product.css`：桌面三栏和窄屏布局、单一协助入口样式。
- `frontend/tests/delivery-readiness.spec.ts`、`logic-audit.spec.ts`、`workspace.spec.ts`：更新访问路径与客户可见状态断言，覆盖 1440px/1280px 桌面入口和重复卡片检查。
- `frontend/src/features/cases/CaseEvidencePanel.tsx`、`frontend/public/images/product-*-guide.png`、`docs/assets/product-*-guide*.md`：已有的通用设备拍照引导素材及来源说明；它们仅作拍摄示例，不是实际设备或客户证据。
- `DESIGN.md`、`docs/design-references/`、`docs/ui-design-guidelines.md`、`frontend/README.md`：补充成熟设计系统取舍、两组参考图来源、客户桌面布局规则和当前验收入口。

## 验收结果

以下结果来自本轮实现时保存的验证记录；本次提交打包仅做文档、原图和 Git 差异复核，没有重新运行这些检查。

| 检查 | 实现阶段记录 |
|---|---|
| `npm run check:api` | 通过 |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过 |
| `npm run test:browser` | 89 passed |
| 视口检查 | 1440×900、1280×800、390×844；包含桌面/移动切换与横向溢出检查 |

浏览器回归使用隔离 HTTP fixtures。运行时页面目视检查为只读，没有提交消息、协助请求或其他业务写操作；它不替代真实 API + PostgreSQL 流程验收。

## 未完成范围与风险

- 后端仍然记录真实 Worker/Agent 完成事件；本变更只控制客户视图，不影响客服内部运行观察与审计。
- Agent 作为正式公开消息保存的正文仍按现有授权原样显示；此改动不会按关键词删除或改写消息正文。
- 本轮不验证真实模型质量、真实 Anker 外部操作、人工客服的实际响应时间或跨进程 SSE 强制断线恢复。
- 原始参考截图是内部设计资料，不作为应用运行时资产；图片所示状态、内容与设备不可用于推导当前业务事实。
