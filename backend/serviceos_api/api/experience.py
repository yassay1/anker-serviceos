"""Staff-only review of case-derived, non-authoritative experience candidates."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import (
    ExperienceCandidatePage, ExperienceCandidateRead, ExperienceCandidateUpdate,
    ExperienceDecision, ExperienceReviewPage,
)
from serviceos_api.application.experience import ExperienceService

router = APIRouter(prefix="/api/v1/experience-candidates", tags=["experience"])


@router.get("", response_model=ExperienceCandidatePage, operation_id="list_experience_candidates")
def list_candidates(status: Literal["DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "REVOKED"] | None = None,
                    limit: int = Query(default=50, ge=1, le=100),
                    actor: Principal = Depends(get_actor), session: Session = Depends(get_session)):
    return ExperienceService(session, actor).list(status=status, limit=limit)


@router.get("/{candidate_id}", response_model=ExperienceCandidateRead,
            operation_id="read_experience_candidate")
def read_candidate(candidate_id: UUID, actor: Principal = Depends(get_actor),
                   session: Session = Depends(get_session)):
    return ExperienceService(session, actor).read(candidate_id)


@router.patch("/{candidate_id}", response_model=ExperienceCandidateRead,
              operation_id="update_experience_candidate")
def update_candidate(candidate_id: UUID, body: ExperienceCandidateUpdate,
                     actor: Principal = Depends(get_actor), session: Session = Depends(get_session)):
    return ExperienceService(session, actor).update(candidate_id, body)


@router.post("/{candidate_id}/decisions", response_model=ExperienceCandidateRead,
             operation_id="decide_experience_candidate")
def decide_candidate(candidate_id: UUID, body: ExperienceDecision,
                     actor: Principal = Depends(get_actor), session: Session = Depends(get_session)):
    return ExperienceService(session, actor).decide(candidate_id, body)


@router.get("/{candidate_id}/reviews", response_model=ExperienceReviewPage,
            operation_id="list_experience_candidate_reviews")
def list_reviews(candidate_id: UUID, actor: Principal = Depends(get_actor),
                 session: Session = Depends(get_session)):
    return ExperienceService(session, actor).reviews(candidate_id)
