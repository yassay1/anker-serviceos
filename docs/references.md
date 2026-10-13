# V1 设计来源说明

本次主要依据是用户从聊天「项目定位与技术框架」提供到 `D:\proj\共享docs` 的五份定稿文件，见 [来源清单](baseline-provenance.json)。仓库主文档分别承担产品、架构、领域与实施计划的权威职责。

共享目录未包含架构末尾提及的原始 `docs/references.md`，因此此文件只补齐引用说明，不声称恢复了原聊天的全部调研资料。

旧 A1229 原型的资料来源与历史研究随原型归档在项目外 `D:\proj\Anker SreviceOS-archive-20261013\legacy\specs\001-device-resolution-loop\`；历史发现记录位于该归档的 `planning/findings.md`。这些只用于追溯，不属于活动工程入口，旧技术选型以 V1 主架构为准。

定稿将 Dify/Onyx 作为前后端与 Worker 组织参考，将 Chatwoot 作为会话与接管参考；阶段 0 未复制这些项目源码、未据此新增框架，也未开展 Parlant/LangGraph 对比。

## Agentic Interface / Generative UI 参考（2026-10-13 核对）

- [OpenAI：Add UI to your MCP server](https://developers.openai.com/plugins/build/chatgpt-ui)：采用“UI 只在查看、比较、编辑、确认、导航结构化信息时增强体验”“工具在无 UI 客户端仍可用”“服务端返回权威更新后再渲染”“组件状态不作业务真相”等原则。本项目不采用远程 iframe 组件方案。
- [OpenAI Plugins Reference](https://developers.openai.com/plugins/reference)：参考 `structuredContent` 与声明 `outputSchema` 匹配、模型可见数据和组件私有元数据分离、CSP/域名白名单等边界；ServiceOS V1 使用自有同源 React Renderer，不直接实现 MCP Apps。
- [Vercel AI SDK：Generative User Interfaces](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)：参考“类型化工具调用/结果映射到已编写组件”以及输入可用、输出可用、错误等明确状态。本项目不更换 FastAPI + React 技术栈，也不引入 Next.js/RSC。
- [Microsoft Copilot Studio：Adaptive Cards](https://learn.microsoft.com/en-us/microsoft-copilot-studio/adaptive-cards-overview)：参考版本化 JSON 卡片、宿主原生渲染、表单提问/确认，以及连续卡片为每个提交动作提供唯一标识。
- [A2UI Catalogs](https://a2ui.org/concepts/catalogs/)、[Actions](https://a2ui.org/concepts/actions/) 与 [v1.0 候选协议](https://github.com/a2ui-project/a2ui/blob/main/specification/v1_0/docs/a2ui_protocol.md)：参考声明式数据、受信组件 Catalog、结构/数据/Renderer 解耦、revision/增量更新和动作上下文。A2UI 仍在演进，本项目只借鉴模式，V1 不把它设为运行时依赖或对外兼容承诺。

上述资料用于设计取舍，不证明本项目已经实现 UI Schema、Renderer 或对应接口；真实范围以 [开发实施计划](development-plan.md) 和阶段验收记录为准。
