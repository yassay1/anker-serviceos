<!--
Sync Impact Report
- Version: template → 1.0.0 (initial ratification)
- Modified principles: template placeholders → Evidence before judgment; Verified resolution; Bounded action and human escalation; Auditability and continuity; Minimal capability architecture
- Added sections: MVP Boundaries; Quality Gates
- Removed sections: none (template placeholders replaced)
- Follow-up TODOs: none; demo-specific choices remain in the feature clarification log
-->
# Anker ServiceOS Constitution

## Core Principles

### I. 证据先于判断

任何诊断结论和下一步动作 MUST 引用可追溯的 Evidence 与来源。系统 MUST 区分已观察事实、用户陈述、工具结果和模型假设；证据不足时 MUST 指出缺口并请求最有信息量的下一项证据。置信度不得替代证据，也不得将推测表述为确定事实。

### II. 解决必须验证

Service Case 只有在 Resolution Contract 的验证条件得到用户或可信工具反馈支持时，才能进入 `VERIFIED_RESOLVED`。生成建议、执行排障步骤或工具调用成功本身均不构成解决。验证失败、无法验证或超时 MUST 保留开放状态、安排 Follow-up，或升级人工。

### III. 动作有界且可升级

每项 Capability 和 Tool MUST 声明输入、输出、前置条件、证据要求、风险等级、成功标准与失败出口。确定性 Rule MUST 在动作前执行。MVP 只能自动执行低风险、可逆、无生产副作用的动作；高风险、不可逆控制、保修/政策承诺和证据冲突 MUST 阻断自动执行并移交人工，携带原因与完整 Case 上下文。

### IV. 状态连续且可审计

Service Case MUST 保留按时间排序的证据、Jev Decision、能力调用、用户确认、状态变更及 Follow-up 记录。Device Passport 与 Case 中已有的信息 MUST 被复用，避免重复索取。每次状态变更 MUST 有触发事件和依据；人工交接 MUST 可复现当前目标、已尝试动作、结果和未决问题。

### V. 最小能力架构

默认使用一个 Service Lead Agent 协调 Rule、Skill 与 Tool。Jev 首先是结构化决策协议或模块；只有独立上下文、知识、工具、权限或风险边界得到明确证明时，才加入 Specialist。Skill 提供可复用方法，Tool 负责明确的查询或动作，Rule 约束确定性政策与状态流转。Capability Evolution 在 MVP 仅记录可审阅的经验，不自动改写生产策略。

## MVP Boundaries

- MVP MUST 覆盖一条设备异常 Case 从理解、证据获取、判断、低风险行动到验证解决或人工升级的闭环。
- Demo 数据与模拟结果 MUST 明示来源及真实性；不得暗示模拟设备状态、视觉分析或工具结果来自真实生产系统。
- 不接入真实客服、订单、支付、维修或设备控制系统；不建设全产品线知识库或通用视觉诊断能力。
- 用户隐私数据只保留演示所需最小集合；共享或交接时 MUST 避免无关敏感信息。

## Quality Gates

- 每项功能需求 MUST 有可观察的验收场景；每项有构建工作的需求 MUST 在 tasks 中有对应任务。
- 固定评估集 MUST 至少覆盖正常解决、证据不足、错误诊断、工具失败与人工升级；检查证据充分性、动作可执行性、验证、上下文连续性和升级质量。
- Spec、plan、tasks MUST 在进入实现前完成 Spec Kit 一致性分析，解决原则冲突与阻断性缺口。
- Phase 0 只产出文档和评估协议；实现任务保持未勾选，不创建业务代码。

## Governance

本宪章高于单项 feature 的 spec、plan 与 tasks。修改原则时，必须记录原因、影响范围及版本变更，并重新检查受影响的规格与任务。移除或重定义原则升主版本；新增或实质扩展原则升次版本；文字澄清升补丁版本。每次进入实现或合并阶段前，评审者必须核对 Quality Gates 与风险边界。尚未确认的产品选择应写为显式假设或澄清问题，不得偷偷变成事实。

**Version**: 1.0.0 | **Ratified**: 2026-09-25 | **Last Amended**: 2026-09-25
