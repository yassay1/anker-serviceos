# 售后通

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

客户描述硬件问题并持续查看服务记录；客服在同一会话阅读案例、回复、内部备注和协作事项。依据用户已确认的四份 V1 基线及现有工程。

## Product Purpose

让客户、真人与受控 Agent 围绕持续服务问题协作；设备、案例、会话独立，以授权业务记录为准。

## Capabilities and Constraints

当前后端已提供会话、持久消息、人工任务、发言策略、内部草稿、受控交互卡、设备与案例读取。真实模型、生产身份、部署及阶段 4 的附件/外部动作/结果核验仍待实现或验收。前端仅调用当前 `contracts/openapi.json`，不把计划接口接入活动 Client。

## Brand Commitments

名称“售后通”，品牌蓝、深色文字、白色工作表面；客户侧暖色、低密度，客服侧提高信息密度。参考 `docs/ui-design-guidelines.md` 与五张参考图。用户已授权自由发挥展示体验，并确认在朋友现有工程上继续。

## Evidence on Hand

四份 V1 文档、实际 API、受控浏览器回归及 CI PostgreSQL 测试。截图中的样例设备、姓名、统计和诊断不能作为业务数据。

## Product Principles

- 只呈现当前身份授权的真实记录。
- 公开消息与内部资料严格分开。
- 成功、拒绝和未知结果明确区分。
- 后端版本、权限及幂等规则保持权威。
- 界面增强不阻断文字服务路径。
