# 五张参考图前端重构验收

日期：2026-10-15。后端基线 `adb4610`。本地分支 `codex/reference-ui-rebuild`。

## 已实施页面与组件

| 参考图 | 实际路由 | 主要实现 |
|---|---|---|
| 客户首页 `customer-home.png` | `/`（客户身份） | `CustomerHome.tsx`：家居横幅、真实问题输入、六类问题入口、服务与设备预览、服务保障说明 |
| AI 诊断 `ai-diagnosis.png` | `/support?conversation=<id>`，原 `/support` 保持可用 | `ConversationWorkspace.tsx`：暖色横幅、使用指引、折叠会话选择、对话和交互卡、右侧真实关联服务与协作说明 |
| 服务详情 `service-detail.png` | `/cases/:id` | `CasesWorkspace.tsx`：案例身份区、真实状态概况、三列进展/动作、问题/图片、协作/核验/回访 |
| 客服总览 `workbench.png` | `/desk?view=overview`，客服身份访问 `/` 也显示总览 | `DeskOverview.tsx`：深色导航、问候、四个已加载记录计数、案例筛选/搜索和真实会话入口 |
| 客服会话 `case-detail.png` | `/desk?conversation=<id>`，原 `/desk` 保持可用 | 原会话列表、消息、内部备注与协作面板；单一关联案例时用真实案例标题/状态/版本/设备链接补齐顶部信息层级 |

`App.tsx` 与 `ServicePage.tsx` 负责共用页头、当前身份、原有访问保护；新增 `StaffNavigation.tsx`。视觉分为 `base.css` 令牌和基础控件、`workspace.css` 业务组件、`surfaces.css` 参考图页面组合。沿用 React、TypeScript、Router、TanStack Query 和 Lucide，没有更换技术栈或修改依赖锁。

## 兼容性与业务保护

- `frontend/src/api/client.ts`、`schema.d.ts`、`contracts/openapi.json` 与重构前逐字节相同，`git diff` 无这些文件或后端代码、迁移、环境配置改动。未运行 API 重新生成。
- 原消息提交 body、公开/内部可见性、按会话和身份保存草稿、稳定消息编号重试、归档禁用、旧到新分页、滚动跟随、SSE 和历史补取均保留。
- 人工任务、策略切换、草稿审阅、UI action 过期/版本/原编号恢复、图片上传检查与授权查看、模拟动作审批/回执、客户结果核验、回访同意/预约均沿用原组件和 Client。
- 首页新问题调用原 `POST /api/v1/conversations`，请求体仍为 `{}`，建立独立会话；问题只作为待确认草稿带入原编辑器，不自动发消息、创建案例或宣布诊断成功。失败保留草稿。既有案例继续从“我的服务”进入。
- 页面不会根据设备类型或同一客户推断会话与案例关系；只有真实 case-summaries 和消息中的 related_case_id 提供关联依据。
- 所有按钮调用现有业务处理或实际导航；planned API、虚拟全局搜索、假电话、假物流和假文章列表均未加入。
- 详细模块、Client、HTTP 路由和后端处理函数见 [UI 与真实后端接口对照](ui-backend-map.md)。

## 实际验证

| 检查 | 结果与范围 |
|---|---|
| 改动前 `PLAYWRIGHT_CHANNEL=chrome npm run test:browser` | 原有 70 项通过。初次未指定 Chrome 时因本机没有 Playwright 捆绑浏览器而无法启动；选择已安装 Chrome 后建立有效基线。 |
| 新流程先失败再实现 | 首页草稿交接、客服总览筛选先失败；后续增加新问题必须独立会话的断言，先捕获旧复用行为，再修正。 |
| `npm run check:api` | 通过，生成类型与当前 OpenAPI 一致。 |
| `npm run typecheck` | 通过，应用及浏览器测试 TypeScript 均检查。 |
| `npm run build` | 通过，1647 modules；JS 414.20 kB/gzip 124.73 kB，CSS 50.71 kB/gzip 10.57 kB。 |
| 最终 `PLAYWRIGHT_CHANNEL=chrome npm run test:browser` | **81 项全部通过**：70 项既有回归、11 项新增流程/错误/权限/布局检查。测试在独立 5174 服务使用受控 HTTP 响应，不写入当前预览业务数据库。 |
| Axe 与手机溢出 | 上述用例包含 12 组桌面/手机 WCAG2A/AA、WCAG2.1AA 扫描，均无违规；新增页面检查页面宽度未超出视口。 |
| 真实 API 浏览器读取 | 5173 页面通过 8000 API 显示既有合成演示记录：客户首页、指定服务会话、指定案例详情，以及客服总览/指定会话；核对身份切换、客户侧不出现内部备注、客服侧可见原内部备注及协作策略。 |
| 资源来源 | `embed-prompt --scan frontend/public/images`：1 raster，0 missing。图片准确生成提示与来源见 [装饰素材说明](assets/service-room.md)。 |
| 视觉独立复核 | 第一轮指出两处无效/溢出截图及案例列结构、会话顶部层级、对比度、旧文档问题；修正后第二轮完整复核 10 张截图，结论 **ship**，此前问题均 resolved。未运行设计 detector。 |

本轮没有重跑真实后端写入闭环或完整后端测试套件。消息、冲突、上传及审批等写入恢复的本轮证据来自受控前端回归；不能把此记录称为整个后端或生产环境验收。

## 两轮视觉核验与截图

桌面视口 1448×1086，手机 390×844。桌面截取当前视口，手机保存整页；浏览器滚动条会影响 PNG 的可见内容宽度。第一轮中诊断桌面截图在调整尺寸后过早截取，客服总览手机表格的绝对定位无障碍文本导致页面横向溢出，均明确记录并重拍。第二轮截图已独立确认可用。

第二轮文件位于本地 `.impeccable/review/reference-round2/`，此目录按现有忽略规则不提交：

| 页面 | 桌面 | 手机 |
|---|---|---|
| 客户首页 | `home-desktop.png` | `home-mobile.png` |
| 诊断会话 | `support-desktop.png` | `support-mobile.png` |
| 案例详情 | `case-desktop.png` | `case-mobile.png` |
| 客服总览 | `overview-desktop.png` | `overview-mobile.png` |
| 客服会话台 | `desk-desktop.png` | `desk-mobile.png` |

已还原暖色家居氛围、深蓝文字、蓝色操作、白色圆角面板、导航与各页面的列结构；同时保留真实功能较多时的滚动和手机视图切换。

## 保留的差异与尚未验证项

1. 本机未配置模型 Provider；诊断、建议和交互卡只展示后端实际返回结果，不能演示真实模型推理。后端接入模型后继续使用现有消息/事件接口。
2. 无真实设备照片、保修、物流、客服头像/电话、文章阅读数和诊断概率接口。采用中性设备图标、真实记录或省略这些区域；不复制参考图中的人物、型号、比例与数字作为用户数据。
3. 后端未提供完整维修阶段时间线或站点 KPI。进展仅使用提交时间、当前状态和真实动作/核验/回访记录；计数明确为当前已加载授权记录（案例列表最多 50 条）。
4. 模拟售后操作继续明确标记“模拟”，不连接真实 Anker 系统。未进行生产部署或对外发布；热更新服务保持 5173 运行。
5. 最新后端基线此前的完整 CI 存在既有失败，见已有预览说明。本轮未触及或修复后端，也不据前端测试宣布其通过。
