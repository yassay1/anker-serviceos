# 本地项目进度与拉取基线（2026-10-16）

## 本次工作范围

先读取关联聊天《探索项目网页前端升级空间》（`01a130e5-ce6a-7892-9374-fdbaa4b35484`），检查本地目录和 Git 状态，再从 GitHub 完整克隆；最后根据最新代码与远端 CI 规划后续开发。本次没有实现新业务功能。

## 本机目录与后续工作入口

| 目录 | 实际用途 | 后续使用方式 |
|---|---|---|
| `D:\Anker黑客松\anker-serviceos` | 本次完整克隆的真实前后端仓库 | 推荐作为后续开发的主目录 |
| `D:\Anker黑客松\integration\anker-serviceos` | 之前的真实接口适配、UI 重构与本地演示工程 | 保留原分支、数据库配置、截图和运行记录，用于对照 |
| `D:\Anker黑客松\web` | 早期使用浏览器本地状态的纯前端模拟原型 | 历史参考；不作为当前全栈工程入口 |
| `D:\Anker黑客松` 根目录文档 | 最初产品材料和前端演示说明 | 以新仓库的活动代码和 `docs/` 验收记录更新认知 |

克隆前旧工程工作区干净，当前分支为 `codex/reference-ui-rebuild`，HEAD 为 `cae703d`；其远端抓取配置只覆盖 `main`。本次未切换或重置旧工程，也未复制其中的 `.env`、凭据、数据库或忽略文件。旧聊天中的“服务已启动”是历史记录，本次没有据此宣称旧服务仍在运行。

## 完整克隆的证据

- 仓库：<https://github.com/yassay1/anker-serviceos>。
- 当前分支：`main`，跟踪 `origin/main`。
- 拉取基线：`1c7da436492cae2996baf6e5fb8bc7dabb1ab136`。
- 提交：`fix: parse curated metrics across Windows line endings`。
- 对应树：`e82ea33f7fdee392f4b0497cb946b6b91bc44429`，与 GitHub 返回的树一致。
- `git rev-parse --is-shallow-repository` 返回 `false`，未使用浅克隆或过滤克隆。
- `remote.origin.fetch` 为 `+refs/heads/*:refs/remotes/origin/*`，已获得 14 条远端分支，不含 `origin/HEAD` 这个符号引用。
- `main` 可达提交数为 62；克隆时跟踪文件共 314 个，含前后端、锁文件、迁移、设计图、官方 Word 和约 43.8 MB 的官方 Excel。
- `git fsck --full` 退出码 0；`git lfs ls-files` 与 `git submodule status` 均为空，当前仓库没有另外待取的 LFS 文件或子模块。
- 初次 HTTPS 下载停滞后，使用仅对该命令生效的 HTTP/1.1 重新克隆成功，没有修改全局 Git 配置。

“完整”指 Git 管理的项目内容与历史。业务数据库、上传文件、本地截图、密钥和虚拟环境并不由 GitHub 克隆提供，必须按运行说明准备。

## 关联聊天与当前主分支的差异

旧聊天完成了五张参考图对应的首页、诊断会话、案例详情、客服总览和客服会话台重构，通过 [PR #13](https://github.com/yassay1/anker-serviceos/pull/13) 合入 `main`，合并提交 `312aeaf`。当时本地前端为 81 项回归通过，后端有 8 项既有失败。

**这些失败是历史状态。** 当前主分支在 `312aeaf` 之后又推进了 13 个提交，已经包含：

1. 恢复后端绿色测试基线，并同步 V1 接口提案。
2. 修复新版客户工作区访问会话列表的路径。
3. 整理应用服务、资源路由和 Worker 写入边界，提高失败可观测性。
4. 加入官方赛题参考资料。
5. 加入用户表达理解与回应提示指导，尚无真实模型质量评测。
6. 加入来源受限的 `KnowledgeMetricChart` 与仅客服可见的 `CaseProcessFlow`，修复来源 ID 和 Windows 换行解析。

上述功能已有实现，后续不应再次按“从零搭建”安排。新增图表也不代表真实设备遥测；来源、型号和权限限制见 [图形组件验收](generative-visual-components-validation.md)。

## 当前可信验证结果

[最新 GitHub Actions](https://github.com/yassay1/anker-serviceos/actions/runs/38840534680) 对应准确提交 `1c7da43`，北京时间 2026-10-16 10:31 完成，结论 `success`：

| 检查 | 实际结果 | 证据范围 |
|---|---|---|
| 后端完整 PostgreSQL 回归 | 219 passed | CI 临时 PostgreSQL，不是本机数据库 |
| 前端受控浏览器回归 | 85 passed | 受控 HTTP 响应，包含新增图表场景 |
| 真实 API/数据库浏览器回归 | 6 passed | CI 临时环境；不含真实模型质量 |
| OpenAPI、提案、生成类型、类型检查与构建 | 通过 | CI 对应准确提交 |
| delivery-config / container-smoke / dependency-audit | 全部 success | 不等于真实云部署或真实售后系统接入 |

本次新目录已恢复前端锁定依赖，本机 `npm run check:api`、`npm run typecheck`、`npm run build` 均退出码 0。构建产物 JS 419.28 kB、gzip 126.25 kB；CSS 52.08 kB、gzip 10.89 kB。

本机 Python 环境恢复与后端契约检查的最终结果见本文件末尾的本地检查补充。没有启动新的业务数据库、写入原演示库，或重新执行本机完整 PostgreSQL/真实浏览器验收。

## 当前真正未关闭的缺口

| 缺口 | 实际依据 | 对路线的影响 |
|---|---|---|
| 页面创建 Case、录入 Device、关联 Conversation/Device 的入口不完整 | `CasesWorkspace.tsx`、`DevicesWorkspace.tsx` 和 `api/client.ts` 与 PR #13 合并时相同；仍以列表/详情为主 | 优先补齐从空账号开始的服务入口 |
| 创建 Case/Device 的未知结果恢复不完善 | `CreateCase`、`CreateDevice` 没有客户端请求 UUID；`BusinessService.create` 每次创建新记录 | 在增加自动重试前明确创建幂等契约，不能假定接口已支持 |
| 真实 Provider、多轮质量及强制中断恢复待验 | 当前活动开发计划和阶段 2 验收记录 | 软件 CI 通过不能替代真实模型验收 |
| 官方数据尚未形成标注评测集或完整运行时检索 | `data/reference/hackathon/README.md` | 按型号、来源、适用范围整理后再接入，不能直接整包导入知识库 |
| 经验审核有 API，没有客服审核界面 | `docs/experience-learning-validation.md` | 可作为后续独立增强切片 |
| 图片只有结构检查；多模态与完整安全扫描未完成 | 阶段 4 文档 | 演示边界必须准确，若实现则单独验收 |
| 回访撤回、改期和取消未实现 | 阶段 4 文档 | 放到后续完善，演示不承诺这些操作 |
| 生产认证、真实售后 API、云环境仍待接入 | README、部署与运维文档 | 与本轮黑客松本地交付分阶段推进 |

## 后续计划

见 [2026-10-16 开发路线](superpowers/plans/2026-10-16-development-roadmap.md)。继续沿用旧聊天中用户确认的“黑客松可提交、可演示版本”目标。

## 本地检查补充

- 前端：`npm ci --prefer-offline --no-audit --no-fund` 成功恢复 70 个包；API 类型、TypeScript 与生产构建检查通过。
- 后端：使用 `D:\Anker黑客松\integration\.tools\uv\bin\uv.exe`，通过 `sync --project backend --locked --python C:\Users\Felicitate\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe --no-python-downloads` 恢复 73 个包，实际解释器 Python 3.12.14。首次自动选择 3.12.15 时 uv 的解释器链接检查失败；改用本机已验证的解释器后成功，未改项目依赖或锁文件。
- `backend/.venv/Scripts/python.exe -m serviceos_api.export_openapi --check`：通过。
- `backend/.venv/Scripts/python.exe contracts/proposed/v1/sync_implemented.py --check`：通过。
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_agent_result.py backend/tests/test_ui_catalog.py backend/tests/test_ui_visualizations.py backend/tests/test_api_baseline.py backend/tests/test_observability.py -q --basetemp <本仓库.runtime下本次唯一目录>`：**47 passed，退出码 0**。这仅是指定文件的离线回归，不是本机 219 项 PostgreSQL 全量回归。
- 首次 pytest 在系统临时目录清理旧链接时遇到 WinError 5；改为仓库内新建的独立临时目录后完成。复现时先确保 `.runtime` 父目录存在，并为 `--basetemp` 使用新的目录名。
- Git 跟踪源码和锁文件与拉取基线无差异；新增文件仅本进度报告和开发路线，尚未提交或推送。原 `cae703d` UI 分支提交是当前 `main` 的祖先，前端成果已包含在新工程中。
