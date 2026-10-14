---
name: 售后通
description: 延续现有品牌的中文服务工作界面
colors:
  accent: "#3267f4"
  accent-hover: "#244fc7"
  accent-soft: "#eaf0ff"
  ink: "#14243d"
  muted: "#5f6f83"
  surface: "#fff"
  canvas: "#f7f5f2"
  border: "#e2e7ef"
  danger: "#a7332b"
  success: "#24634b"
  status-neutral: "#385077"
  status-neutral-soft: "#edf2fa"
  status-success-soft: "#e8f3eb"
  status-warning: "#825520"
  status-warning-soft: "#fff1d9"
  status-danger-soft: "#fcece9"
typography:
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
  tag: "4px"
  control: "8px"
  panel: "12px"
  elevated: "16px"
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
    backgroundColor: "{colors.accent}"
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
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  navigation-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-hover}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
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

沿用已有品牌的蓝色操作、深色文字、白色工作表面与客户侧暖色画布。界面服务中文日常操作：客户侧留出阅读空间，客服侧将会话、回复与案例资料聚合为更紧凑的工作区。

深浅表面、轻描边和明确的文字状态承担信息分组。设备页面呈现授权的只读档案与已核验事实；视觉材料不制造诊断、进度或业务完成感。名称与材料来自既有工程，不引入第二套品牌。

**Key Characteristics:**

- 同一品牌在客户侧保持温暖，在客服侧提高信息密度。
- 中文系统字体、紧凑标题、蓝色选择与操作反馈。
- 白色分栏表面、圆角控件、低强度层级。
- Lucide 线性图标、可见焦点、文字辅助状态。

记录依据为当前 `frontend/src/styles/base.css`、`workspace.css` 与对应组件。六张 adaptation 桌面/手机截图是本轮评审材料；受控无障碍回归和真实 API 浏览器 CI 的状态应在验收记录中分别报告，本文不将待验的 CI 记为已完成。

## Colors

一组稳定的品牌蓝配合暖中性色；状态色承担事实解释，不扩充为新的装饰品牌。

### Primary

- **服务蓝**（`accent`）：主要发送按钮、品牌图标、键盘焦点与选择反馈。
- **沉稳蓝**（`accent-hover`）：链接、激活导航及主要按钮悬停。
- **淡蓝选择面**（`accent-soft`）：已选列表、导航与筛选，避免整块内容被高饱和蓝占据。

### Neutral

- **深墨文字**（`ink`）：标题、主要内容和已读取事实。
- **灰蓝辅助文字**（`muted`）：时间、来源、辅助说明与次要导航。
- **白色工作面**（`surface`）：会话、资料、设备档案和输入控件。
- **暖纸画布**（`canvas`）：客户侧页面底色。
- **柔和边界**（`border`）：分栏边界、内容分隔和卡片轮廓。

### Semantic States

- **成功绿**与对应浅面（`success`、`status-success-soft`）：已核验、已解决、已完成、已批准。
- **等待棕**与对应浅面（`status-warning`、`status-warning-soft`）：待核验、等待、待审阅、待处理。
- **拒绝红**与对应浅面（`danger`、`status-danger-soft`）：错误、已拒绝与已撤销。
- **中性灰蓝**与对应浅面（`status-neutral`、`status-neutral-soft`）：其余状态。

**The 文字状态 Rule.** 颜色须与真实状态文字一起出现；状态色不单独证明操作成功。

## Typography

**Body Font:** Segoe UI → Microsoft YaHei UI → PingFang SC → sans-serif。标题、正文、标签共用现有中文系统字体栈，不加载新的展示字体。

**Character:** 以可持续阅读和表单操作为中心。标题靠字号、字重与紧凑行高建立层级，编号、时间与统计辅助文字使用等宽数字排布，长文本允许换行。

### Hierarchy

- **Headline**：页面标题使用前置规范中的标题角色；客户服务标题在桌面增至 30px，手机统一为 23px。设备详情标题桌面为 26px，手机为 22px。
- **Title**：会话与侧栏分区标题使用标题角色；资料区标题为 15px，会话标题手机为 15px。
- **Body**：默认正文使用正文角色。保留当前实际 14px 基线，不将草案中的 16px 冒充实现。
- **Label**：输入标题与短操作说明使用标签角色；常规按钮字重为 600。
- **Status / metadata**：状态标签使用状态角色；元数据以 11–12px 呈现，仅承载辅助信息，不用于主要问题描述。

## Layout

外层容器最大宽度为 1680px；桌面主区左右内边距为 28px，顶部为 16px，页头最小高度为 66px。内容使用普通文档流、grid 与局部滚动，长编号和事实值可换行。

桌面会话布局为 250px 列表 / 自适应会话 / 340px 资料，间隔为 14px；无资料时保留前两栏。整体高度为 `calc(100dvh - 245px)`，最小高度为 650px。列表、消息区与资料区分别允许纵向滚动。客户侧标题与阅读区更松，客服侧沿用相同组件语言。

761–1200px 下会话成为 230px 列表 / 自适应会话，资料移到下方，以最小 270px 单元自动排布。消息滚动区最大高度为 520px。760px 及以下主区水平内边距为 14px，页头导航换行；会话改为列表 / 会话 / 资料三种视图，当前视图仅显示对应区域。会话面板最小高度为 530px，消息滚动区最大高度为 490px，最小为 260px；输入操作竖排并拉满宽度。

设备桌面为 280px 列表 / 自适应详情，间隔为 18px。手机上下排列，设备列表内部可横向滚动，事实从两列变为单列，历史条目竖排。间距不被强制压成单一比例：前置规范记录复用尺度，14px、18px 等保留为现有布局的局部值。

**The 服务连续性 Rule.** 手机切换改变显示区域，按会话保存的草稿继续保留；不把切换视图当成重新开始服务。

## Elevation & Depth

常规工作面采用边界与轻微色调差异表达层级，列表选中、自己发送的消息和内部备注各有独立表面。客服画布当前为较冷的 `#f3f5f9`；消息阅读区和设备标题区使用 `#fcfdff`。这些为局部表面，不另建品牌色组。

### Shadow Vocabulary

- **登录表面**：`0 12px 36px rgba(20,36,61,.06)`，仅现有登录卡使用轻柔环境阴影。

**The 轻层级 Rule.** 工作栏与消息优先使用边界和色调分组；不向所有卡片扩散登录卡的阴影。

## Shapes

控件采用前置规范中的 control 圆角；会话、资料、设备档案采用 panel 圆角；登录卡采用 elevated 圆角。短私有标识采用 tag 圆角，状态使用 pill 圆角。描边通常为 1px。

消息以 12px 主圆角配合一侧 3px 小角表达方向：收到的消息小角位于左下，发送的消息位于右下。此形式为会话特征，不扩散为普通卡片形状。

## Components

### Buttons

清晰、紧凑的操作控件。主要按钮采用服务蓝与白字，次要按钮采用白面与深墨文字，圆角和内边距遵循前置组件规范。桌面默认最小高度为 40px，手机通用按钮默认最小高度为 44px；既有小型辅助与筛选按钮仍有显式覆盖。

悬停改变背景和边界，主要按钮转为沉稳蓝。禁用时使用灰色文字、浅灰面和不可用光标。焦点统一为 3px 服务蓝轮廓、3px 偏移；不移除键盘可见反馈。

### Chips

状态为紧凑胶囊标签，用文字和语义色共同表达状态。标签本身不承担点击操作。会话筛选使用按钮与 `aria-pressed`；选中为淡蓝表面、沉稳蓝文字和加重字重。

### Cards / Containers

白色面、柔和边界和 panel 圆角构成常规容器。资料摘要与协作区常用 20px 内边距；设备详情在桌面采用 28px / 32px 边距，手机为 22px。无需为所有容器添加统一阴影。缺失数据以明确空态呈现，而非占位统计。

### Inputs / Fields

白色面、1px `#b7c3d4` 边界、control 圆角；内边距遵循前置 input 规范。搜索框采用较淡局部背景、左侧 Lucide 搜索图标与明确可访问名称。文本域可纵向缩放，基础最小高度为 88px。

焦点遵循全局轮廓。错误文字使用拒绝红并允许长错误信息换行；不得仅靠边框色表达错误。归档会话中的输入明确禁用，显示无法继续发送的说明。

### Navigation

桌面导航横排，默认灰蓝文字；悬停与激活使用淡蓝面和沉稳蓝文字，激活字重为 700。手机导航换行并均匀分配，工作区切换采用独立的分段按钮和按下状态。列表当前项有选中色面、细边界与当前位置语义。

### Messages / Private Notes

消息文本保留换行，桌面气泡最大宽度为 `min(85%, 620px)`，手机为 95%。自己发送的消息使用浅蓝面和右对齐，内部备注使用暖浅黄面、私有锁图标和“内部备注”文字。发送失败与重试位于消息附近，不将异步受理绘成已完成。

### Read-only Device Record

Lucide 设备线性图标用于通用档案识别，不代表真实产品图片。身份核验标签、型号、遮蔽后的设备标识、事实来源和关联历史组成只读详情。未知型号和未提供信息直接说明；不可访问的详情显示权限或读取错误，避免旧数据继续形成视觉事实。

### Motion

交互仅使用 150ms 的背景、边界与文字颜色过渡。尊重 `prefers-reduced-motion: reduce`，关闭过渡、动画和滚动动效。

## Do's and Don'ts

### Do:

- **Do** 沿用前置规范中的品牌蓝、深墨文字、白色工作面与中文系统字体。
- **Do** 用文字、图标和色调共同标识状态、内部备注和权限边界。
- **Do** 保留全局键盘焦点、可访问标签、跳转到主内容的入口和减少动态效果设置。
- **Do** 在手机保持会话草稿、输入操作与明确的视图切换。
- **Do** 在设备档案展示真实授权记录、事实来源、核验状态和遮蔽标识。

### Don't:

- **Don't** 引入第二套品牌色、新的展示字体或营销式巨型标题。
- **Don't** 将参考图里的样例姓名、诊断、统计或完成进度作为业务数据。
- **Don't** 仅靠颜色表达成功、拒绝或未知结果。
- **Don't** 将只读设备档案扩展成未实现的编辑或诊断操作。
- **Don't** 将已加载会话的本地筛选描述为搜索整个后端。
