import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.errors import ServiceError
from serviceos_api.persistence.models import AuthSession, Customer, StaffUser, Tenant, TenantMembership
from serviceos_api.settings import Settings

LOCAL_ACCOUNTS = {
    "customer-a": ("CUSTOMER", "local-demo-a", "local:customer-a"),
    "customer-b": ("CUSTOMER", "local-demo-a", "local:customer-b"),
    "staff": ("STAFF", "local-demo-a", "local:staff"),
    "other-tenant": ("CUSTOMER", "local-demo-b", "local:other-tenant"),
}
COOKIE_NAME = "serviceos_session"
SESSION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    actor_id: UUID
    kind: str
    display_name: str
    role: str | None = None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login_local(session: Session, settings: Settings, username: str, password: str):
    if not settings.local_auth_enabled:
        raise ServiceError(404, "本地体验登录未启用。")
    if username not in LOCAL_ACCOUNTS or not hmac.compare_digest(password, settings.local_password):
        raise ServiceError(401, "账号或密码不正确。")
    kind, slug, subject = LOCAL_ACCOUNTS[username]
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise ServiceError(503, "本地测试账号尚未初始化。")
    if kind == "CUSTOMER":
        actor = session.scalar(select(Customer).where(Customer.tenant_id == tenant.id, Customer.external_subject == subject))
        if actor is None:
            raise ServiceError(503, "本地测试账号尚未初始化。")
        principal = Principal(tenant.id, actor.id, kind, actor.display_name)
        identity = {"customer_id": actor.id}
    else:
        actor = session.scalar(select(StaffUser).where(StaffUser.external_subject == subject))
        membership = session.scalar(select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id, TenantMembership.staff_user_id == actor.id,
            TenantMembership.active.is_(True),
        )) if actor else None
        if membership is None:
            raise ServiceError(403, "客服账号没有当前租户的有效权限。")
        principal = Principal(tenant.id, actor.id, kind, actor.display_name, membership.role)
        identity = {"staff_user_id": actor.id}
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(tenant_id=tenant.id, token_hash=token_hash(token),
                            expires_at=datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS), **identity))
    session.commit()
    return principal, token


def authenticated_principal(session: Session, token: str | None) -> Principal:
    if not token or len(token) > 128:
        raise ServiceError(401, "请先登录。")
    auth = session.scalar(select(AuthSession).where(
        AuthSession.token_hash == token_hash(token), AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > datetime.now(timezone.utc),
    ))
    if auth is None:
        raise ServiceError(401, "登录已失效，请重新登录。")
    if auth.customer_id:
        actor = session.scalar(select(Customer).where(Customer.tenant_id == auth.tenant_id, Customer.id == auth.customer_id))
        if actor:
            return Principal(auth.tenant_id, actor.id, "CUSTOMER", actor.display_name)
    else:
        actor = session.get(StaffUser, auth.staff_user_id)
        membership = session.scalar(select(TenantMembership).where(
            TenantMembership.tenant_id == auth.tenant_id, TenantMembership.staff_user_id == auth.staff_user_id,
            TenantMembership.active.is_(True),
        ))
        if actor and membership:
            return Principal(auth.tenant_id, actor.id, "STAFF", actor.display_name, membership.role)
    raise ServiceError(403, "当前账号权限已失效。")


def logout(session: Session, token: str):
    auth = session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    if auth:
        auth.revoked_at = datetime.now(timezone.utc)
        session.commit()
