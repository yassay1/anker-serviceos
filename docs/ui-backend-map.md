# UI 模块与真实后端接口对照

日期：2026-10-15。后端基线：`adb4610`；UI 分支 `codex/reference-ui-rebuild`。按前端实际导入的 Client 调用和当前 FastAPI 路由生成；不包含 planned 接口。所有接口完整路径均列出 `/api/v1` 前缀。

开发地址：http://127.0.0.1:5173/support；API 文档：http://127.0.0.1:8000/docs。Vite 将 `/api` 代理到 8000，修改 `frontend/src` 后自动热更新。

## 参考图重构后的页面入口

| 页面模块 | 真实请求 | 展示与限制 |
|---|---|---|
| 客户首页 `/` · `CustomerHome.tsx` | `GET /api/v1/cases`、`GET /api/v1/devices` | 我的服务、设备档案。没有设备照片接口时使用中性图标，不把装饰横幅当成实际设备图片。 |
| 首页开始诊断 | `POST /api/v1/conversations`，原 Client 请求体 `{}` | 为新问题建立独立会话；问题通过 Router state 进入原消息草稿，确认发送后才调用原消息接口。不复用可能关联旧问题的活跃会话。 |
| 客服总览 `/desk?view=overview` · `DeskOverview.tsx` | `GET /api/v1/cases`、`GET /api/v1/conversations`、`GET /api/v1/devices` | 仅统计已加载且授权可见的记录，不伪造全站总数、响应时间、满意度或 AI 解决率。筛选与搜索在已加载案例上执行。 |
| 客服会话顶部关联信息 | 原 `GET /api/v1/conversations/{id}/case-summaries` | 仅存在一个关联案例时使用其真实标题、状态、版本及设备 ID；多案例时保留通用会话标题和右侧完整案例列表，不假设会话与案例一一对应。 |
| 案例详情三列 `/cases/:id` | 原 `GET /api/v1/cases/{id}` 及下表的证据、动作、核验、回访请求 | 提交时间和当前状态来自案例，不由截图推断“AI 已诊断”“已安排维修”等进度。保留所有原写入入口、权限与原编号重试逻辑。 |

## 现有功能与 Client 对照

| 页面模块 / 前端源码 | Client 方法 | HTTP 请求 | 后端处理文件与函数 |
|---|---|---|---|
| 登录与身份<br>[ServicePage.tsx](../frontend/src/app/ServicePage.tsx) | [readActor](../frontend/src/api/client.ts#L48) | `GET /api/v1/auth/me` | [backend/serviceos_api/api/business.py:33](../backend/serviceos_api/api/business.py#L33)<br>`me` |
| 登录与身份<br>[ServicePage.tsx](../frontend/src/app/ServicePage.tsx) | [loginLocal](../frontend/src/api/client.ts#L54) | `POST /api/v1/local-auth/login` | [backend/serviceos_api/api/business.py:25](../backend/serviceos_api/api/business.py#L25)<br>`login` |
| 登录与身份<br>[ServicePage.tsx](../frontend/src/app/ServicePage.tsx) | [logout](../frontend/src/api/client.ts#L61) | `POST /api/v1/auth/logout` | [backend/serviceos_api/api/business.py:39](../backend/serviceos_api/api/business.py#L39)<br>`logout` |
| 服务连接状态<br>[ConnectionStatus.tsx](../frontend/src/shared/ConnectionStatus.tsx) | [readHealth](../frontend/src/api/client.ts#L41) | `GET /api/v1/health` | [backend/serviceos_api/api/health.py:33](../backend/serviceos_api/api/health.py#L33)<br>`read_health` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [listConversations](../frontend/src/api/client.ts#L66) | `GET /api/v1/conversations` | [backend/serviceos_api/api/business.py:52](../backend/serviceos_api/api/business.py#L52)<br>`list_conversations` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [createConversation](../frontend/src/api/client.ts#L71) | `POST /api/v1/conversations` | [backend/serviceos_api/api/business.py:47](../backend/serviceos_api/api/business.py#L47)<br>`create_conversation` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [listMessages](../frontend/src/api/client.ts#L76) | `GET /api/v1/conversations/{id}/messages` | [backend/serviceos_api/api/business.py:68](../backend/serviceos_api/api/business.py#L68)<br>`list_messages` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [listDeskCaseSummaries](../frontend/src/api/client.ts#L83) | `GET /api/v1/conversations/{id}/case-summaries` | [backend/serviceos_api/api/business.py:74](../backend/serviceos_api/api/business.py#L74)<br>`list_desk_case_summaries` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [readUIDocument](../frontend/src/api/client.ts#L132) | `GET /api/v1/conversations/{id}/ui-document` | [backend/serviceos_api/api/business.py:123](../backend/serviceos_api/api/business.py#L123)<br>`read_ui_document` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [refreshUIDocument](../frontend/src/api/client.ts#L139) | `POST /api/v1/conversations/{id}/ui-document/refresh` | [backend/serviceos_api/api/business.py:129](../backend/serviceos_api/api/business.py#L129)<br>`refresh_ui_document` |
| 会话列表/消息/案例摘要<br>[ConversationWorkspace.tsx](../frontend/src/features/conversation/ConversationWorkspace.tsx) | [sendMessage](../frontend/src/api/client.ts#L153) | `POST /api/v1/conversations/{id}/messages` | [backend/serviceos_api/api/business.py:63](../backend/serviceos_api/api/business.py#L63)<br>`send_message` |
| 关联案例资料<br>[ConversationContext.tsx](../frontend/src/features/conversation/ConversationContext.tsx) | [readCase](../frontend/src/api/client.ts#L219) | `GET /api/v1/cases/{id}` | [backend/serviceos_api/api/business.py:180](../backend/serviceos_api/api/business.py#L180)<br>`read_case` |
| 任务接管/模式/草稿审阅<br>[CollaborationPanel.tsx](../frontend/src/features/collaboration/CollaborationPanel.tsx) | [transitionMode](../frontend/src/api/client.ts#L90) | `POST /api/v1/conversations/{id}/mode-transitions` | [backend/serviceos_api/api/business.py:80](../backend/serviceos_api/api/business.py#L80)<br>`transition_mode` |
| 任务接管/模式/草稿审阅<br>[CollaborationPanel.tsx](../frontend/src/features/collaboration/CollaborationPanel.tsx) | [listTasks](../frontend/src/api/client.ts#L104) | `GET /api/v1/conversations/{id}/tasks` | [backend/serviceos_api/api/business.py:92](../backend/serviceos_api/api/business.py#L92)<br>`list_tasks` |
| 任务接管/模式/草稿审阅<br>[CollaborationPanel.tsx](../frontend/src/features/collaboration/CollaborationPanel.tsx) | [claimTask](../frontend/src/api/client.ts#L111) | `POST /api/v1/tasks/{id}/claim` | [backend/serviceos_api/api/business.py:98](../backend/serviceos_api/api/business.py#L98)<br>`claim_task` |
| 任务接管/模式/草稿审阅<br>[CollaborationPanel.tsx](../frontend/src/features/collaboration/CollaborationPanel.tsx) | [listProposals](../frontend/src/api/client.ts#L118) | `GET /api/v1/conversations/{id}/proposals` | [backend/serviceos_api/api/business.py:104](../backend/serviceos_api/api/business.py#L104)<br>`list_proposals` |
| 任务接管/模式/草稿审阅<br>[CollaborationPanel.tsx](../frontend/src/features/collaboration/CollaborationPanel.tsx) | [decideProposal](../frontend/src/api/client.ts#L125) | `POST /api/v1/proposals/{id}/decision` | [backend/serviceos_api/api/business.py:110](../backend/serviceos_api/api/business.py#L110)<br>`decide_proposal` |
| 受控交互卡/人工协助/选择回复<br>[UIDocumentRenderer.tsx](../frontend/src/features/ui-document/UIDocumentRenderer.tsx) | [invokeUIAction](../frontend/src/api/client.ts#L146) | `POST /api/v1/conversations/{id}/ui-actions` | [backend/serviceos_api/api/business.py:135](../backend/serviceos_api/api/business.py#L135)<br>`invoke_ui_action` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [listCases](../frontend/src/api/client.ts#L214) | `GET /api/v1/cases` | [backend/serviceos_api/api/business.py:175](../backend/serviceos_api/api/business.py#L175)<br>`list_cases` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [readCase](../frontend/src/api/client.ts#L219) | `GET /api/v1/cases/{id}` | [backend/serviceos_api/api/business.py:180](../backend/serviceos_api/api/business.py#L180)<br>`read_case` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [listCaseActions](../frontend/src/api/client.ts#L309) | `GET /api/v1/cases/{id}/actions` | [backend/serviceos_api/api/actions.py:38](../backend/serviceos_api/api/actions.py#L38)<br>`list_case_actions` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [requestMockAction](../frontend/src/api/client.ts#L314) | `POST /api/v1/cases/{id}/action-requests` | [backend/serviceos_api/api/actions.py:32](../backend/serviceos_api/api/actions.py#L32)<br>`request_mock_case_action` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [listActionApprovals](../frontend/src/api/client.ts#L321) | `GET /api/v1/cases/{id}/approvals` | [backend/serviceos_api/api/actions.py:50](../backend/serviceos_api/api/actions.py#L50)<br>`list_case_action_approvals` |
| 案例/模拟售后/审批<br>[CasesWorkspace.tsx](../frontend/src/features/cases/CasesWorkspace.tsx) | [decideActionApproval](../frontend/src/api/client.ts#L326) | `POST /api/v1/approvals/{id}/decisions` | [backend/serviceos_api/api/actions.py:58](../backend/serviceos_api/api/actions.py#L58)<br>`decide_action_approval` |
| 图片证据<br>[CaseEvidencePanel.tsx](../frontend/src/features/cases/CaseEvidencePanel.tsx) | [listCaseEvidence](../frontend/src/api/client.ts#L276) | `GET /api/v1/cases/{id}/evidence` | [backend/serviceos_api/api/evidence.py:46](../backend/serviceos_api/api/evidence.py#L46)<br>`list_case_evidence` |
| 图片证据<br>[CaseEvidencePanel.tsx](../frontend/src/features/cases/CaseEvidencePanel.tsx) | [uploadCaseEvidence](../frontend/src/api/client.ts#L283) | `POST /api/v1/cases/{id}/evidence` | [backend/serviceos_api/api/evidence.py:53](../backend/serviceos_api/api/evidence.py#L53)<br>`upload_case_evidence` |
| 图片证据<br>[CaseEvidencePanel.tsx](../frontend/src/features/cases/CaseEvidencePanel.tsx) | [readCaseEvidenceImage](../frontend/src/api/client.ts#L301) | `GET /api/v1/cases/{id}/evidence/{evidence_id}/content` | [backend/serviceos_api/api/evidence.py:84](../backend/serviceos_api/api/evidence.py#L84)<br>`read_case_evidence_content` |
| 客户结果核验<br>[VerificationPanel.tsx](../frontend/src/features/cases/VerificationPanel.tsx) | [readResolutionContract](../frontend/src/api/client.ts#L224) | `GET /api/v1/cases/{id}/resolution-contract` | [backend/serviceos_api/api/verification.py:30](../backend/serviceos_api/api/verification.py#L30)<br>`read_case_resolution_contract` |
| 客户结果核验<br>[VerificationPanel.tsx](../frontend/src/features/cases/VerificationPanel.tsx) | [listCaseVerifications](../frontend/src/api/client.ts#L231) | `GET /api/v1/cases/{id}/verifications` | [backend/serviceos_api/api/verification.py:36](../backend/serviceos_api/api/verification.py#L36)<br>`list_case_verifications` |
| 客户结果核验<br>[VerificationPanel.tsx](../frontend/src/features/cases/VerificationPanel.tsx) | [recordCaseVerification](../frontend/src/api/client.ts#L238) | `POST /api/v1/cases/{id}/verifications` | [backend/serviceos_api/api/verification.py:45](../backend/serviceos_api/api/verification.py#L45)<br>`record_case_verification` |
| 客户结果核验<br>[VerificationPanel.tsx](../frontend/src/features/cases/VerificationPanel.tsx) | [listCaseActions](../frontend/src/api/client.ts#L309) | `GET /api/v1/cases/{id}/actions` | [backend/serviceos_api/api/actions.py:38](../backend/serviceos_api/api/actions.py#L38)<br>`list_case_actions` |
| 回访同意与预约<br>[FollowUpPanel.tsx](../frontend/src/features/cases/FollowUpPanel.tsx) | [listFollowUpConsents](../frontend/src/api/client.ts#L246) | `GET /api/v1/cases/{id}/follow-up-consents` | [backend/serviceos_api/api/followups.py:30](../backend/serviceos_api/api/followups.py#L30)<br>`list_consents` |
| 回访同意与预约<br>[FollowUpPanel.tsx](../frontend/src/features/cases/FollowUpPanel.tsx) | [recordFollowUpConsent](../frontend/src/api/client.ts#L253) | `POST /api/v1/cases/{id}/follow-up-consents` | [backend/serviceos_api/api/followups.py:36](../backend/serviceos_api/api/followups.py#L36)<br>`consent` |
| 回访同意与预约<br>[FollowUpPanel.tsx](../frontend/src/features/cases/FollowUpPanel.tsx) | [listFollowUps](../frontend/src/api/client.ts#L261) | `GET /api/v1/cases/{id}/follow-ups` | [backend/serviceos_api/api/followups.py:42](../backend/serviceos_api/api/followups.py#L42)<br>`list_jobs` |
| 回访同意与预约<br>[FollowUpPanel.tsx](../frontend/src/features/cases/FollowUpPanel.tsx) | [scheduleFollowUp](../frontend/src/api/client.ts#L268) | `POST /api/v1/cases/{id}/follow-ups` | [backend/serviceos_api/api/followups.py:48](../backend/serviceos_api/api/followups.py#L48)<br>`schedule` |
| 设备档案/历史<br>[DevicesWorkspace.tsx](../frontend/src/features/devices/DevicesWorkspace.tsx) | [listDevices](../frontend/src/api/client.ts#L160) | `GET /api/v1/devices` | [backend/serviceos_api/api/business.py:216](../backend/serviceos_api/api/business.py#L216)<br>`list_devices` |
| 设备档案/历史<br>[DevicesWorkspace.tsx](../frontend/src/features/devices/DevicesWorkspace.tsx) | [readDevice](../frontend/src/api/client.ts#L165) | `GET /api/v1/devices/{id}` | [backend/serviceos_api/api/business.py:221](../backend/serviceos_api/api/business.py#L221)<br>`read_device` |
| 设备档案/历史<br>[DevicesWorkspace.tsx](../frontend/src/features/devices/DevicesWorkspace.tsx) | [listDeviceCases](../frontend/src/api/client.ts#L170) | `GET /api/v1/devices/{id}/cases` | [backend/serviceos_api/api/business.py:237](../backend/serviceos_api/api/business.py#L237)<br>`device_cases` |
| 设备事实候选/核验/归档/撤销<br>[CaseFactPanel.tsx](../frontend/src/features/devices/CaseFactPanel.tsx) | [listCaseFactReview](../frontend/src/api/client.ts#L175) | `GET /api/v1/devices/{id}/fact-review` | [backend/serviceos_api/api/business.py:253](../backend/serviceos_api/api/business.py#L253)<br>`list_case_fact_review` |
| 设备事实候选/核验/归档/撤销<br>[CaseFactPanel.tsx](../frontend/src/features/devices/CaseFactPanel.tsx) | [createCandidateFact](../frontend/src/api/client.ts#L182) | `POST /api/v1/devices/{id}/facts` | [backend/serviceos_api/api/business.py:242](../backend/serviceos_api/api/business.py#L242)<br>`create_candidate_fact` |
| 设备事实候选/核验/归档/撤销<br>[CaseFactPanel.tsx](../frontend/src/features/devices/CaseFactPanel.tsx) | [verifyFact](../frontend/src/api/client.ts#L190) | `POST /api/v1/devices/{id}/facts/{fact_id}/verify` | [backend/serviceos_api/api/business.py:258](../backend/serviceos_api/api/business.py#L258)<br>`verify_fact` |
| 设备事实候选/核验/归档/撤销<br>[CaseFactPanel.tsx](../frontend/src/features/devices/CaseFactPanel.tsx) | [archiveCaseFact](../frontend/src/api/client.ts#L198) | `POST /api/v1/cases/{case_id}/devices/{device_id}/facts/{fact_id}/archive` | [backend/serviceos_api/api/business.py:269](../backend/serviceos_api/api/business.py#L269)<br>`archive_case_device_fact` |
| 设备事实候选/核验/归档/撤销<br>[CaseFactPanel.tsx](../frontend/src/features/devices/CaseFactPanel.tsx) | [retractFact](../frontend/src/api/client.ts#L206) | `POST /api/v1/devices/{id}/facts/{fact_id}/retract` | [backend/serviceos_api/api/business.py:263](../backend/serviceos_api/api/business.py#L263)<br>`retract_fact` |

## 实时更新与后台工作

- SSE：`GET /api/v1/conversations/{id}/events?after={sequence}`，由 `useConversationEvents.ts` 订阅；同时使用 `GET /api/v1/conversations/{id}/event-history` 补取持久事件。消息/协作快照有轮询兜底。
- AI 回复：浏览器提交消息；Message Worker 异步处理，再经消息与事件接口返回。浏览器不直接请求模型厂商，不持有模型密钥。
- 图片检查、模拟动作执行、到期回访和 Outbox 发布各有独立 Worker；按钮收到受理/审批回执不等于执行完成。

## 纯前端逻辑

已加载会话搜索/筛选、手机面板切换、输入草稿、内部备注选择、请求恢复记录、滚动定位、状态中文名和视觉样式属于前端逻辑，没有独立业务接口。状态切换或提交仍通过上表真实 API。

## 体验边界

账号是本地开发身份；展示数据会明确标识为合成演示资料。模拟售后回执保持 MOCK 标识。未配置模型时，消息可持久保存、人工可回复，但不能展示虚构 AI 回复或进度。
