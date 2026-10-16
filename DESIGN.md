---
name: 售后通
description: 延续现有品牌的中文服务工作界面
colors:
  accent: "#2860ff"
  accent-hover: "#214ed0"
  accent-soft: "#edf2ff"
  ink: "#10213c"
  muted: "#59677d"
  surface: "#fff"
  canvas: "#f8f6f3"
  warm: "#fff0e3"
  own-message: "#ffead8"
  staff-rail: "#172331"
  border: "#e9ecf2"
  danger: "#a7332b"
  success: "#24634b"
  status-neutral: "#385077"
  status-neutral-soft: "#edf2fa"
  status-success-soft: "#e8f3eb"
  status-warning: "#825520"
  status-warning-soft: "#fff1d9"
  status-danger-soft: "#fcece9"
typography:
  display:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "clamp(36px, 3.6vw, 54px)"
    fontWeight: 750
    lineHeight: 1.25
    letterSpacing: "-.025em"
  headline:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "26px"
    lineHeight: 1.35
    letterSpacing: "-.025em"
  title:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "17px"
    lineHeight: 1.35
  body:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.6
  status:
    fontFamily: '"Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.5
rounded:
  flat: "0"
  tag: "4px"
  control: "8px"
  panel: "12px"
  elevated: "16px"
  entry: "15px"
  pill: "99px"
spacing:
  compact: "4px"
  small: "8px"
  medium: "12px"
  regular: "16px"
  panel: "20px"
  large: "24px"
  section: "28px"
  spacious: "32px"
components:
  button-primary:
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-secondary-hover:
    backgroundColor: "{colors.accent-soft}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 11px"
  navigation:
    textColor: "{colors.ink}"
    rounded: "{rounded.flat}"
    padding: "8px 14px"
  navigation-active:
    textColor: "{colors.accent-hover}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  message-own:
    backgroundColor: "{colors.own-message}"
    textColor: "#25313c"
    padding: "12px 15px"
  status-neutral:
    backgroundColor: "{colors.status-neutral-soft}"
    textColor: "{colors.status-neutral}"
    typography: "{typography.status}"
    rounded: "{rounded.pill}"
    padding: "3px 8px"
  status-success:
    backgroundColor: "{colors.status-success-soft}"
    textColor: "{colors.success}"
  status-warning:
    backgroundColor: "{colors.status-warning-soft}"
    textColor: "{colors.status-warning}"
  status-danger:
    backgroundColor: "{colors.status-danger-soft}"
    textColor: "{colors.danger}"
---

# Design System: 售后通

## Overview

**Creative North Star: "持续服务工作台"**

延续售后通的品牌蓝、深墨中文文字与白色工作面，并以用户指定的五张参考图作为页面构图依据。客户侧使用暖纸画布、宽幅室内照片与舒展的问题入口；客服侧以深色导航栏、真实记录计数、案例表格和并列沟通区提高信息密度。

圆角白面、轻描边和低强度阴影组织内容，浅桃色气泡区分自己发送的消息。装饰照片建立温暖的服务环境；设备身份、服务状态、证据与诊断内容仍由授权业务记录决定。

**Key Characteristics:**

- 暖色客户页面与深色客服导航共享同一品牌。
- 中文系统字体、宽幅场景引导、蓝色操作与下划线导航。
- 白色圆角分栏、浅桃色自发消息、低强度表面阴影。
- 真实数据、可见焦点和文字状态共同维持服务连续性。

本规范按 `frontend/src/styles/base.css` → `workspace.css` → `surfaces.css` 的实际加载顺序和对应 React 组件提取。最终第二轮十张截图的视觉评审结论为 ship；81 项受控浏览器测试、12 次无障碍扫描及构建检查通过。截图模式、真实 API 只读检查和未重跑实时写入闭环的边界详见 `docs/reference-ui-surface.md`；本轮未运行 detector，亦未配置真实 AI 提供方。

## Design references and project fit

Use mature design systems as references for interaction grammar and component boundaries, while keeping the warm ivory, navy, and service-blue identity established by the supplied reference images. Do not import a reference product's brand palette or visual skin wholesale.

| Reference | Borrow | Apply here |
|---|---|---|
| [Atlassian Design System — navigation layout](https://atlassian.design/components/navigation-system/layout) | Separate app navigation, page content, and contextual areas; make navigation responsive and keep its hierarchy predictable. | Keep customer navigation simple. Use the staff rail and queue as work-area navigation, with the conversation and case context in distinct content regions. |
| [Atlassian Design System — lozenge](https://atlassian.design/components/lozenge) | Give status labels stable semantic meanings such as success, warning, danger, and information. | Map labels to actual Case, Conversation, evidence, action, and verification states. Always show the status text; color alone is never a state. |
| [GitHub Primer — components](https://primer.style/product/components/) | Reusable status labels, timelines, and underline navigation for dense workflow interfaces. | Reuse the same status, progress, and navigation patterns across customer and staff surfaces, with role-appropriate density. |

These are pattern references, not dependencies to install. The frontend remains the existing React, TypeScript, CSS, Router, TanStack Query, and Lucide application. Favor native semantic controls and the existing component catalog over adding a second component framework.

## Premium quality rules

“Premium” means calm, legible, precise, and consistent; it does not mean adding visual effects to every surface.

- Keep one primary action per visible region. Secondary actions use a quiet outline or text treatment.
- Use warm canvas, white work surfaces, navy text, and the existing service blue. Peach is reserved for the customer's own messages and warm service guidance; semantic status colors keep their operational meaning.
- Use thin dividers and low, soft shadows to separate surfaces. Avoid stacked shadows, heavy borders, pervasive gradients, glass blur, decorative glow, and oversized card radii.
- Keep Chinese system typography. Use a small, predictable type scale, readable line length, and aligned numeric metadata. Do not add an external display font solely to signal luxury.
- Use Lucide SVG icons with consistent stroke weight and size. Never use emoji as interface icons. Icon-only buttons need an accessible name and visible focus state.
- Reserve photography for the home-page atmosphere. Conversation, evidence, and device identity surfaces should prioritize actual records and readable text.
- Keep customer and staff density intentionally different while sharing spacing, controls, surfaces, status semantics, and focus treatment.

## Asset library and provenance

Maintain a small curated library rather than collecting assets before the interface needs them. Every shipped raster must have an owner/source, intended use, alt-text rule, and provenance record.

| Asset class | Source of truth | Rendering rule |
|---|---|---|
| Brand mark | Approved product artwork; use the current text mark until supplied | Do not redraw or invent a logo from the reference image. |
| Interface icons | Existing `lucide-react` dependency | Keep stroke weight and optical size consistent; hide decorative icons from assistive technology. |
| Decorative room image | `frontend/public/images/service-room.png`, with prompt in `docs/assets/service-room.md` | Atmosphere only; never present it as a customer room, product image, or diagnostic evidence. |
| Product photo guide set | Three `frontend/public/images/product-*-guide.png` images, with prompts and usage rules in `docs/assets/product-photo-guide-set.md` | Upload guidance only; the UI labels them as examples, never evidence or real devices. |
| Device identity image | No general device-photo feed is established by the current contract | Use a neutral device icon until a real authorized image source exists. Do not substitute generated product photos. |
| Customer evidence | Authorized evidence content endpoint after the server permits access | Show the actual inspection state; do not expose uninspected or unauthorized content. |
| User and staff avatars | No authoritative avatar source is established in the current contract | Use a neutral initials/icon fallback, not a fabricated person. |

Keep reference screenshots grouped by date under `docs/design-references/` as review material only. The 2026-10-17 customer session set is indexed at `docs/design-references/2026-10-17-customer/README.md`; the earlier 2026-10-13 set remains in its original folders. Do not use screenshots as page backgrounds or copy their names, case IDs, device facts, status, metrics, or service promises into UI fixtures presented as real records.

## Reference-image translation

The image set has several compositions of the same service journey. Treat them as responsive and state variants rather than competing page specifications:

1. **Customer home / history:** brand header and account control; greeting and new-conversation action; searchable, filterable service list; selected conversation or case summary. On wide screens use master-detail; on narrow screens show one panel at a time.
2. **Customer conversation:** conversation selector, message thread, evidence/request card, composer, and a contextual service panel. The thread remains the visual center; status and next step come from authorized records or published UI documents.
3. **Customer service detail:** case identity header, actual progress, evidence, associated device, verification, and follow-up. A three-column desktop arrangement may collapse into stacked sections on smaller screens.
4. **Staff overview:** work navigation, scoped record counts, search/filter controls, and case queue. Counts must be labeled as the currently loaded authorized set.
5. **Staff conversation:** queue, conversation, and authorized case/collaboration context. Internal notes must be visibly distinct from public messages.

Never force a one-to-one relationship between Conversation and Case to make the composition easier. The sidebar can display multiple case summaries returned by the API.

## Visual review handoff

Review one representative desktop and mobile capture for each of the five surfaces. Check these in order:

1. **Hierarchy:** page title, primary task, current status, and next action are immediately distinguishable.
2. **Consistency:** shared controls, spacing, text roles, borders, and status labels look like the same product across routes.
3. **Truthfulness:** every visible business value maps to an authorized API field or persisted event; unavailable data is omitted or explicitly unavailable.
4. **Interaction:** loading, empty, error, pending, denied, stale-version, and disconnected states remain understandable and recoverable.
5. **Responsive and accessible behavior:** no page-level horizontal overflow; keyboard focus is visible; touch targets remain comfortable; reduced motion is respected; status is not color-only.

The current reference rebuild has its own dated evidence in `docs/reference-ui-validation.md`. This checklist is for future visual changes and does not retroactively claim new screenshots or acceptance.

## Colors

服务蓝负责操作和选中反馈，暖纸与浅桃色缓和客户会话，深色导航帮助客服区定位。

### Primary

- **服务蓝**（`accent`）：品牌操作、活动导航下划线、焦点和当前状态节点。
- **沉稳蓝**（`accent-hover`）：链接、激活文字和主要按钮悬停。
- **淡蓝选择面**（`accent-soft`）：列表选中、筛选和辅助图标背景。

### Neutral

- **深墨文字**（`ink`）：标题、正文和业务事实。
- **灰蓝辅助文字**（`muted`）：时间、来源和次要说明。
- **白色工作面**（`surface`）：表单、卡片、会话与资料。
- **暖纸画布**（`canvas`）：客户页面底色。
- **柔和边界**（`border`）：控件与分栏边界。
- **暖杏图标面**（`warm`）：头像与圆形服务图标。
- **浅桃消息面**（`own-message`）：右对齐的自己发送消息。
- **客服深色栏**（`staff-rail`）：客服导航背景。

成功绿、等待棕、拒绝红和中性灰蓝及其浅面沿用前置规范中的语义 token，只表达服务器或明确本地状态。

**The 文字状态 Rule.** 颜色须与真实状态文字一起出现；状态色不单独证明操作成功。

## Typography

**Body Font:** Segoe UI → Microsoft YaHei UI → PingFang SC → sans-serif。标题、正文和控件沿用中文系统字体；现有装饰题字使用本机 KaiTi / STKaiti / serif 回退，不下载字体。

**Character:** 以中文阅读、表单操作与客服扫描为中心。客户首页采用较大的问候标题；业务详情和工作台保持紧凑层级。编号、时间和记录计数使用等宽数字排布，长业务文本允许换行。

### Hierarchy

- **Display**：首页问候标题使用前置 display 角色，手机为 35px；其宽度与行高服务于参考图的宽幅问题入口。
- **Headline**：通用页面标题使用前置 headline 角色。服务会话横幅桌面为 36px、手机为 27px；客服总览为 32px / 24px；案例身份标题为 26px / 20px。
- **Title**：分区标题通常为 17–19px；案例内容标题为 18px。客服会话标题为 20px，手机为 16px；客户会话手机为 14px。
- **Body**：正文基线为前置 body 角色；首页引导为 17px，详情段落通常为 13px、1.85 行高。
- **Label / status**：控件标签与状态使用前置角色。11–12px 元数据承载辅助信息，主要问题和操作保持更清楚的层级。

## Layout

页头与主容器最大宽度为 1800px；桌面页头最小高度为 90px、内边距为 16px 34px。页脚仍以 1680px 为最大宽度。页面内容由各 surface 决定内边距，不能沿用旧版全局 28px 主区假设。

客户首页以最小 395px 高的室内场景横幅和左侧问题表单建立首屏；六类问题为六列，服务与设备区为 1.35:1 两列。服务会话采用左侧会话 / 右侧 350px 资料区，18px 栏距；会话选择器折叠为左侧摘要行。步骤条仅概括服务路径，具体状态仍看实际记录。

客服壳层采用 176px 深色导航栏；总览为四个记录计数、案例表格和 340px 协作区。客服会话在导航栏内采用 246px 会话列表 / 自适应聊天 / 330px 资料，12px 栏距，最小高度为 690px；1600px 及以上列表和资料分别增至 280px / 370px。

案例详情采用宽幅身份条、三段记录概况以及三列内容（1.35fr / 1fr / minmax(270px, .85fr)），18px 栏距。左列为进展与模拟动作，中列为问题和证据，右列为服务协作、结果核验和跟进；不把此页面构图强加给所有资料页。设备页保留 280px 列表 / 自适应只读详情。

761–1280px 下客服导航收至 146px，客服资料移到两列会话下方；客户会话资料为 300px。761–1000px 下总览统计为两列，表格与协作区上下排列，问题类型为三列，案例详情改为单列。760px 及以下，客服栏成为横向导航；首页问题类型两列、下部面板单列；案例概况与详情单列。会话提供列表 / 聊天 / 资料切换，当前视图仅显示对应区域，聊天面板最小高度为 560px。表格在自身容器内横向滚动，设备列表内部横向滚动。

**The 服务连续性 Rule.** 手机切换改变显示区域，按会话保存的草稿继续保留；不把切换视图当成重新开始服务。

## Elevation & Depth

表面由暖冷色调、柔和边界与轻微环境阴影共同区分。客服画布为冷浅灰，客户阅读区为暖浅灰；资料以独立白色面板纵向组合。主要按钮使用轻微蓝色渐变与阴影，仍保持明确的单一操作层级。

### Shadow Vocabulary

- **常规表面**：`0 6px 24px rgb(30 43 67 / 3%)`，用于首页卡片、总览统计、设备详情等复用表面。
- **问题入口**：`0 8px 35px rgb(72 52 24 / 5%)`，用于首页问题表单。
- **主要按钮**：`0 4px 10px rgb(40 96 255 / 10%)`。
- **展开会话列表**：`0 16px 30px rgb(20 30 50 / 12%)`，用于桌面客户会话选择器浮层。
- **登录表面**：`0 12px 36px rgba(20,36,61,.06)`。

**The 轻层级 Rule.** 阴影用于低强度分组；聊天消息和资料优先保持清楚的表面关系。

## Shapes

控件沿用 control 圆角，主要工作面沿用 panel 圆角，首页问题入口采用 entry 圆角，登录卡采用 elevated 圆角。头像、服务图标和步骤节点为圆形；状态使用 pill 圆角，私有标识使用 tag 圆角。描边通常为 1px。

消息采用 12px 主圆角与顶部一侧 3px 小角：收到消息在左上，自己发送消息在右上。内部备注采用浅黄面与虚线边界，并保留锁图标和文字标识。

## Components

### Buttons

蓝色主要操作采用 `linear-gradient(115deg, #3d74ff, #2455f4)`、白字与服务蓝边界；悬停转为沉稳蓝。次要按钮为白面深墨字，悬停为淡蓝面。默认最小高度为 40px，通用手机按钮为 44px；首页启动按钮为 48px，显式小型控件保留局部覆盖。

禁用控件使用浅灰面、灰字和不可用光标。全局键盘焦点为 3px 服务蓝轮廓、3px 偏移；文本域保留适配局部空间的偏移覆盖。颜色过渡为 150ms，并尊重减少动态效果设置。

### Chips

状态为文字加语义色的紧凑胶囊，不承担点击操作。会话筛选采用按钮及 `aria-pressed`；总览状态筛选采用下划线选中指示。

### Cards / Containers

白色面、柔和边界与圆角构成常规容器。首页和总览使用低强度阴影；客服资料由多个独立白色卡片组成。常见内边距为 20–23px，手机通常为 20px。加载、空态和失败以文字明确呈现。

### Inputs / Fields

基础输入为白色、1px `#b7c3d4` 边界、control 圆角与前置 input 内边距。首页问题入口和客服回复区采用更轻的边界；客户回复区仍有独立描边。搜索有明确可访问名称。错误显示可换行的文字；归档会话输入禁用并说明原因。

### Navigation

桌面页头为横排文字导航，以蓝字和蓝色下划线表示当前页。客服深色栏采用浅字、线性图标、蓝色选中面与左侧细亮线。手机页头换行，客服栏横排；列表与当前工作视图保持可访问的当前位置或按下状态。

### Messages / Private Notes

消息保留换行，桌面气泡最大宽度为 `min(85%, 620px)`，手机为 95%。自己发送的消息右对齐并使用浅桃面；收到消息为浅灰面，客户会话中为白面。内部备注使用浅黄面、虚线、锁图标和“内部备注”文字。发送失败和重试靠近消息，不把受理状态绘成完成。

### Room Hero / Record Identity

同一室内照片服务首页、客户会话横幅、客服问候和案例身份条，以渐变覆层保证正文可读。照片为生成的装饰资产，来源记录位于 `docs/assets/service-room.md`；照片不代表真实产品、设备档案或客户环境。设备与案例使用通用线性图标和真实文本识别。

### Record Counts / Case Table

总览数字由已加载的案例、会话和设备记录计算，不能解释成全站或实时运营指标。案例接口最多返回 50 条，页面保留范围说明；本地搜索与筛选只作用于已加载记录。未知、加载和失败分别使用省略号、破折号或错误文字，不能补入参考图样例数字。

## Do's and Don'ts

### Do:

- **Do** 沿用前置规范中的品牌蓝、深墨文字、暖纸画布与中文系统字体。
- **Do** 遵循已批准参考图的页面层级，并以真实授权记录填充内容。
- **Do** 保留全局键盘焦点、可访问标签、跳转入口和减少动态效果设置。
- **Do** 在手机保持会话草稿、输入操作与明确的视图切换。
- **Do** 区分装饰照片、通用设备图标和真实设备身份记录。

### Don't:

- **Don't** 引入第二套品牌或下载新的展示字体来替代当前参考方向。
- **Don't** 将参考图里的样例姓名、诊断、统计或完成进度作为业务数据。
- **Don't** 仅靠颜色表达成功、拒绝或未知结果。
- **Don't** 将只读设备档案或模拟售后动作描述为真实外部服务执行。
- **Don't** 将已加载记录的本地筛选描述为搜索整个后端。
