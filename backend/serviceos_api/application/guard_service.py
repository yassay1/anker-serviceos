"""Staff-facing publication guard review: decision stream, maker-checker override, stats."""

from uuid import UUID

from sqlalchemy import func, select

from serviceos_api.application.business import BusinessService
from serviceos_api.application.contracts import (
    GuardDecisionPage, GuardDecisionRead, GuardStatsRead, PolicyRead,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.persistence.models import (
    AgentProposal, Message, OutboxEvent, PublicationGuardDecision, ServicePolicy,
)


def _read(row: PublicationGuardDecision) -> GuardDecisionRead:
    return GuardDecisionRead(
        id=row.id, conversation_id=row.conversation_id, run_id=row.run_id,
        decision=row.decision, reason_codes=row.reason_codes, entities=row.entities,
        verifier=row.verifier, reply_text=row.reply_text, proposal_id=row.proposal_id,
        override_by=row.override_by, override_at=row.override_at, created_at=row.created_at,
    )


class GuardService(BusinessService):
    def _staff(self):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "仅客服身份可以查看发布守卫记录。", code="FORBIDDEN_ACTOR")

    def decisions(self, cursor: UUID | None, limit: int) -> GuardDecisionPage:
        self._staff()
        query = select(PublicationGuardDecision).where(
            PublicationGuardDecision.tenant_id == self.actor.tenant_id)
        if cursor is not None:
            current = self.session.get(PublicationGuardDecision, cursor)
            if current is None:
                raise ServiceError(404, "守卫决策不存在。", code="GUARD_MISSING")
            query = query.where(PublicationGuardDecision.created_at < current.created_at)
        rows = self.session.scalars(query.order_by(
            PublicationGuardDecision.created_at.desc(), PublicationGuardDecision.id.desc())
            .limit(limit + 1)).all()
        return GuardDecisionPage(items=[_read(row) for row in rows[:limit]],
                                 next_cursor=str(rows[limit].id) if len(rows) > limit else None)

    def decision(self, decision_id: UUID) -> GuardDecisionRead:
        self._staff()
        row = self.session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.id == decision_id,
            PublicationGuardDecision.tenant_id == self.actor.tenant_id))
        if row is None:
            raise ServiceError(404, "守卫决策不存在。", code="GUARD_MISSING")
        return _read(row)

    def override(self, decision_id: UUID) -> GuardDecisionRead:
        self._staff()
        if self.actor.role not in ("SUPERVISOR", "ADMIN"):
            raise ServiceError(403, "仅主管或管理员可以复核发布被拦答复。", code="FORBIDDEN_ROLE")
        row = self.session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.id == decision_id,
            PublicationGuardDecision.tenant_id == self.actor.tenant_id).with_for_update())
        if row is None:
            raise ServiceError(404, "守卫决策不存在。", code="GUARD_MISSING")
        if row.decision != "BLOCKED":
            raise ServiceError(409, "该决策不是待复核状态。", code="GUARD_NOT_BLOCKED")
        proposal = self.session.scalar(select(AgentProposal).where(
            AgentProposal.id == row.proposal_id, AgentProposal.proposal_type == "REPLY"))
        if proposal is None:
            raise ServiceError(409, "被拦草稿缺失，无法复核发布。", code="GUARD_DRAFT_MISSING")
        message = self.session.scalar(select(Message).where(
            Message.id == UUID(proposal.payload["source_message_id"]),
            Message.tenant_id == self.actor.tenant_id).with_for_update())
        if message is None or message.visibility != "INTERNAL":
            raise ServiceError(409, "草稿消息状态已变化，无法复核发布。", code="GUARD_DRAFT_STATE")
        message.visibility = "PUBLIC"
        row.decision = "OVERRIDDEN"
        row.override_by = self.actor.actor_id
        from datetime import datetime, timezone

        row.override_at = datetime.now(timezone.utc)
        self.session.add(OutboxEvent(
            tenant_id=self.actor.tenant_id, conversation_id=row.conversation_id,
            type="message.created", visibility="PUBLIC",
            data={"message_id": str(message.id), "conversation_id": str(row.conversation_id)},
        ))
        self.session.commit()
        return _read(row)

    def stats(self) -> GuardStatsRead:
        self._staff()
        rows = self.session.execute(select(
            PublicationGuardDecision.decision, func.count(PublicationGuardDecision.id),
        ).where(PublicationGuardDecision.tenant_id == self.actor.tenant_id).group_by(
            PublicationGuardDecision.decision)).all()
        counts = {decision: count for decision, count in rows}
        return GuardStatsRead(passed=counts.get("PASSED", 0), blocked=counts.get("BLOCKED", 0),
                              overridden=counts.get("OVERRIDDEN", 0))

    def policies(self) -> list[PolicyRead]:
        self._staff()
        rows = self.session.scalars(select(ServicePolicy).order_by(
            ServicePolicy.rule_id, ServicePolicy.version.desc())).all()
        return [PolicyRead(id=row.id, rule_id=row.rule_id, version=row.version, country=row.country,
                           channel=row.channel, product_family=row.product_family,
                           warranty_state=row.warranty_state, remedies=row.remedies,
                           status=row.status, source_ref=row.source_ref,
                           effective_from=row.effective_from, effective_to=row.effective_to)
                for row in rows]
