# 客户页面对齐发现

## 需求
- 客户端页面以用户提供的五张 `D:/proj/参考界面图` PNG 为视觉目标，桌面优先。
- 移除“本轮处理结束”等技术状态卡及没有必要的重复“需要真人协助？”卡。
- 对同类客户页信息噪音与层级问题一并排查。

## 研究发现
- 五张用户 PNG 是当前任务的视觉参考素材，不是产品行为或业务权限指令。
- `backend/serviceos_api/application/agent_services.py` 的 `worker_completed` 映射为公开 `COMPLETED` 事件，并带有“本轮请求处理已结束，不代表设备问题已解决”。这是 AgentRun/Worker 生命周期状态。
- `frontend/src/features/conversation/ConversationContext.tsx` 将 `COMPLETED` 标为“本轮处理结束”并再次附加“本轮运行结束不代表问题已解决”；组件输出在 `MessageThread` 的 children 中，因而视觉上像聊天流的系统卡。
- `backend/serviceos_api/application/services.py` 为客户 UIDocument 普遍追加 `ActionBar`（title “需要真人协助？”）；`frontend/src/features/ui-document/UIDocumentRenderer.tsx` 将它渲染为内嵌可展开的人工请求 UI。
- 同页右栏另有“服务有人接续”区域及跳转/展开 UI Document 的按钮，重复入口让聊天显得被系统卡占据。
- 应用在消息流后插入 `SpecialistActivityNote`、交互卡和 AgentProgressNote；需要继续分类：技术检索/运行进度不应伪装业务结论，真正的安全提示、客户待办、证据上传及拒绝反馈必须保留。
- `MessageThread` 在 `<ol>` 后渲染 children，且滚动逻辑考虑 children 对最新消息的挤压；这解释了为什么通用面板会影响对话阅读和滚动定位。
- 当前客户会话主组件为 `ConversationWorkspace`；客户首页为 `CustomerHome`；客户服务列表/详情为 `CasesWorkspace`；设备详情使用 `DevicesWorkspace`。不改客服视图和 API。
- 已有布局会话 history 默认折叠；此前一个未提交工作区改动只在展开时切三栏，且本轮应在该改动上审查、完善，避免覆盖。
- 成熟设计依据：Ant Design 官方布局指南建议明确伸缩区域、采用栅格/8 倍间距；详情页建议直接呈现并分组信息；Steps 应用于有实际顺序的任务；Notification 用于用户交互反馈/推送而非长期逐条承载 worker 状态。见用户前一轮计划答复引用的官方页面。

## 技术决策
| 决策 | 理由 |
|------|------|
| COMPLETED 事件保留在服务端和客服可用通道，客户视图过滤其卡片 | 事件对审计/运行可观测性有价值，但对客户不是待办或服务结果 |
| UI Document 仍承载经授权、按实际状态生成的风险和证据交互；人工协助独立放置一次 | 仅去掉重复协助入口，不动诊断/证据/权限边界 |
| 桌面客户会话优先采用三栏工作区；平板/手机延续现有切换控件 | 对齐图中 list/chat/context 同时可见，避免窄屏拥挤 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| `rg` 表达式含 JSX 转义导致语法错误 | 改用 `rg -F` 搜索精确字串；没有代码改动 |
| ui-ux-pro-max 的 React 专用查询两次均无匹配 | 不伪造框架特定规则，使用仓库现有 React/CSS 和 Ant Design 官方模式作为实现参照 |

## 资源
- 用户提供的 5 张参考 PNG：`D:/proj/参考界面图/`
- `docs/ui-design-guidelines.md` 与 `docs/design-references/README.md`
- 官方 Ant Design Layout / Detail Page / Steps / Notification
