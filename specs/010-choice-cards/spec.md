# Feature Specification: 可点击选项卡（ChoiceGroup）

**Feature Branch**: `phase4/choice-cards`
**Created**: 2026-10-15
**Status**: Draft
**Input**: 用户反馈「Agent 的卡片只有文字，能不能给几个选项让用户点」。定位结论见下。

## 背景：为什么现在没有可点的选项

不是坏了，是整条链路上没有任何地方能表达「选项」这个数据结构：

1. `backend/serviceos_api/agents/result.py:50` 要求 `ui_proposal` 的键**恰好**是 `{purpose, audience, fallback_text, component_hints}`——没有选项字段。
2. `backend/serviceos_api/agents/runtime.py:33` 提示词明确写「不包含 props、URL、HTML」——模型想给也无处安放。
3. `backend/serviceos_api/application/services.py:536` 构建卡片时**从不读** `component_hints`，组件类型硬编码成 `QuestionForm`，props 写死为标题加一句 `purpose`。
4. `backend/serviceos_api/application/ui_catalog.py:13,51` 与 `frontend/src/features/ui-document/UIDocumentRenderer.tsx:11,29` 都要求 props 键集合**恰好**等于目录声明，多一个键整份文档判废。

阶段判断：这不在阶段 5。它是阶段 4 漏掉的一项——`docs/development-plan.md:72` 尚未勾选的「用户侧身份/证据/步骤/核验/风险卡与客服侧摘要/Skill/审批/流程卡完整纵切面」的第一个切片。`ChoiceGroup` 此前只作为设计名存在于 `docs/architecture.md:125` 与 `docs/domain-and-contracts.md:235`。

## User Scenarios & Testing

### User Story 1 - 客户点一下就能回答（Priority: P1）

客户在 `/support` 看到 Agent 提出的几个选项，点一下即作为自己的回复发出，不必手打。

**Why this priority**: 这是用户直接反馈的诉求；卡片只有文字时，客户仍要自己组织语言。

**Independent Test**: 真实模型下让 Agent 产出一个带选项的提案，在浏览器里点一项，确认产生了一条普通客户消息且 Agent 继续回话。

**Acceptance Scenarios**:
1. **Given** 提案带合法 `options`，**When** 客户查看会话，**Then** 卡片渲染出可点击选项，且「服务交互卡」区域同时保留文字输入。
2. **Given** 客户点了一项，**When** 请求成功，**Then** 该选项作为一条 CUSTOMER/PUBLIC 消息持久化，Agent 像收到手打消息一样回应。
3. **Given** 文档已过期、revision 回退或组件不在目录中，**When** 客户查看，**Then** 选项禁用并走现有降级（刷新按钮 + 文字路径）。

### User Story 2 - 选项不能成为新的越权面（Priority: P1）

维护者确认选项点击没有新增任何服务端写入口子。

**Why this priority**: 这是本切片唯一的实质性风险。

**Independent Test**: 检查点击路径确实只走已存在的消息接口，且动作白名单未被放宽。

**Acceptance Scenarios**:
1. **Given** 选项点击，**When** 观察服务端，**Then** 只有 `POST /conversations/{id}/messages`，没有新的 UI action intent。
2. **Given** 提案里的选项不合法（数量、长度、slug 格式、重复、含标签或 URL），**When** 发布投影，**Then** 提案判废并退回文本，不发布卡片。

### Edge Cases

- 选项少于 2 项或多于 5 项；label 与 value 各自重复。
- `ChoiceGroup` 试图携带 `actions`（必须被拒，与现有非 ActionBar 规则一致）。
- 体验库中已存在的 `catalog_version = 1` 文档在新前端下仍须正常渲染。
- 客户连点同一选项、提交失败后重试、断线后重连。

## Requirements

- **FR-001**: `ui_proposal` 允许**可选** `options`，逐项校验数量、长度、slug 格式与去重；不合法则整个提案判废。
- **FR-002**: 可信目录新增 `ChoiceGroup`，props 为 `("title", "body")`，选项放在组件级 `options`；该类型不得携带动作。
- **FR-003**: 投影构建器首次读取提案内容：有合法 `options` 时输出 `ChoiceGroup`，否则维持 `QuestionForm`；`ChoiceGroup` 必须排在 `ActionBar` 之后。
- **FR-004**: 选项点击复用已存在的消息接口，不新增 HTTP 操作、不放宽动作白名单。
- **FR-005**: `CATALOG_VERSION` 升到 2，前端接受 `{1, 2}`，既有文档不被判废。
- **FR-006**: 未知类型、非法选项、过期 revision 与过期文档继续走现有整文档降级，文字路径始终可用。

## Success Criteria

- **SC-001**: 真实浏览器中点到选项后，数据库里出现对应的 CUSTOMER/PUBLIC 消息，且 Agent 产生新一轮回复。
- **SC-002**: 后端全量、浏览器回归与真实端到端套件在改动后保持通过（数量不低于改动前）。
- **SC-003**: 契约漂移检查、前端 typecheck 与 build 通过。

## Assumptions

- 选项点击**不**触发任何售后动作，只等同于客户说了一句话。
- 情绪与置信度不参与选项生成，模型只依据上下文与手册给出选项。
- 本切片不覆盖身份卡、证据卡、步骤卡、核验卡等其他纵切面内容。
