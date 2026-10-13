<!--
Sync Impact Report
- Version: 1.0.0 → 2.0.0 (V1 replaces incompatible prototype state and Phase 0 rules)
- Modified principles: II Verified resolution; III Bounded action; IV Auditability; V Minimal capability architecture
- Added sections: none
- Removed sections: none
- Follow-up TODOs: none
-->
# Anker ServiceOS Constitution

## Core Principles

### I. 证据先于判断

任何诊断结论和下一步动作 MUST 引用可追溯的 Evidence 与来源。系统 MUST 区分已观察事实、用户陈述、工具结果和模型假设；证据不足时 MUST 指出缺口并请求最有信息量的下一项证据。置信度不得替代证据，也不得将推测表述为确定事实。

### II. 解决必须验证

Service Case 只有在冻结的 Resolution Contract 得到用户或可信工具反馈支持时，才能进入 V1 `RESOLVED`；`CLOSED` 另按关闭规则处理。建议、排障步骤或工具调用成功均不构成解决。验证失败、无法验证或超时 MUST 保持未解决状态并记录后续任务或人工协作；重开 MUST 留痕，不得覆盖历史结论。

### III. 动作有界且可升级

每项 Capability 和 Tool MUST 声明输入、输出、前置条件、证据要求、风险等级、成功标准与失败出口。确定性 Rule 和后端权限 MUST 在公开发布与业务动作前执行。Agent 只能通过类型化应用服务改变业务状态；重要外部操作 MUST 有幂等键、授权和真实回执，无真实接入时 MUST 明示 Mock Adapter。三种协作模式的公开发言受最新后端策略控制，人工加入不终止授权的内部 Agent 工作。

### IV. 状态连续且可审计

Device Passport、Service Case、Conversation、Agent Run MUST 独立建模；Conversation 与 Case 不得强制一对一。Service Case MUST 保留按时间排序的证据、决策、能力调用、用户确认、状态变更及 Follow-up 记录。Checkpoint 不代替业务数据库；中断恢复和重复执行的副作用 MUST 可重入且可审计。所有用户可见消息和公开事件 MUST 经 Conversation Service。

### V. 最小能力架构

当前使用受限的单 Agent 协调 Rule、Skill 与 Tool；只有明确的权限、知识或风险边界需要时才加入 Specialist。Skill 提供方法，Tool 调用应用服务，Rule 约束政策。UI 提案是可失效投影，MUST 与文本和动作提案分离，不能成为业务事实或执行权限。Capability Evolution 仅记录待审经验，不自动改写生产策略。

## MVP Boundaries

- V1 四份主基线及实际验收状态决定实施范围；阶段 0 工程初始化和阶段 1 底座已验收，阶段 2–5 按真实完成状态推进，不得把草案当实现。
- Demo 数据与模拟结果 MUST 明示来源及真实性；不得暗示模拟设备状态、视觉分析或工具结果来自真实生产系统。
- 无明确授权不接入真实客服、订单、支付、维修或设备控制系统；不建设全产品线知识库或通用视觉诊断能力，不创建云资源。
- 用户隐私数据只保留演示所需最小集合；共享或交接时 MUST 避免无关敏感信息。

## Quality Gates

- 每项功能需求 MUST 有可观察的验收场景；每项有构建工作的需求 MUST 在 tasks 中有对应任务。
- 关键成功、权限拒绝、幂等冲突、失败和恢复路径 MUST 有真实 PostgreSQL 验证；缺少 Provider 凭据时真实模型多轮与杀进程恢复 MUST 标为待验。
- Spec、plan、tasks MUST 在进入实现前完成 Spec Kit 一致性分析，解决原则冲突与阻断性缺口。
- Spec Kit plan 的 Phase 0 是研究阶段；开发计划的阶段 0 是已验收工程初始化。两者不得混淆，也不限制后续阶段编写业务代码。

## Governance

本宪章高于单项 feature 的 spec、plan 与 tasks。修改原则时，必须记录原因、影响范围及版本变更，并重新检查受影响的规格与任务。移除或重定义原则升主版本；新增或实质扩展原则升次版本；文字澄清升补丁版本。每次进入实现或合并阶段前，评审者必须核对 Quality Gates 与风险边界。尚未确认的产品选择应写为显式假设或澄清问题，不得偷偷变成事实。

**Version**: 2.0.0 | **Ratified**: 2026-09-25 | **Last Amended**: 2026-10-13
