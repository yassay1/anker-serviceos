"""DMN-style policy resolution: most-specific ACTIVE row wins, with reason codes."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.persistence.models import ServicePolicy

CHANNELS = ("DIRECT", "AUTHORIZED_DEALER", "UNAUTHORIZED")
FAMILIES = ("ROBOVAC", "BREAST_PUMP")
WARRANTY_STATES = ("IN", "OUT", "UNKNOWN")


def _specificity(row: ServicePolicy, country: str, channel: str, family: str) -> tuple:
    return (
        0 if row.country == country else 1,
        0 if row.channel == channel else 1,
        0 if row.product_family == family else 1,
        -row.version,
    )


def resolve_policy_row(session: Session, *, country: str, channel: str,
                       product_family: str, warranty_state: str) -> ServicePolicy | None:
    country_key = country.strip().upper() or "*"
    channel_key = channel.strip().upper()
    family_key = product_family.strip().upper()
    state_key = warranty_state.strip().upper()
    if channel_key not in CHANNELS or family_key not in FAMILIES or state_key not in WARRANTY_STATES:
        return None
    now = datetime.now(timezone.utc)
    rows = session.scalars(select(ServicePolicy).where(
        ServicePolicy.status == "ACTIVE",
        ServicePolicy.country.in_((country_key, "*")),
        ServicePolicy.channel.in_((channel_key, "*")),
        ServicePolicy.product_family.in_((family_key, "*")),
        ServicePolicy.warranty_state == state_key,
        ServicePolicy.effective_from <= now,
        (ServicePolicy.effective_to.is_(None) | (ServicePolicy.effective_to > now)),
    )).all()
    if not rows:
        return None
    return sorted(rows, key=lambda row: _specificity(row, country_key, channel_key, family_key))[0]
