# 全面逻辑检查与修复记录

日期：2026-10-14。工程：`yassay1/anker-serviceos`，基线 `87f4885`。检查活动前端、真实 API、认证/权限、业务服务、Worker 上下文、消息与事件、设备历史、协作状态和测试；未修改项目外归档。

## 修复内容

| 问题 | 修复与回归 |
|---|---|
| 后端从旧到新分页，前端停在首 50 条并标成“更早消息” | 按真实 cursor 顺序读取到末页；失败暂停自动读取、保留重试；115 条消息回归检查最新回复和滚动位置。阅读历史时不强行跳到底部 |
| 身份更新后沿用上一位客服草稿 | 按 tenant/actor/kind 重建工作区；草稿、内部选择及乐观消息隔离；身份切换回归，设备页无重复 React key |
| UI 修订更换丢失未知结果请求，409 后又重试旧版本 | 不按 revision 重建；未知结果保留原请求，明确 4xx 拒绝后允许用户提交最新请求；网络失败和 409 分别回归，无自动业务重放 |
| 切换会话、设备页或刷新丢失原请求；迟到旧回执清空新记录 | 同标签页内存/sessionStorage 保存原动作，按身份与会话隔离；只清理匹配 client_action_id 的记录；三种导航与延迟回执回归 |
| 两个人工协助按钮，其中一个绕过幂等入口 | 统一使用已有 `/ui-actions`，确认后展示真实回执；卡片不可用时提示文字沟通。单入口回归，Live 流程也验证真实 UI action |
| 归档会话仍显示可执行协作操作并定期发布新 UI | 禁用发送、切换、接管和审阅；归档 UI 使用只读 GET；归档控件回归 |
| Agent 处理早先消息时历史包含后来消息 | 限定历史在当前消息 `(created_at,id)` 之前；未修复代码的真实 PostgreSQL CI 得到 2 failed / 70 passed，分别复现不同时间及相同时间 ID 排序 |

后端仅修改 `application/agent_services.py` 历史查询及测试。不改路由、Schema、OpenAPI、生成类型、迁移或公开消息授权。

## 验证记录

- 前端 `npm run check:api`、`npm run typecheck`、`npm run build`；浏览器受控回归共 31 项，包含六组桌面/手机 axe A/AA 检查。最终结果以本轮终端与 CI 为准。
- 本机后端 `pytest backend/tests`：17 passed、55 skipped（本机没有 PostgreSQL）；真实 OpenAPI 与 V1 提案同步检查通过。跳过不能计作通过。
- CI 验证全部 72 项 PostgreSQL 后端测试、31 项受控浏览器回归和两条真实 API 浏览器流程。最终运行、成功/失败日志及截图见 [PR #3 checks](https://github.com/yassay1/anker-serviceos/pull/3/checks)，以实际记录为准。
- 新增回归均先复现问题，再检查修复。独立审阅发现的导航恢复记录丢失、旧回执覆盖新请求问题已修复，再审未发现新 Critical/Important 问题。未调用模型 Provider、部署或合并。

## 待维护者确认的边界

1. 后端允许主管设置 `CO_SERVICE + AI_AUTO`，但 Agent 发布和 UI 投影当前仍只对 `AI_LEAD + AI_AUTO` 自动公开。普通前端共同服务使用需人工审阅策略。本轮保留保守公开边界，未扩大 Agent 发言权限；维护者需统一发布、投影和读取规则后验收该授权分支。
2. 正式处理结果核验属于未实施的阶段 4。现有 Case 服务可由客服依据原因转为 RESOLVED，不能将此状态宣传为已完成正式核验。本轮未临时发明核验器或外部售后回执。
3. 恢复记录只针对同一标签页。禁用 sessionStorage 时内存仍支持 SPA 切换，完全刷新不保证恢复；关闭标签页、换浏览器或设备不共享记录。只保存原动作和原因，不含 Cookie 或密钥。重试始终由用户触发并经后端鉴权与幂等校验。
4. 现有消息 API 前向分页，长会话需依次读历史，轮询重新读取已加载页。大量历史的优化需要后端提供最新消息/向后分页契约，不在前端臆造接口。
5. 真实模型多轮、SSE 强制断线/序号补取、生产身份、阶段 4 外部动作仍未验收。

## 影响文件与保存

前端：ServicePage、conversation 工作区/线程、CollaborationPanel、UIDocumentRenderer、actionRecovery、workspace fixtures/spec、logic-audit spec、Live 服务流程。后端：AgentContextBuilder 及 worker 测试。文档：README 和本记录。

保存到现有私有分支与草稿 PR；主分支及公开演示仓库不改。系统收尾在代码保存与验证后执行，不将发出关机命令称为已完成关机。
