"""Special education procedural guardrails (Gap E3 — school_system pack).

Praxis **drafts**; the IEP team **decides**. This module enforces:

1. **Timeline tracking** — referral → eval → eligibility → IEP → annual →
   reeval against EducationProfile.sped_eval_timeline_days (IDEA floor).
2. **Draft-not-decide gate** — eligibility, placement, FAPE, manifestation
   determination cannot be autonomously finalized.
3. **Mass-IEP quality flags** — goals/templates without baseline data.
4. **Transition age** — from EducationProfile.transition_planning_age.

Never determines FAPE, placement, or eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from hybridagent.jurisdictions import get_education_profile

SpedMilestone = Literal[
    "referral",
    "eval_complete",
    "eligibility",
    "iep_developed",
    "iep_annual",
    "reeval",
    "transition_plan",
]

DecisionType = Literal[
    "eligibility",
    "placement",
    "fape",
    "manifestation",
    "related_services",
    "accommodations_only",  # draftable
    "goal_language",        # draftable
]


@dataclass(frozen=True)
class SpedCase:
    case_id: str
    student_id: str
    state: str
    referral_at: float
    student_age: int = 12
    has_baseline_data: bool = True
    milestones: tuple[tuple[str, float], ...] = ()  # (milestone, ts)


@dataclass(frozen=True)
class IepDraft:
    draft_id: str
    case_id: str
    section: str  # present_levels, goals, services, placement, pwn, ...
    content_hash: str
    has_baseline_link: bool = False
    proposes_decision: DecisionType | None = None


@dataclass
class SpedFinding:
    severity: str
    code: str
    message: str
    state: str = ""


@dataclass
class SpedReport:
    findings: list[SpedFinding] = field(default_factory=list)
    allowed: bool = True

    @property
    def blocked(self) -> bool:
        return not self.allowed or any(
            f.severity == "critical" for f in self.findings
        )


class SpedGuardrailError(Exception):
    """Raised when an autonomous SPED decision is attempted."""


_HUMAN_ONLY_DECISIONS = frozenset({
    "eligibility", "placement", "fape", "manifestation",
})


def check_timeline(case: SpedCase, *, now: float) -> SpedReport:
    """Flag overdue evaluation / IEP milestones."""
    report = SpedReport()
    st = case.state.upper()
    prof = get_education_profile(st)
    days = prof.sped_eval_timeline_days if prof else 60
    deadline = case.referral_at + days * 86400.0
    done = {m for m, _ in case.milestones}
    if "eval_complete" not in done and now > deadline:
        report.findings.append(SpedFinding(
            "high", "eval_overdue",
            f"evaluation not completed within {days} days of referral "
            f"({prof.sped_citation if prof else 'IDEA floor'})",
            st,
        ))
    elif "eval_complete" not in done:
        report.findings.append(SpedFinding(
            "info", "eval_pending",
            f"evaluation due by day {days} from referral",
            st,
        ))
    if "iep_developed" not in done and "eligibility" in done:
        report.findings.append(SpedFinding(
            "medium", "iep_after_eligibility",
            "eligibility reached without IEP developed milestone — track IEP meeting",
            st,
        ))
    # Transition
    t_age = prof.transition_planning_age if prof else 16
    if case.student_age >= t_age and "transition_plan" not in done:
        report.findings.append(SpedFinding(
            "high", "transition_missing",
            f"student age {case.student_age} ≥ transition age {t_age} for {st} "
            f"without transition_plan milestone",
            st,
        ))
    if not any(f.severity in ("high", "critical") for f in report.findings):
        report.findings.append(SpedFinding(
            "info", "timeline_ok", "no overdue critical milestones", st,
        ))
    return report


def check_decision_authority(decision: DecisionType) -> SpedReport:
    """Block human-only SPED decisions from autonomous finalization."""
    report = SpedReport()
    if decision in _HUMAN_ONLY_DECISIONS:
        report.allowed = False
        report.findings.append(SpedFinding(
            "critical", "human_only_decision",
            f"{decision} is an IEP-team / LEA human decision — Praxis may "
            f"draft supporting materials only, never finalize",
        ))
    else:
        report.findings.append(SpedFinding(
            "info", "draftable",
            f"{decision} may be drafted for human review",
        ))
    return report


def check_iep_draft(case: SpedCase, draft: IepDraft) -> SpedReport:
    """Quality + decision gate on an IEP section draft."""
    report = SpedReport()
    st = case.state.upper()
    if draft.proposes_decision in _HUMAN_ONLY_DECISIONS:
        report.allowed = False
        report.findings.append(SpedFinding(
            "critical", "draft_proposes_human_decision",
            f"draft {draft.draft_id} proposes autonomous {draft.proposes_decision} "
            f"— blocked; route to IEP team",
            st,
        ))
    # Mass-IEP flag: goals without baseline
    if draft.section in ("goals", "present_levels", "goal_language"):
        if not draft.has_baseline_link and not case.has_baseline_data:
            report.findings.append(SpedFinding(
                "high", "mass_iep_risk",
                "goal/present-levels draft lacks baseline data link — risk of "
                "non-individualized 'mass IEP' language (CDT 2025 concern)",
                st,
            ))
        elif not draft.has_baseline_link:
            report.findings.append(SpedFinding(
                "medium", "baseline_not_linked",
                "draft should link to documented baseline / present levels",
                st,
            ))
    if draft.section == "placement" and draft.proposes_decision is None:
        report.findings.append(SpedFinding(
            "high", "placement_section_needs_team",
            "placement section drafts require IEP team review before adoption",
            st,
        ))
    if report.allowed and not any(
        f.severity in ("high", "critical") for f in report.findings
    ):
        report.findings.append(SpedFinding(
            "info", "draft_ok",
            f"section {draft.section} may proceed as DRAFT for team review",
            st,
        ))
    return report


def assert_not_human_decision(decision: DecisionType) -> None:
    r = check_decision_authority(decision)
    if r.blocked:
        raise SpedGuardrailError(
            next(f.message for f in r.findings if f.severity == "critical")
        )
