# 售后通视觉系统与组件基础

状态：第一轮视觉基线提案，源自手机优先双端原型，待客户/客服整体评审  
目标：给客户和客服体验建立一致、可扩展的视觉语言；本文件不是已实现的 CSS 或已批准的品牌标准。主要交互稿见[手机优先双端原型](prototypes/mobile-first-review.html)。

## 1. 视觉原则

1. **可信的精致感**：依靠排版、比例、留白和细节建立品质，不依赖大量渐变、阴影或玻璃拟态。
2. **品牌统一、密度分层**：客户侧舒展；客服侧信息紧凑但清楚。两端共享颜色语义、表单、按钮、图标与状态系统。
3. **有意义的层级**：主操作只有一个；次要操作不抢焦点；业务时间线真有先后时才使用连接线/编号。
4. **事实可读**：来源、可信度、处理状态都明确标注，不能用强烈颜色或大字号制造事实确定性。
5. **系统性细节**：所有可交互组件覆盖默认、hover、focus、pressed、disabled、loading、error、success 状态。

## 2. 色彩 token 提案

以下 hex 是初步可执行的设计 token 草案；进行页面原型评审时可微调，不能直接在组件内散落原始色值。

| Token | 提案值 | 使用方式 |
|---|---|---|
| `canvas` | `#F7F6F2` | 参考图中偏暖的明亮画布 |
| `surface` | `#FFFFFF` | 对话、资料、表单主表面 |
| `surface-subtle` | `#EEF3FA` | 选中项、次级信息区域 |
| `ink` | `#14223B` | 主文字/标题，深蓝黑 |
| `muted` | `#5F6F87` | 辅助说明和时间 |
| `brand` | `#1769F5` | 主要按钮、链接、当前选中 |
| `brand-strong` | `#0D52D6` | hover/pressed |
| `brand-soft` | `#E9F1FF` | 蓝色弱提示和选中底 |
| `success` | `#0D8F80` | 核验通过、成功 |
| `warning` | `#B76A09` | 等待客户、待处理、需留意 |
| `danger` | `#C43D4B` | 明确失败或风险 |
| `border` | `#E5E5E3` | 分隔、输入框、轻边界 |

原则：文本对比按 WCAG AA 检查；状态不能只用色相区分，须配合文字、图标或线型。成功绿不表示“已解决”，只有核验记录决定业务解决状态。

## 3. 字体与排版

- 中文正文：优先系统可用的 `PingFang SC`、`Microsoft YaHei UI`、`Noto Sans SC` 等无衬线字体；不得依赖在线字体加载才能正常使用。
- 英文与数字：与中文保持视觉匹配的无衬线字体；时刻、金额、编号等变化数字可使用等宽数字。
- 客户正文和聊天消息以 14–16px 为基准；客服密度更高，但主要内容不低于 14px，紧凑元信息可为 12px。仅装饰性或辅助标签可用 11px，不能用小字承载关键步骤。
- 首轮 type scale：页面标题 30–34px、区块标题 18–20px、组件标题 15–16px、正文/聊天 14–16px、辅助说明 12–13px。长正文行距 1.6–1.75；标题紧凑但避免过度压缩字距。
- 行宽为中文阅读优化。长问题描述和客服草稿不应被无限拉宽；时间、编号等元信息不与标题争夺层级。
- 文案用用户任务描述，不显示 API 枚举、数据库字段或 Agent 生命周期名。

## 4. 布局与间距

- 采用 4px 基础单位，核心节奏使用 8/12/16/24/32px。优先用留白和分隔关系，不把每个信息块变成独立卡片。
- 客户手机首页突出「进入对话」按钮，并以列表入口呈现历史对话和服务记录；服务工作区使用「对话 / 处理详情 / 关联设备」三个轻导航，操作按钮留在对应上下文。
- 手机从单列任务流开始：当前对话优先、历史对话/服务记录/详情可切换；不在窄屏压缩桌面三栏。
- 客服手机端从队列列表开始，进入任务后以单面板切换；消息时间线只显示已经发送的公开内容，AI 建议单独放在客服可见的未发送卡片中，客户可见回复对象持续标注。
- 双端手机评审稿在 [mobile-first-review.html](prototypes/mobile-first-review.html)：客户首页单 CTA；工作区可切换对话、处理详情、关联设备，并从操作区新建对话。客户对话底部将助手/专项诊断参与状态与「人工」按钮并列；前两项是基于真实事件的状态，后者才是操作。客服手机单列切换队列/会话/服务资料；桌面并列显示队列、会话、服务资料。
- 宽桌面工作区可以三列：会话/队列列表、主任务、上下文；为消息正文设可读宽度下限。
- 页面和表面间区分层级：主工作区用背景与留白分区；浮层、弹出菜单和拖拽层才用较强阴影。
- 卡片仅在真实分组或独立操作边界需要时使用。避免每项文字都套白底圆角卡。
- 常用交互目标至少 44×44 CSS px；相邻触控目标留出足够间距。
- 客户桌面服务工作区参考列宽：记录 250–305px、对话自适应且优先、上下文 260–315px；最窄可用聊天宽度应在窄屏时转为独立面板，而不是压缩到不可读。
- 首轮断点：1120px 及以下切换到单面板导航；客户可见「对话 / 处理详情 / 关联设备」，历史对话和服务记录从首页进入；客服可见「处理队列 / 客户会话 / 服务资料」。760px 以下进一步收紧导航与纵向间距。桌面保持分区并列。断点是原型验证值，不是生产适配验收结论。
- 手机验收目标：360×800、375×812、390×844；平板 768×1024；桌面 1280×800。键盘弹出后输入区仍可用，考虑底部安全区，不允许横向溢出。当前单入口版仅在 1260×708 浏览器窗口查看了入口视觉；目标手机视口、面板切换和软键盘状态仍待检查。

## 5. 圆角、边界和图标

- 小控件 8–10px；常规面板 12–16px；圆形只用于头像、状态点或紧凑工具按钮。
- 描边使用低对比中性色；把清晰边界留给输入、可聚焦区域和可交互项。
- 优先使用同一套线性 SVG 图标。图标按钮必须有可访问名称；不使用 emoji 代替业务图标。
- 设备缩略图只有在真实记录存在、且展示有助于识别时才显示；无图像时使用中性占位，不以合成图暗示特定型号。

首轮组件几何提案：输入/普通按钮圆角 10–12px，分组面板 14–18px，欢迎区最多 24px；页面主面板用轻边界和低强度投影，工作区内部优先使用分隔线。小型交互目标至少 44×44 CSS px。

## 6. 组件目录初稿

| 组件 | 变体/职责 | 核心状态 |
|---|---|---|
| `AppShell` | customer/staff；品牌、一级导航、账户 | authenticated / unavailable |
| `PageHeading` | 标题、说明、唯一主操作 | default |
| `ConversationList` | 搜索、状态筛选、最近活动、当前选择 | loading / empty / error / selected |
| `ConversationThread` | PUBLIC 消息、作者、时间、附件和安全提示 | loading history / sending / saved / uncertain / failed |
| `MessageComposer` | 客户文本/附件；客服固定标注回复客户且客户可见 | active / disabled / sending / validation error |
| `ServiceTeamStatus` | 当前轮次真实可见的助手/专项诊断参与状态；含唯一「人工」请求按钮 | processing / participated / waiting / result ready / failed / request pending / accepted |
| `AISuggestion` | 与时间线分离的客服专属未发送建议；来源消息与过期状态可见，插入编辑器不触发发送 | generating / current / stale / inserted / dismissed |
| `ServiceStage` | 当前服务阶段、下一步、等待对象 | active / waiting / resolved / closed / failed |
| `CaseSummary` | Case 问题、真实状态、版本隐藏于操作语境、相关设备 | loading / no linked case / accessible / forbidden |
| `EvidenceItem` | 图像预览、来源、检查与核验状态 | pending inspection / clean / rejected / unavailable |
| `FactRow` | 事实值、来源、候选/核验/撤销 | candidate / verified / retracted |
| `TaskRow` | 人工协助任务和接管状态 | open / claimed / stale conflict |
| `ActionTimeline` | 售后申请、审批、执行、Mock 回执、对账 | waiting approval / executing / unknown / success / failed |
| `VerificationPrompt` | 客户选择 WORKING/NOT_WORKING/UNCERTAIN | pending / submitted / resolved / continue service |
| `FeedbackPrompt` | 未来可选满意度回执；本期不可提交 | planned only |
| `InlineNotice` | info/success/warning/danger，文字+图标 | persistent / dismissible |
| `ProgressiveForm` | 缺失信息和证据采集，说明用途和稍后补充 | incomplete / submitting / accepted / recoverable error |

## 7. 状态、动效和可访问性

- 业务阶段用简洁名词/动词；视觉样式由共享状态 token 渲染，不各页面重复翻译状态。
- 客户显示业务含义。客服可以在展开的诊断/操作详情里读到必要技术状态；不把 Agent trace 或原始推理显示给任一方。
- 动效只反馈状态切换、打开/关闭和保存结果；优先 120–220ms，尊重 `prefers-reduced-motion`。
- 焦点指示清晰，键盘可操作，不依赖 hover；错误信息靠近字段并可被辅助技术读取。
- 上传进度、发送状态、SSE 连接状态和 Case 业务阶段分开展示。
- 客户状态栏不模拟团队成员“在线”；`agent.progress` / `specialist.activity` 只有真实、PUBLIC 且符合当前发布策略的事件才可映射为客户状态。角色名、阶段文字与状态点同时出现。
- AI 建议不是 `ConversationThread` 消息。只有后端保存并允许公开的 Message 才加入客户可见时间线；“放入回复框”仅更新客服本地编辑器，客服显式发送并收到真实回执后才作为已发送消息展示。
- 组件不支持或 UI Schema 失效时提供文本/固定表单 fallback。

## 8. 不做的视觉套路

- 不让页面成为相同圆角卡片的集合。
- 不使用大面积装饰渐变、无数据的仪表盘、虚构的 AI 在线状态、随机百分比或假的服务时间线。
- 不把每个 Agent 进度事件做成聊天气泡。
- 不在未确认图片素材许可或事实前使用真实品牌设备图。
- 不为了“高级”降低字号、对比度或操作反馈。


