"""Teacher credential and professional-development tracking for Education."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from hybridagent.jurisdictions import get_education_profile

Profession = Literal["teacher"]
CredentialStatus = Literal[
    "current", "expiring_soon", "expired", "ce_deficient", "no_requirement"
]


@dataclass(frozen=True)
class CESession:
    date: str
    hours: float
    ethics_hours: float = 0.0
    provider: str = ""
    course_name: str = ""
    topic: str = ""


@dataclass
class Credential:
    user_id: str
    profession: Profession
    state: str
    license_number: str
    renewal_cycle_years: int
    required_hours: float
    required_ethics_hours: float
    last_renewed: str
    expires_at: str = ""
    status: str = "active"
    sessions: list[CESession] = field(default_factory=list)
    notes: str = ""

    @property
    def accumulated_hours(self) -> float:
        return sum(session.hours for session in self.sessions)

    @property
    def accumulated_ethics_hours(self) -> float:
        return sum(session.ethics_hours for session in self.sessions)


def credential_for(
    user_id: str,
    profession: str,
    state: str,
    license_number: str,
    last_renewed: str,
) -> Credential | None:
    if profession != "teacher":
        return None
    profile = get_education_profile(state.lower())
    if profile is None:
        return None
    try:
        datetime.fromisoformat(last_renewed)
    except (TypeError, ValueError):
        return None
    hours = float(profile.teacher_pd_hours) if profile.teacher_pd_hours > 0 else 0.0
    cycle = profile.teacher_pd_cycle_years if profile.teacher_pd_cycle_years > 0 else 5
    return Credential(
        user_id=user_id,
        profession="teacher",
        state=state.upper(),
        license_number=license_number,
        renewal_cycle_years=cycle,
        required_hours=hours,
        required_ethics_hours=0.0,
        last_renewed=last_renewed,
        notes=(
            f"cert_authority={profile.teacher_cert_authority}; "
            f"{profile.teacher_cert_citation}"
        ),
    )


def record_hours(credential: Credential, session: CESession) -> Credential:
    if not math.isfinite(session.hours) or not math.isfinite(session.ethics_hours):
        raise ValueError("CE hours must be finite")
    if session.hours < 0 or session.ethics_hours < 0:
        raise ValueError("CE hours cannot be negative")
    if session.ethics_hours > session.hours:
        raise ValueError("ethics_hours cannot exceed total hours")
    try:
        datetime.fromisoformat(session.date)
    except (TypeError, ValueError) as exc:
        raise ValueError("session date must be ISO-8601") from exc
    credential.sessions.append(session)
    return credential


def _cycle_end(last: datetime, years: int) -> datetime:
    try:
        return last.replace(year=last.year + years)
    except ValueError:
        # A February 29 renewal ends on February 28 in a non-leap year.
        return last.replace(year=last.year + years, day=28)


def compliance_status(
    credential: Credential,
    *,
    now: float | None = None,
    expiring_threshold_days: int = 60,
) -> CredentialStatus:
    if credential.status != "active":
        return "expired"
    if credential.required_hours == 0 and credential.required_ethics_hours == 0:
        return "no_requirement"
    try:
        last = datetime.fromisoformat(credential.last_renewed)
    except (TypeError, ValueError):
        return "ce_deficient"
    cycle_end = _cycle_end(last, credential.renewal_cycle_years)
    now_dt = datetime.fromtimestamp(now if now is not None else time.time())
    if now_dt > cycle_end:
        return "expired"
    current_sessions: list[CESession] = []
    for session in credential.sessions:
        try:
            occurred = datetime.fromisoformat(session.date)
        except (TypeError, ValueError):
            continue
        if last <= occurred <= cycle_end:
            current_sessions.append(session)
    if sum(item.hours for item in current_sessions) < credential.required_hours:
        return "ce_deficient"
    if sum(item.ethics_hours for item in current_sessions) < credential.required_ethics_hours:
        return "ce_deficient"
    if (cycle_end - now_dt).days <= expiring_threshold_days:
        return "expiring_soon"
    return "current"


def is_compliant(credential: Credential, *, now: float | None = None) -> bool:
    return compliance_status(credential, now=now) in {"current", "no_requirement"}
