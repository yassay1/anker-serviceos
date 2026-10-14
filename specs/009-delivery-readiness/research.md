# Research: 交付准备

## 当前基线

Decision: main 10fe1fc 上增量推进；动作、核验、回访、归档复用现有服务。
Rationale: 远端领先旧图片分支 25 个提交，已有完整阶段四切片及 live Playwright 流程。
Alternatives considered: 重新实现阶段四会复制规则，拒绝。

## 运行环境

Decision: 同一 Python 镜像多个独立进程；本地 Compose PG17，显式一次性迁移；生产外接 RDS。
Rationale: API 启动不迁移或启动 Worker；无 Provider 不领取消息任务；非模型 Worker 可独立运行。
Alternatives considered: 不引入 Redis/Celery，不用容器健康检测触发模型调用。

## 安全就绪

Decision: liveness 不变，readiness 检查数据库/schema 并单独报告认证、存储和模型配置；生产认证未配置必须 fail closed。
Rationale: 当前业务认证仅本地开发，不能把容器启动等同于生产可用。
Alternatives considered: 不开放生产本地账号，不信任任意 X-Forwarded-For，不记录原始异常/请求体。

## Skill

Decision: 固定版本注册表与类型化输出；服务端过滤适用性，LLM 只能选择已允许方法，加载状态与完成状态分开。
Rationale: 现有 AgentRun.result_payload 可容纳 INTERNAL 审计，工具仍由应用服务验证活跃租约；情绪只准备契约。
Alternatives considered: 不增加模型训练、独立推理服务或可执行远程 Skill。

## 事件与界面

Decision: 现有 Outbox/SSE 保留，增加枚举化真实进度与前端单调游标、去重、补取和快照回退。
Rationale: 当前公开类型白名单没有 Agent progress，客户端保存任意数字序号且未去重；客户看不到内部事件导致序号间隙是合法情况。
Alternatives considered: 不凭动画造进度，不将 sequence 不连续直接视为丢失，不展示工具参数或推理。

## 证据存储

Decision: 沿用 EvidenceStorage 协议；生产 S3 私有桶、限定 UUID 对象键、服务端授权代理读取；不开放任意 URL。
Rationale: local_evidence_storage 已拒绝生产目录回退。私有代理访问保持现有下载授权及 CLEAN 检查。
Alternatives considered: 暂不做浏览器直传和公开对象 URL。

## 网络与验证限制

Git smart HTTP 和 Docker Hub 当前受本地网络限制；Git 已用 gh 只读 API 重建并验证全部对象 SHA，未推送。容器镜像尝试本机已有 DaoCloud 来源，默认交付仍使用官方镜像参数。缺少真实 Provider，相关质量/首 token 指标必须保留未测。
