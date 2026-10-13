# Codex 工程工作规范 · 售后通

## 在写代码前

1. 阅读 `README.md` 与 `docs/product-definition.md`、`docs/architecture.md`、`docs/domain-and-contracts.md`、`docs/development-plan.md`。
2. 先检查实际项目文件与依赖，避免重写已有实现；不得把文档草案称为已实现。
3. 开始每个阶段时指出目标、受影响模块和验收方式；除非明确需要，不得重做技术栈选型、不做 Parlant/LangGraph 对比 Spike。

## 必须遵守的业务规则

- Device Passport（长期设备档案）和 Service Case（一次问题服务案例）独立建模；Conversation 与 Case 不是一对一。
- `AI_LEAD` / `CO_SERVICE` / `HUMAN_LEAD` 是协作策略；对外发布必须经过后端授权控制，不由 LLM Prompt 控制。
- Agent 的工具只通过应用服务修改业务状态；所有重要外部操作有幂等键、权限和真实回执；无真实 Anker API 接入时使用明确标识的 Mock Adapter。
- 不把模型猜测直接写成已验证设备事实；不泄漏用户私密资料、内部备注、原始模型推理内容或密钥。
- LangGraph Checkpoint 不等于业务数据库；人工中断恢复前后的副作用必须设计可重入性。
- 快速确认用户消息，不把长 LLM 调用阻塞在 HTTP；真实事件可观察，前端不能虚构完成进度。

## 代码与接口

- 后端模块化单体，业务边界明确；前后端独立开发于同一仓库。
- 真实业务路由、Pydantic Schema、OpenAPI 和前端生成 Client 同源。对未实现接口，不注册只返回 200 的伪接口。
- 使用 `.env.example` 给出变量名称，不提交秘密和账号凭证。未经批准，不部署 AWS、不创建云付费资源、不修改他人外部服务。
- 新功能须有测试覆盖关键成功与失败路径；性能优化不能绕过安全验证和正确性。
- 所有代码修改输出：变更文件、实际执行命令、测试结果、已实现范围、未实现/风险项。

## 本仓库的文档入口与演进

- docs 下四份 V1 是用户指定主基线。涉及新旧冲突、目录衔接或复用现有模块时，先阅读 docs/baseline-integration.md；来源哈希见 docs/baseline-provenance.json。
- 旧 A1229 `app/` 原型、旧功能 spec、根级旧 Python 工程及历史会话规划日志已归档到项目外的 `D:\proj\Anker SreviceOS-archive-20261013`；不得把归档里的旧选型或未执行任务当成当前计划。`.specify/memory/constitution.md` 是仍保留的工程约束，继续继承证据、安全、验证与审计原则。
- 当前后端工程位于 `backend/serviceos_api/`；Agent 所需的活动只读手册资料位于 `backend/serviceos_api/knowledge/`。业务变更须经过应用服务和类型化命令，不能复制出第二套验证规则。
- 开始下一阶段前检查 `docs/development-plan.md` 的真实勾选状态；当前实施清单在 `docs/baseline-integration.md`。所有用户可见消息和公开流通过 Conversation Service；不得将历史原型或归档内容描述为当前实现。
- 跨模块、接口或迁移改动先读 `docs/contributing.md`：按实际代码确认边界，先协调契约，再分别实现并做集成校验。

