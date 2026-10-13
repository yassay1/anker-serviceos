# Tasks: Persistent Events and SSE

## Phase 1: Tests
- [x] T001 PUBLIC/INTERNAL 历史过滤及跨租户拒绝。
- [x] T002 断线补取的序号与消息恢复，不重复 Agent Job。

## Phase 2: Implementation
- [x] T003 Conversation Service 持久事件投递与查询。
- [x] T004 历史和 SSE API，前端订阅与重连后权威刷新。

## Phase 3: Validation
- [x] T005 PostgreSQL、契约、类型、构建与收敛验收。

## Phase 4: Convergence

- [x] SSE 作为通知层，消息列表和事件历史作为断线恢复权威来源。
