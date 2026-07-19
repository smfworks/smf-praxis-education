"""Student records access + retention for schools (Gap E7).

Parent/eligible-student access requests and retention assessment using
EducationProfile (MA 60yr transcript, FERPA 45-day access floor, FL/OH
operator deletion is separate in student_privacy).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from hybridagent.jurisdictions import get_education_profile

FERPA_ACCESS_DAYS_FLOOR = 45
_SECONDS_PER_YEAR = 365.25 * 24 * 3600
_SECONDS_PER_DAY = 24 * 3600

RecordKind = Literal["transcript", "temporary", "special_education", "other"]
AccessStatus = Literal["open", "fulfilled", "overdue", "cancelled"]


@dataclass(frozen=True)
class StudentRecordSet:
    record_id: str
    student_id: str
    state: str
    kind: RecordKind
    last_activity_at: float
    legal_hold: bool = False


@dataclass
class RetentionReport:
    record: StudentRecordSet
    retain_years: int
    dispose_after: float
    status: str  # active | eligible_for_disposal | legal_hold | unknown
    findings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParentAccessRequest:
    request_id: str
    student_id: str
    state: str
    requested_at: float
    requester: str = "parent"  # parent | eligible_student


@dataclass
class AccessWorkflow:
    request: ParentAccessRequest
    deadline_at: float
    access_days: int
    status: AccessStatus = "open"
    fulfilled_at: float = 0.0
    findings: list[str] = field(default_factory=list)

    def refresh(self, *, now: float) -> AccessStatus:
        if self.status in ("fulfilled", "cancelled"):
            return self.status
        self.status = "overdue" if now > self.deadline_at else "open"
        return self.status


def assess_student_record_retention(
    record: StudentRecordSet, *, now: float,
) -> RetentionReport:
    st = record.state.upper()
    prof = get_education_profile(st)
    if prof is None:
        return RetentionReport(
            record, 0, 0.0, "unknown",
            [f"state {st!r} not in education registry"],
        )
    if record.kind == "transcript":
        years = prof.transcript_retention_years or 60  # conservative default
    elif record.kind == "temporary":
        years = prof.temporary_record_retention_years or 7
    elif record.kind == "special_education":
        years = max(prof.temporary_record_retention_years or 7, 5)
    else:
        years = prof.temporary_record_retention_years or 7
    dispose_after = record.last_activity_at + years * _SECONDS_PER_YEAR
    findings = [f"{st} retain ~{years}y for {record.kind} ({prof.records_citation})"]
    if record.legal_hold:
        return RetentionReport(
            record, years, dispose_after, "legal_hold",
            findings + ["LEGAL HOLD — disposal blocked"],
        )
    if now >= dispose_after:
        status = "eligible_for_disposal"
        findings.append("retention elapsed — disposal review only (DESTRUCTIVE)")
    else:
        status = "active"
        findings.append("retention active")
    return RetentionReport(record, years, dispose_after, status, findings)


def open_parent_access_request(req: ParentAccessRequest) -> AccessWorkflow:
    st = req.state.upper()
    prof = get_education_profile(st)
    days = FERPA_ACCESS_DAYS_FLOOR
    findings: list[str] = []
    if prof is not None and prof.parent_access_days > 0:
        days = prof.parent_access_days
        findings.append(
            f"{st} access window: {days} days ({prof.records_citation})"
        )
    else:
        findings.append(
            f"applying FERPA {FERPA_ACCESS_DAYS_FLOOR}-day floor for {st}"
        )
    return AccessWorkflow(
        request=req,
        deadline_at=req.requested_at + days * _SECONDS_PER_DAY,
        access_days=days,
        findings=findings,
    )


def fulfill_access(wf: AccessWorkflow, *, fulfilled_at: float) -> AccessWorkflow:
    wf.fulfilled_at = fulfilled_at
    if fulfilled_at > wf.deadline_at:
        wf.status = "overdue"
        wf.findings.append("fulfilled after deadline")
    else:
        wf.status = "fulfilled"
        wf.findings.append("fulfilled within deadline")
    return wf
