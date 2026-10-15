from typing import Annotated
from ipaddress import ip_address, ip_network

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from serviceos_api.application.auth import COOKIE_NAME, authenticated_principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import BusinessService, ConversationService
from serviceos_api.persistence.database import build_engine

cookie = APIKeyCookie(name=COOKIE_NAME, scheme_name="SessionCookie", auto_error=False)


def configured_auth(request: Request):
    # Local sessions are accepted only by an explicitly enabled local adapter.
    if not request.app.state.settings.local_auth_enabled:
        raise ServiceError(401, "当前环境尚未配置业务认证。")
    require_local_peer(request)


def get_session(request: Request):
    if request.app.state.database_engine is None:
        try:
            request.app.state.database_engine = build_engine()
            request.app.state.owns_engine = True
        except (RuntimeError, ValueError):
            raise ServiceError(503, "业务数据库尚未配置。") from None
    with Session(request.app.state.database_engine, expire_on_commit=False) as session:
        yield session


def get_actor(
    _=Depends(configured_auth),
    token: str | None = Security(cookie),
    session: Session = Depends(get_session),
):
    return authenticated_principal(session, token)


def get_business(actor=Depends(get_actor), session: Session = Depends(get_session)):
    return BusinessService(session, actor)


Business = Annotated[BusinessService, Depends(get_business)]


def get_conversation_service(actor=Depends(get_actor), session: Session = Depends(get_session)):
    return ConversationService(session, actor)


ConversationBusiness = Annotated[ConversationService, Depends(get_conversation_service)]


def local_login_allowed(request: Request):
    settings = request.app.state.settings
    if not settings.local_auth_enabled:
        raise ServiceError(404, "本地体验登录未启用。")
    require_local_peer(request)


def require_local_peer(request: Request):
    settings = request.app.state.settings
    peer = request.client.host if request.client else ""
    if settings.environment == "test" and peer == "testclient":
        return
    try:
        address = ip_address(peer)
        allowed = any(address in ip_network(cidr) for cidr in settings.local_auth_networks)
    except ValueError:
        allowed = False
    if not settings.local_auth_enabled or not allowed:
        raise ServiceError(403, "本地体验登录仅允许显式配置的本地网络。")
