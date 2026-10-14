# 售后 SOP 与验收矩阵

本流程以当前应用服务和授权状态为准。Conversation 管沟通，Case 管一次问题，Device Passport 仅存经核验的设备事实，AgentRun 是执行尝试，Task/Action 是待办与受控操作。Case 可关联多个会话/设备，设备未知时不创建虚假身份。

## 标准服务链路

| 环节 | 必需信息及推进条件 | Tool / UI / 状态 | 失败或退出 |
|---|---|---|---|
| 咨询受理 | 客户真实消息、服务器202持久回执 | 聊天、消息编号；异步Job/Outbox | 重试复用client_message_id，不重建售后动作；数据库失败说明未受理 |
| 建立/匹配Case | 客户选择已有事项或明确新问题，同一客户的会话关联 | Case列表/详情、当前状态；多事项须显式选择 | 不因一段对话自动合并多Case，信息不够先追问 |
| 产品识别 | 用户型号陈述、相关设备或标签；未核验明确标识 | 型号询问、证据入口；Device保持UNVERIFIED | 型号不明不可编造规格；必要时只建Case |
| 风险筛查 | 是否鼓包、冒烟、焦味、过热或破损 | 固定安全提醒优先；建议停止测试并人工协助 | 不指导拆解/短接或危险充电；转人工不等于解决 |
| 检索/诊断 | 适用的已授权手册与用户描述，来源可追溯 | lookup_manual / 可用Skill；真实检索进度 | 无适用资料明确无法判断，不将假设写事实 |
| 补充证据 | 一次只追问高价值信息；说明用途与可选性 | 图片经真实上传→PENDING→CLEAN/REJECTED；文本始终可继续 | CLEAN仅本地结构检查，不等于病毒扫描/视觉理解；未知上传编号先查询对账 |
| 提供方案 | 安全可逆步骤、依据、成功标准和停止条件 | 受控Question/Step卡或文本；输入经后端校验 | 未知组件/旧卡降级，不能用步骤完成代替解决 |
| 人工协作 | 客户请求或能力/风险边界，已有上下文供客服阅读 | 人工任务、claim、AI_LEAD/CO_SERVICE/HUMAN_LEAD | 最新后端发言策略控制外发；旧Agent不偷发，内部资料不公开 |
| 提出动作 | Case未解决、理由明确、版本有效 | 仅MOCK_SERVICE_REQUEST；明确模拟标签 | 未接真实Anker；不承诺真实退款/维修；情绪不能授权动作 |
| 审批/执行 | 另一名SUPERVISOR/ADMIN审批，不可自批 | WAITING_APPROVAL→APPROVED→EXECUTING→回执 | 拒绝禁止执行；同key同内容复用、不同内容409 |
| UNKNOWN对账 | 未能确认外部执行结果，保留操作身份 | 独立Worker仅查询回执，租约防抢占 | 不盲重试执行；持续未知保持未解决并可人工处理 |
| 结果核验 | 冻结条件：成功模拟回执＋客户明确确认，且无未结动作 | 客户WORKING/NOT_WORKING/UNSURE，经服务端核验 | 失败/UNKNOWN/未确认不能解决；NOT_WORKING继续服务 |
| 可信事实归档 | 已关联设备、候选事实有来源、客服核验、来源Case已解决 | 独立事实归档，客户/Agent只读已归档可信事实 | 不归档整个Case/情绪/模型推测；撤销后不再展示 |
| 后续跟进 | 客户本人同意、目的匹配、有效未来时间 | 客服预约；到期只创建内部任务 | 不自动向客户发消息；撤回/改期/取消仍需后续切片 |
| 关闭或继续 | 核验通过后才能解决，已解决后关闭；重开留痕 | Case状态与版本、审计事件 | UI显示成功不决定状态；历史核验不得覆盖 |

## Skill 与情绪边界

Skill是可发现、版本化的方法契约：适用条件、输入/输出、所需工具、风险、失败出口及执行审计。Tool是调用应用服务的入口；Rule确定授权和前置条件；create_agent只在过滤后的能力中选择。Context Builder只提供有权且相关的数据，人工备注与无关历史不进入客户公开输出。

加载Skill仅记录LOADED，不表示已完成。情绪识别本轮准备结构化契约（类别、强度、置信度、不确定性、消息依据、服务策略），未接入新模型；不得虚构识别结果。未来只辅助语气、简洁解释、人工关注建议，不能直接退款、换货、关单、改变权限或跳过审批。

## 测试矩阵

| 场景 | 预期 | 自动化入口 | 浏览器验收 |
|---|---|---|---|
| 正常模拟动作闭环 | 审批/Worker/回执/核验逐步真实保存 | backend/tests/test_mock_service_actions.py | frontend/tests-live/service-flow.spec.ts |
| 信息不足/无法判断 | 有来源、可追问/求助，不造事实 | test_agent_result.py、test_worker_runtime.py | 真实Provider多轮待配置 |
| 图片与失败清理 | PENDING禁下载、授权CLEAN预览、REJECTED清理可重试 | test_case_image_evidence.py、test_image_safety.py | live图片上传+跨用户拒绝 |
| 接管及内部隔离 | 最新策略生效，客户不见内部备注 | test_worker_runtime.py、test_business_api.py | live客服接管及PUBLIC/INTERNAL |
| 拒绝/失败/UNKNOWN | 无重复执行、未知只对账 | test_mock_service_actions.py、test_phase4_recovery.py（如存在） | 对应分支单独记录，不以成功路径替代 |
| 刷新/断线/重复/旧卡 | 单调游标、持久快照、幂等恢复 | frontend/tests/、test_worker_runtime.py | 断网/重连及页面刷新 |
| 多用户/租户/多Case | 资源所有权明确，越权404/403 | test_database.py、test_business_api.py | 切换会话及身份回归 |
| 跟进与事实归档 | 同意与授权有效、来源核验和撤销生效 | test_followups.py、test_case_fact_archive.py | live跟进/归档；到期任务另测 |
| 交付与故障恢复 | 配置缺失fail closed，持久卷重启保留 | test_readiness.py、test_operations.py | Compose启动/重启/恢复演练 |

性能记录请求数、错误率、P50/P95及样本来源；真实模型未配置时模型首token、质量与恢复必须标为未测。部署准备、业务闭环、UI体验和真实Provider分别验收；实际命令及结果见phase5-validation.md。
