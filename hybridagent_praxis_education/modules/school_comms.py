"""Parent/school portal triage, academic integrity gate, mandatory-report
reminders (Gaps E6, E8, E9 — school_system pack).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from hybridagent.jurisdictions import get_education_profile

MessageClass = Literal["academic", "logistics", "sped_sensitive", "mixed", "unknown"]
TriageAction = Literal["draft_for_staff", "autonomous_reply", "hold_for_admin"]

_ACADEMIC = (
    "grade", "assignment", "homework", "test score", "failing", "progress",
    "behavior", "detention", "suspension", "iep", "504", "accommodation",
    "placement", "special education", "attendance concern",
)
_LOGISTICS = (
    "field trip", "picture day", "bus schedule", "early dismissal",
    "school calendar", "spirit week", "volunteer", "pta meeting",
    "office hours", "forms location", "lunch menu",
)
_SPED = ("iep", "504", "related service", "evaluation", "eligibility", "fape")

AUTONOMOUS_LOGISTICS_TEMPLATES: dict[str, str] = {
    "calendar_hours": (
        "School office hours are Monday–Friday during the published school "
        "calendar. For student-specific academic questions, a staff member "
        "will follow up."
    ),
    "forms_location": (
        "Enrollment and general forms are available on the district website "
        "under Families → Forms, and at the main office."
    ),
    "event_confirm": (
        "Thank you — your event RSVP was received. Contact the office if you "
        "need to change attendance details."
    ),
}


@dataclass(frozen=True)
class ParentMessage:
    message_id: str
    student_id: str
    subject: str
    body: str
    state: str = ""


@dataclass(frozen=True)
class ParentReplyDraft:
    draft_id: str
    message_id: str
    body: str
    template_id: str = ""


@dataclass
class TriageFinding:
    severity: str
    code: str
    message: str


@dataclass
class TriageReport:
    message: ParentMessage
    classification: MessageClass
    action: TriageAction
    autonomous_allowed: bool = False
    findings: list[TriageFinding] = field(default_factory=list)


def _hits(text: str, signals: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for s in signals:
        if " " in s:
            if s in lower:
                found.append(s)
        elif re.search(rf"\b{re.escape(s)}\b", lower):
            found.append(s)
    return found


def classify_parent_message(msg: ParentMessage) -> MessageClass:
    text = f"{msg.subject}\n{msg.body}"
    acad = _hits(text, _ACADEMIC)
    logi = _hits(text, _LOGISTICS)
    sped = _hits(text, _SPED)
    if sped or (acad and logi):
        return "sped_sensitive" if sped and not logi else (
            "mixed" if acad and logi else ("sped_sensitive" if sped else "mixed")
        )
    if acad:
        return "academic"
    if logi:
        return "logistics"
    if sped:
        return "sped_sensitive"
    return "unknown"


def triage_parent_message(
    msg: ParentMessage,
    reply: ParentReplyDraft | None = None,
) -> TriageReport:
    cls = classify_parent_message(msg)
    # normalize mixed/sped
    text = f"{msg.subject}\n{msg.body}"
    if _hits(text, _SPED):
        cls = "sped_sensitive"
    elif _hits(text, _ACADEMIC) and _hits(text, _LOGISTICS):
        cls = "mixed"
    elif _hits(text, _ACADEMIC):
        cls = "academic"
    elif _hits(text, _LOGISTICS):
        cls = "logistics"
    else:
        cls = "unknown"

    report = TriageReport(message=msg, classification=cls, action="draft_for_staff")
    if cls in ("academic", "sped_sensitive", "mixed", "unknown"):
        report.action = "draft_for_staff"
        report.autonomous_allowed = False
        report.findings.append(TriageFinding(
            "info", "staff_hold",
            f"{cls} parent messages are SEND-held for staff approval",
        ))
        return report

    # pure logistics
    if reply is None:
        report.action = "hold_for_admin"
        report.findings.append(TriageFinding(
            "info", "awaiting_template",
            "select an allowlisted logistics template for autonomous reply",
        ))
        return report
    if (
        reply.template_id in AUTONOMOUS_LOGISTICS_TEMPLATES
        and reply.body.strip()
        == AUTONOMOUS_LOGISTICS_TEMPLATES[reply.template_id].strip()
    ):
        report.action = "autonomous_reply"
        report.autonomous_allowed = True
        report.findings.append(TriageFinding(
            "info", "autonomous_ok",
            f"template {reply.template_id!r} allowlisted for logistics",
        ))
        return report
    report.action = "hold_for_admin"
    report.findings.append(TriageFinding(
        "medium", "not_allowlisted",
        "logistics reply is not an exact allowlisted template",
    ))
    return report


# --- E8 academic integrity ---

IntegrityContext = Literal[
    "formative_feedback",
    "summative_graded",
    "homework_complete_answers",
    "lesson_plan_teacher",
    "study_guide_no_key",
]


@dataclass
class IntegrityReport:
    allowed: bool
    findings: list[str] = field(default_factory=list)


def check_academic_integrity(
    *,
    context: IntegrityContext,
    student_facing: bool,
    provides_complete_answers: bool,
    state: str = "",
) -> IntegrityReport:
    """Gate student-facing complete solutions on graded work."""
    report = IntegrityReport(allowed=True)
    if context == "lesson_plan_teacher" and not student_facing:
        report.findings.append("teacher-facing lesson plan OK")
        return report
    if student_facing and provides_complete_answers and context in (
        "summative_graded", "homework_complete_answers",
    ):
        report.allowed = False
        report.findings.append(
            "student-facing complete answers on graded/homework work blocked "
            "— academic integrity (draft hints/scaffolds only)"
        )
        return report
    if student_facing and context == "formative_feedback":
        report.findings.append(
            "formative feedback OK if district policy allows; no grade posting"
        )
    prof = get_education_profile(state) if state else None
    if prof and prof.ai_policy_required:
        report.findings.append(
            f"{state.upper()} requires district AI policy "
            f"({prof.ai_policy_citation}) — confirm tool is approved"
        )
    return report


# --- E9 mandatory report reminder ---

_REPORT_SIGNALS = (
    "abuse", "neglect", "bruises", "unsafe home", "disclosure of harm",
    "self-harm", "suicidal", "assault",
)


@dataclass
class ReportReminder:
    should_remind: bool
    signals: list[str] = field(default_factory=list)
    message: str = ""
    may_auto_file: bool = False  # always False


def scan_for_mandatory_report_signals(text: str, *, state: str = "") -> ReportReminder:
    """Remind staff of reporting duty; never file as agent."""
    low = text.lower()
    hits = [s for s in _REPORT_SIGNALS if s in low]
    prof = get_education_profile(state) if state else None
    cite = prof.mandatory_report_citation if prof else "state mandated reporter law"
    if not hits:
        return ReportReminder(False, [], "no reportable signals detected")
    return ReportReminder(
        should_remind=True,
        signals=hits,
        message=(
            f"Possible mandated-reporting signals ({', '.join(hits)}). "
            f"Remind authorized staff of duty under {cite}. "
            f"Praxis may draft documentation only — never file as reporter of record."
        ),
        may_auto_file=False,
    )
