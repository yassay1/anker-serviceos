# Feature contract: Delivery readiness

状态：依据用户本轮要求确定的增量契约；仅真实实现后导出活动 OpenAPI。

## HTTP

- `GET /api/v1/health`：原有 liveness 保持不变。
- `GET /api/v1/readiness`：无副作用、无模型外呼，200/503，返回 overall 与 database/schema/auth/storage/provider 的最小状态；不包含地址、密钥或异常原文。
- `GET /api/v1/skills`：需要客服认证，返回版本化 registry 与 schema，PREPARED 明示不可执行。
- `GET /api/v1/conversations/{conversation_id}/skill-executions`：仅同租户有权客服，返回分页有界 INTERNAL skill 记录；客户403、跨租户404。
- Skill 加载经 AgentToolService 活跃 run+lease 验证；未知/预备技能拒绝，不注册外部动作接口。

## Events and UI

`agent.progress` 使用固定 stage 枚举及安全摘要；run_id 仅当前会话内引用。公开发布统一通过 ConversationService；人工主导时不得把模型生成文本当公开进度。旧 UI revision 按既有409语义拒绝。客户端处理重复/乱序事件不倒退游标，重连查询权威快照；内部事件形成的 sequence 间隙不视为错误。

## Configuration

- `SERVICEOS_ENV`、`SERVICEOS_AUTH_MODE`：生产禁止 local；保留现有 disabled 模式但 readiness/auth 明示未配置。
- `SERVICEOS_ALLOWED_ORIGINS`：显式 origin 列表；不使用 wildcard。
- `SERVICEOS_LOCAL_AUTH_NETWORKS`：仅开发/测试容器显式私网，默认回环；不信任客户端转发头。
- `SERVICEOS_EVIDENCE_STORAGE_BACKEND=local|s3`，S3 bucket/region/prefix 由环境注入，使用 SDK 凭据链；不提交长期密钥。
- 所有容器密钥由环境或 Docker secret file 注入；前端不得构建入后端密钥。
- 开发网关仅绑定127.0.0.1，API/DB 不默认暴露宿主端口。

## Integration ownership

主任务负责 settings/main/dependencies/health/observability/storage 及最终 OpenAPI/Client。交付子任务只改 Docker/Compose/deploy/CI/operations 文档；Runtime 子任务只改 Skill、Agent 工具和进度；前端子任务负责事件 hook、界面及浏览器测试。阶段四审查结果由主任务协调，避免共享文件并发覆盖。

## Acceptance

真实 PostgreSQL 成功/拒绝/租户隔离/版本/幂等/恢复；SSE重连与UI降级；local 与生产配置负例；容器初始化/重启/备份恢复；桌面/移动端真实浏览器；所有 Provider/云端未验收门槛单独记录。
