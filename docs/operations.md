# 交付、运行与恢复

本文件对应阶段 5 的交付准备，不是云部署完成记录。生产身份源尚未实现；生产 Compose 固定 `SERVICEOS_AUTH_MODE=disabled`，业务认证仍被阻断，`/api/v1/readiness` 应返回 503。不得改为开发登录、绕过认证或把健康灯当上线批准。真实 Provider、Anker API、RDS/S3、公开 HTTPS 和灾难恢复演练分别需要真实验收与授权。

## 1. 文件与隔离边界

| 环境 | Compose / 配置 | 边界 |
|---|---|---|
| 开发 | 根 `compose.yaml`、`deploy/local/.env.example` | PostgreSQL 17 持久卷；独立 API、inspection、actions（明确 Mock）、followups、outbox；仅 `127.0.0.1:8080` 对宿主开放 |
| 测试 | `deploy/compose.test.yaml`、`deploy/test/.env.example` | 独立项目 `serviceos-test`；仅测试 PG，回环 55433；数据库位于 tmpfs，停止后不承诺保留；pytest 创建/删除独立临时数据库 |
| 生产准备 | 根 `compose.production.yaml`、`deploy/production/.env.example` | 独立文件，**不与开发 Compose 合并**；外部 TLS PostgreSQL、私有 S3、HTTPS；无数据库容器、种子服务、开发身份或 Mock action Worker |

开发网络固定为 `172.30.85.0/24`，API 明确允许此私网及回环开发登录。不要将其他容器接入此网络，不要给开发网关添加公网转发。API/DB 不发布宿主端口。Nginx 清除转发身份头，Uvicorn 使用 `--no-proxy-headers`，不可用用户提供的 `X-Forwarded-For` 通过本地认证检查。网络冲突时先协调修改 subnet 与认证白名单，不能只改其中一处。

API、检查 Worker（以及显式启用的 Agent）共用私有 `evidence-data` 卷，路径 `/data/evidence`，UID/GID 10001、目录权限 0700。数据库只保存对象引用；Nginx 不挂载、不直接发布证据卷。新命名卷继承镜像目录所有权；已有 root 所有权卷须在停写、备份后由管理员定向修复，不能设为 0777。

Python 镜像的工作目录为 `/app`，安装包和可执行程序在 `/app/backend/.venv`，迁移配置固定 `/app/backend/alembic.ini`。API/Worker 使用同一镜像、非 root、只读根文件系统，`/tmp` 用于临时文件和心跳。前端 Node 24 多阶段构建，只复制静态产物到非 root Nginx，不接收任何后端秘密或 `VITE_*` 密钥。

## 2. 本地启动（操作者执行，本次文件交付未启动）

需要 Docker Engine/Desktop、Compose v2.24+（当前静态校验使用 v5.1.4）；原生测试使用 Python 3.12、uv 0.12.5、Node 24。以下命令是 Bash / Git Bash，不是 Windows PowerShell 5 的二进制重定向语法。设仓库绝对路径；Linux 替换为实际路径：

```sh
REPO='D:/Anker'
# 只在文件不存在时复制；随后编辑样例密码。
test -e "$REPO/deploy/local/.env" || cp "$REPO/deploy/local/.env.example" "$REPO/deploy/local/.env"
# Linux/macOS 上限制文件权限；Windows 用相应的文件 ACL。
chmod 600 "$REPO/deploy/local/.env"
dc() { docker compose --project-directory "$REPO" --env-file "$REPO/deploy/local/.env" -f "$REPO/compose.yaml" -p serviceos-dev "$@"; }
dc config -q
dc build api web
dc up -d --no-build --wait --wait-timeout 180
# migrate 已成功退出后才显式建立样例身份；不会在 API 启动时自动 seed。
dc --profile seed run --rm --no-deps seed
dc ps -a
curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/readiness
```

`POSTGRES_PASSWORD` 直接嵌入开发 URL，请用字母、数字、`-`、`_`；不要在此字段放未编码的 `@:/?#%`。生产完整 URL 的用户名/密码须正确 URL 编码。配置文件只用于 Compose 插值，不会把所有变量自动传入容器。不要在终端/CI 打印 `docker compose config` 的完整结果，也不要上传 `.env`、`docker inspect` 环境或私钥。`.env` 被 Git 忽略，构建上下文同时排除所有 `.env*`、私钥、缓存和备份。

入口：`http://127.0.0.1:8080/support`、`/desk`、`/cases`。开发账号包括 `customer-a`、`customer-b`、`staff`、`supervisor`、`other-tenant`；密码为独立的 `SERVICEOS_LOCAL_AUTH_PASSWORD`。迁移服务执行 `alembic -c backend/alembic.ini upgrade head`；失败则 API/Workers 不启动。数据库密码改变不会自动改变已存在 PG 卷中的角色密码，需受控轮换，不能通过删卷“修复”。

### 镜像来源与离线限制

默认来源：`python:3.12-slim`、`node:24-alpine`、`nginx:1.28-alpine`、`postgres:17`。uv 固定 0.12.5，Python `uv sync --locked --no-dev --no-editable`，前端 `npm ci --registry=https://registry.npmjs.org`。锁文件不等于基础镜像不可变；发布时记录基础镜像 digest、来源、平台、代码版本与最终镜像 digest，完成漏洞审查后使用不可变引用。

Docker Hub 不可达时，可在本地 `.env` 覆盖 `PYTHON_IMAGE`、`NODE_IMAGE`、`NGINX_IMAGE`、`POSTGRES_IMAGE`，或直接用 Docker `--build-arg`。本次环境已知缓存了 `docker.m.daocloud.io/library/python:3.12-slim` 和 `nginx:1.27-alpine`；Node 镜像由集成负责人处理，本任务未重复拉取。镜像缓存/镜像站不是供应链验证：先核对受信来源的 digest、平台和版本，记录与官方内容是否匹配；旧 Nginx 1.27 仅可作为经核对的本地联调覆盖，不能默认为已通过生产安全审查。Dockerfile 使用内置语法，不额外拉取 Dockerfile frontend 镜像；PyPI/npm 下载仍可能受网络限制，不要通过去掉锁定或禁用 TLS 绕过失败。

### Agent 必须显式启用

只有模型目的地、预算和数据出境已获准时，才在本地 `.env` 设置全部 `SERVICEOS_LLM_MODEL`、`SERVICEOS_LLM_BASE_URL`、`SERVICEOS_LLM_API_KEY`：

```sh
dc --profile agent up -d --no-build --wait --wait-timeout 180 agent
```

`checkpoints` 一次性初始化独立 schema 后，Agent 才启动。缺失 Provider 时 Worker 拒绝领取任务；profile 本身不提供 Provider、不代表模型验收成功。不启用 Agent 时，图片结构检查、Mock 回执、内部回访任务及 Outbox 仍各自由独立 Worker 处理；检查通过不代表恶意内容扫描或多模态理解。

## 3. 测试与健康检查

独立原生测试数据库（不要指向已有演示库或生产）：

```sh
test -e "$REPO/deploy/test/.env" || cp "$REPO/deploy/test/.env.example" "$REPO/deploy/test/.env"
tc() { docker compose --env-file "$REPO/deploy/test/.env" -f "$REPO/deploy/compose.test.yaml" -p serviceos-test "$@"; }
tc config -q
tc up -d --wait
# 仅 source 自己审查过的本地测试配置；不要 source 不可信文件。
set -a
. "$REPO/deploy/test/.env"
set +a
uv run --project "$REPO/backend" --locked pytest "$REPO/backend/tests" --require-postgres
# 完成后停止测试库；tmpfs 中的数据是可丢弃的。
tc down
```

不要把 `backend/.env`、测试文件或 CI 临时凭据当生产配置。CI 保留真实 PostgreSQL、Mock HTTP Playwright、真实 API live Playwright；live 测试使用 CI 独立创建的 `serviceos_dev` 和显式开发认证，非生产库。CI 新增三环境 `config -q`、缺参负例、生产预检单元测试、镜像构建/非模型栈启动/卷重启/HTTPS 配置检查与依赖审计。审计查询网络失败也会失败，不写 `continue-on-error`；npm 高危/严重及 Python 任意已知漏洞分别阻断其审计 job，报告保存为 artifact。CI 文件存在不表示远端已执行或审计无漏洞。

| 检查 | 含义与限制 |
|---|---|
| `/nginx-health` | 仅网关进程；不代表 API、证书链或业务可用 |
| `/api/v1/health` | API liveness；生产 Compose 用它做基础进程探测，不用 readiness 阻断离线预检 |
| `/api/v1/readiness` | DB/schema、已启用认证等真实前提；生产身份缺失为 503，Provider/S3 配置不等于外部验收 |
| `python -m serviceos_api.worker.health --role inspection` | 读取 `/tmp/serviceos-inspection.heartbeat`；同样支持 `actions`、`followups`、`outbox`、`agent` |

心跳由 Worker 实际循环维护，不由健康探针伪造。健康容器不代表每个业务任务成功；需同时检查持久任务状态、租约过期、队列等待与错误码。Docker `unhealthy` 本身不会触发自动重启；`unless-stopped` 只负责进程退出/宿主重启后的恢复。告警、积压阈值和监控外送还需运维接入。

Nginx `/api/` 使用 HTTP/1.1，关闭响应/请求缓冲、缓存、gzip 和 upstream 重试，读写/SSE 超时 3600 秒；动态解析容器 DNS 以支持 API 重建。12 MiB 代理请求上限给 10 MiB 文件加 multipart 留余量，业务文件限制仍由后端执行。安全头禁止嵌入、限制内容来源和缓存；SSE 重连只能补取真实事件，不重放业务写请求。

## 4. 重启、升级与日志

```sh
dc restart api inspection actions followups outbox web
dc up -d --no-build --wait --wait-timeout 180
dc logs --since 10m --tail 100 api inspection actions followups outbox
```

不要把原始日志当公开工单附件。Nginx access log 只记录时间、方法、状态、字节数、耗时和关联编号，不记录 IP/URL/query/cookie。API proxy 的 Nginx error log 关闭，避免 Nginx 把原始请求带进错误记录；排障使用脱敏 API 日志与元数据 access log。Docker 日志每容器轮转 3 × 10 MiB；这不是长期审计备份。长期保留/告警需单独配置，禁止把聊天内容、内部备注、凭据或原始推理送进日志。

升级前完成下节协调备份，停止所有写入者，记录旧/新代码及镜像 digest、Alembic revision。数据库保持运行，先用目标镜像执行一次性迁移，再启动新 API/Workers。`restart` 不更新镜像/环境，升级使用 `up -d --force-recreate`；迁移失败停止发布，不能继续放流量。恢复后核对原幂等键与真实回执，UNKNOWN 只查询对账，不能直接重置为 APPROVED 或重复执行。

禁止把 `alembic downgrade` 当通用回滚：可能丢列/记录，旧程序也未必兼容新 schema。优先受审的向前修复，或将完整备份恢复到隔离新库/新证据卷后验证并切换；降级只能在可丢弃副本上核对具体 migration 后演练。

## 5. 本地协调备份和隔离恢复

PG dump 不包含图片；分别在不停写时导出会产生不一致。以下是**维护停写窗口**方案，不是在线高可用备份。先确认本机其他 API/脚本不连接该库/证据卷；关闭所有客户端入口和全部写入者（包括已启用的 Agent），等待在途事务结束，再保留 PG 运行：

```sh
# Bash，遇错停止，不在备份失败时自动恢复写入。
set -euo pipefail
BACKUP="$REPO/.runtime/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
umask 077
dc --profile agent stop web api inspection actions followups outbox agent
# 确认不再有其他写入者后执行；dump 包含业务、public 迁移版本及已存在的 checkpoint schema。
dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$BACKUP/database.dump"
dc run --rm --no-deps -T api python -c 'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); t.add("/data/evidence",arcname="."); t.close()' > "$BACKUP/evidence.tar"
test -s "$BACKUP/database.dump" && test -s "$BACKUP/evidence.tar"
sha256sum "$BACKUP/database.dump" "$BACKUP/evidence.tar" > "$BACKUP/SHA256SUMS"
dc run --rm --no-deps migrate alembic -c backend/alembic.ini current
# 在受保护的备份目录记录输出 revision、镜像 digest、UTC 停写窗口和备份命令退出状态。
```

备份含身份、消息、内部资料及图片，须加密、限制 ACL，移到受保护的独立存储并制定保留/删除策略；校验和不提供加密。不要把 dump/tar 放入 Git 或构建上下文。复制后校验 `SHA256SUMS`，实际执行恢复才能证明可恢复。非演练时确认备份完整后，可用 `dc up -d --no-build --wait` 恢复原来的非模型服务；Agent 只在原本获准启用时单独恢复。

隔离恢复使用新 Compose project/new volumes，**绝不导入原卷**。由于开发网络/端口固定，先移除原容器与网络但保留原卷；这不会清空源数据：

```sh
# 先人工确认 BACKUP 指向刚才同一停写窗口、正确版本的备份。
sha256sum --check "$BACKUP/SHA256SUMS"
dc --profile seed --profile agent down   # 不加 --volumes
rc() { docker compose --project-directory "$REPO" --env-file "$REPO/deploy/local/.env" -f "$REPO/compose.yaml" -p serviceos-restore "$@"; }
# 第一次演练前确认 serviceos-restore 项目和它的卷不存在；已存在时另选新项目名。
rc up -d --wait postgres
rc exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$BACKUP/database.dump"
# 禁止覆盖非空证据目录；Python 3.12 data filter 拒绝不安全归档路径。
rc run --rm --no-deps -T api python -c 'import pathlib,sys,tarfile; p=pathlib.Path("/data/evidence"); assert not any(p.iterdir()), "restore target must be empty"; t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|*"); t.extractall(p,filter="data"); t.close()' < "$BACKUP/evidence.tar"
rc run --rm --no-deps migrate alembic -c backend/alembic.ini current
# 使用备份对应镜像；先人工确认 schema 兼容再迁移，不先建表再导入 dump。
rc run --rm --no-deps migrate
# 第一轮仅开 API/Web，保持 Agent、动作、回访、Outbox 停止，防止自动处理还原任务。
rc up -d --no-build --wait api web
```

恢复验收：核对租户隔离、消息/Case/设备数量与关联、证据摘要和授权下载、动作回执/UNKNOWN、未到期与到期回访、Outbox/Checkpoint/租约状态；种子账号已在备份中，不重复初始化。先以只读/查询检查为主，再在隔离副本受控启用各 Worker 验证幂等恢复。记录实际耗时/可接受数据损失（RTO/RPO）及失败点，不能从脚本推算为已达标。演练结束停止 `serviceos-restore`，不带 `--volumes`；人工确认后再恢复 `serviceos-dev`。本文件不提供自动删库/删卷命令；演示 reset 由受控业务 CLI 独立负责，不等同于灾备恢复。

## 6. EC2 / RDS / S3 / HTTPS 准备（不执行云变更）

1. **身份门槛**：先实现并验收生产身份/会话/租户授权、HTTPS Cookie/CSRF 策略；目前配置固定 disabled，不能对真实用户开放。预检只检查传输配置，不调用 readiness，也不登录 AWS/Provider。
2. **EC2 网络**：审批后才创建资源。主机最小权限、补丁、磁盘加密、SSM 管理优先；SSH 如保留，仅固定管理员 CIDR。EC2 SG 只向允许的业务来源开放 443，80 仅重定向；不开放 8000/5432。维护阶段先保持外部流量关闭。
3. **RDS**：PostgreSQL 17 私有子网、Public access 关闭；RDS SG 的 5432 只接受应用 EC2 SG，不用 `0.0.0.0/0`。DB 子网/出站/DNS 连通分别验证；开启静态加密、自动备份/PITR，按业务批准保留期、维护窗口、删除保护，恢复演练使用新实例。
4. **数据库权限/TLS**：运行账号仅必要 DML/sequence 权限；迁移/Checkpoint 初始化账号另给有限 DDL，发布时单独注入迁移 URL，不长期让 API 持有高权限账号。完整 `SERVICEOS_DATABASE_URL` 必须含 `sslmode=verify-full&sslrootcert=/etc/serviceos/rds/global-bundle.pem`；从受信 AWS 来源获取并校验 RDS CA bundle，宿主绝对文件只读挂载。预检拒绝 TLS 降级、query host/service 覆盖、不可读 CA，不替代真实 TLS 握手。
5. **S3/IAM**：独立私有 bucket 与环境 prefix，Block Public Access 全开、Object Ownership bucket-owner-enforced、禁用 ACL、默认加密、版本控制和经批准的保留/生命周期。`iam-evidence-policy.json` 是实例角色对象级最小权限模板，替换 bucket/prefix；`s3-bucket-policy.json` 只拒绝明文传输，不负责授予访问。API/inspection 使用 SDK 默认凭据链和实例角色，不嵌入长期 AWS Key；模板不传 `AWS_ACCESS_KEY_ID` 等变量。使用 SSE-KMS 时另行评审指定 key 的 `GenerateDataKey`/`Decrypt` 权限。应用角色不给 bucket 管理、跨 prefix 或删除历史版本权限；备份角色另行隔离。
6. **容器角色访问**：实例角色是同宿主共享权限边界，不宣称这里实现了逐容器 IAM 隔离；限制宿主与 Docker socket 权限。IMDSv2 必须启用，容器桥接确需时评审 token response hop limit=2，不关闭 IMDSv2。按 VPC 策略配置 S3 endpoint/出站；只有 Agent 的获准 Provider 需要额外模型出站。
7. **HTTPS**：DNS 与受信证书由获授权运维准备，目录内有 `fullchain.pem`、`privkey.pem`，只读挂载给 Nginx。私钥限制到实际 Nginx UID/GID（官方 Alpine 通常为 101）可读的 0640/ACL，不设 world-readable；CA 可公开读取。证书目录用真实文件，不放指向挂载外的失效 symlink。80 对指定域名 308 到 HTTPS；未知 Host 拒绝、未知 SNI 拒绝握手；TLS 1.2/1.3、HSTS，不使用未确认的 preload/includeSubDomains。
8. **续期**：预先指定负责人、到期告警与续期任务，推荐受控 DNS-01（模板不提供 HTTP-01 路径）。新证书原子替换到已挂载目录，先 `pc exec -T web nginx -t`，成功后 `pc exec -T web nginx -s reload`；失败保留当前进程/旧证书，告警并回退。外部验证证书域名、完整链、到期时间、重定向、SSE 和上传。禁止用 `curl -k` 作为验收。

生产准备命令只供将来经授权的目标机使用，**当前不执行**：

```sh
# 目标机 REPO、受保护 .env、CA、证书目录和已验证镜像已由操作者准备。
pc() { docker compose --project-directory "$REPO" --env-file "$REPO/deploy/production/.env" -f "$REPO/compose.production.yaml" -p serviceos-production "$@"; }
pc config -q
pc run --rm --no-deps preflight
# 此时仍不得开放真实用户流量。下列有 DB 副作用的命令需部署授权：
pc run --rm --no-deps migrate
# Agent 使用前单独授权初始化 checkpoint；不自动调用 Provider。
# pc --profile agent run --rm --no-deps checkpoints
pc up -d --wait --wait-timeout 180 api inspection followups outbox web
pc exec -T web nginx -t
# liveness 可为 200，但生产 readiness 的 503 是当前预期阻断，不能隐藏。
```

生产 Compose 不自动构建/推送镜像。发布前用 CI 验证过的同一镜像 digest，不临时从未审查镜像站替换。模板支持环境注入秘密；环境对 Docker 管理员可见，需受控发布渠道、0600/ACL 配置与轮换；不要把 `.env` 放 web 根目录。当前模板未接 Secrets Manager 自动获取/轮换。

### 生产备份与恢复门槛

RDS 自动备份/PITR **不包含 S3**；S3 versioning **不等于协调备份**。必须建立同一停写屏障：关闭入口、停止全部 API/Workers 和其他对象写入者，记录 UTC、RDS 恢复点/快照、全部相关 S3 key/version-id 清单与校验和、迁移版本和镜像 digest。保留屏障直至数据库与对象清单一致且备份可读取；在线协调机制未实现前不要宣称零停机备份。

恢复到新 RDS 实例和独立 bucket/prefix，按同一版本清单恢复对象，重建最小 DB 权限；不要用会删除源对象的同步命令。验证引用完整性、授权、回执、租约、Outbox 和 checkpoint 后才允许受控切换。恢复副本初始禁止 Provider/外部动作出站并停止 Workers，防止还原到期任务产生副作用。审计/图片/身份数据按隐私保留期处理；RTO/RPO、证书轮换、IAM 最小权限与真实 S3 失败路径仍需实际演练。

## 7. 当前验证范围

本交付执行了三份 Compose（含可选 profiles）`config -q`、缺少本地密码/生产数据库 URL 的两项拒绝检查、YAML/JSON 与拓扑隔离断言、Python 3.12 下 10 项离线生产预检测试；没有构建镜像、启动/重启服务、导入/清空数据、运行云命令、推送或部署。镜像构建、Nginx `-t`、容器登录/上传/SSE、卷恢复、远端 CI 与依赖审计结果由集成负责人据实记录，不能从配置文件推断通过。生产身份、真实模型、真实 Anker 操作、云端对象存储/网络/证书与备份恢复各自保持独立门槛。
