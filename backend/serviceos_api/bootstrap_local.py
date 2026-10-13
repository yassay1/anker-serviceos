"""Explicit sample identities for the isolated local development database."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.auth import LOCAL_ACCOUNTS
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import Customer, StaffUser, Tenant, TenantMembership
from serviceos_api.settings import Settings


def seed_local_accounts(session: Session):
    for username, (kind, slug, subject) in LOCAL_ACCOUNTS.items():
        tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            tenant = Tenant(slug=slug, name="本地服务体验" if slug.endswith("a") else "另一租户体验")
            session.add(tenant)
            session.flush()
        if kind == "CUSTOMER":
            actor = session.scalar(select(Customer).where(Customer.tenant_id == tenant.id, Customer.external_subject == subject))
            if actor is None:
                session.add(Customer(tenant_id=tenant.id, external_subject=subject, display_name={
                    "customer-a": "客户 A", "customer-b": "客户 B", "other-tenant": "另一租户客户",
                }[username]))
                session.flush()
        else:
            actor = session.scalar(select(StaffUser).where(StaffUser.external_subject == subject))
            if actor is None:
                actor = StaffUser(external_subject=subject, display_name="本地客服")
                session.add(actor)
                session.flush()
            membership = session.scalar(select(TenantMembership).where(
                TenantMembership.tenant_id == tenant.id, TenantMembership.staff_user_id == actor.id,
            ))
            if membership is None:
                session.add(TenantMembership(tenant_id=tenant.id, staff_user_id=actor.id, role="SUPPORT"))
                session.flush()
    session.commit()


def main():
    settings = Settings.from_environment()
    if not settings.local_auth_enabled:
        raise SystemExit("Explicit development local authentication is required for sample seeding.")
    engine = build_engine()
    if engine.url.host not in ("127.0.0.1", "localhost") or engine.url.database != "serviceos_dev":
        raise SystemExit("Sample seeding is limited to the loopback serviceos_dev database.")
    try:
        with Session(engine) as session:
            seed_local_accounts(session)
        print("Local sample accounts initialized; no production accounts were created.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
