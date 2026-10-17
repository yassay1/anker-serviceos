# 发现与决策

## 需求
- 定位富回复投影中的 `NameError: safety`。
- 参考成熟 Python 项目的错误预防机制，提出能落到本项目 CI 的计划。
- 用户已确认计划，已在独立评测工作区实施。

## 研究发现
- `backend/serviceos_api/application/rich_reply.py` 的 `project_reply` 中，`assessment` 在前面定义；`safety` 没有定义。危险检查触发时已调用 `safety_rich_reply(assessment)` 并提前返回。
- 因此末尾 `if safety or ...` 在到达时会 NameError；将其替换成 `assessment.triggered` 虽能避免 NameError，但该项因前面的提前返回而恒为 False，可直接删去重复判断。
- 现有 `backend/pyproject.toml` 只有 pytest 开发依赖；CI 执行 OpenAPI、前端检查和后端 pytest，没有 Python 静态名称检查门禁。
- 基线使用 Ruff 0.15.20 对 `backend/serviceos_api` 和 `backend/tests` 运行 `F821,F823`：All checks passed，零存量告警。门禁不扫描评测数据/结果、文档或归档目录。
- 已通过 uv 将 Ruff 锁定为 0.15.22；同一配置下活动代码扫描通过。对标准输入的临时故障样例分别产生 F821、F823，退出码为 1，未保留样例文件。
- 已有 `test_publish_agent_response_projects_valid_rich_reply_and_quick_replies` 测试覆盖有效富回复发布路径，可作为行为回归基础。
- Ruff 官方规则目录将 F821 (`undefined-name`) 与 F823 (`undefined-local`) 标为 correctness 规则；Pyright 官方配置将 `reportUndefinedVariable`、`reportUnboundVariable` 默认设为 error。

## 技术决策
| 决策 | 理由 |
|------|------|
| 采用 Ruff F821/F823，不在本轮引入 Pyright | 基线干净且覆盖此故障，减少配置复杂度和全项目类型迁移 |
| 检查范围覆盖后端活动源代码与测试 | 可发现生产路径和测试自身未定义名称；排除资料数据、结果产物和归档 |
| 为当前 RichReply 逻辑保留集成回归，并测试静态门禁能拦截临时故障样例 | 防止仅配置工具但 CI 未真正捕获该类拼写错误 |
| 集中在全量基线后再改，不边测边修业务实现 | 保留评测证据，避免在质量样本执行中改变业务逻辑 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| `.planning` 有多个活动计划，未绑定时拒绝选择 | 创建本任务独立计划目录，并固定 `PLAN_ID=undefined-name-guardrails` |
| 初次补丁以依赖新增前的 pyproject 内容为预期，未匹配 | 读取实际文件后更新补丁 |
| PowerShell 字符串替换损坏了 README 代码块标记 | 从 HEAD 逐字节恢复 README，再用精确补丁加入单行命令与说明 |

## 资源
- Ruff F821/F823 官方规则：[https://docs.astral.sh/ruff/rules/](https://docs.astral.sh/ruff/rules/)
- Pyright 配置（undefined/unbound variables）：[https://github.com/microsoft/pyright/blob/main/docs/configuration.md](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)
- Pylance 对未定义名称规则的说明：[https://github.com/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md](https://github.com/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md)

## 视觉/浏览器发现
- 不适用。
