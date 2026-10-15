"""Staff-only Skill discovery and bounded INTERNAL execution audit."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.auth import Principal
from serviceos_api.application.skills import SkillCatalog, SkillExecutionPage, SkillService

router = APIRouter(prefix="/api/v1", tags=["skills"])


@router.get("/skills", response_model=SkillCatalog, operation_id="list_skills")
def list_skills(response: Response, actor: Principal = Depends(get_actor), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    return SkillService(session, actor).catalog()


@router.get("/conversations/{conversation_id}/skill-executions", response_model=SkillExecutionPage,
            operation_id="list_skill_executions")
def list_skill_executions(conversation_id: UUID, response: Response,
                          after: str | None = Query(default=None, max_length=60),
                          limit: int = Query(default=50, ge=1, le=100),
                          actor: Principal = Depends(get_actor), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    return SkillService(session, actor).executions(conversation_id, after=after, limit=limit)
