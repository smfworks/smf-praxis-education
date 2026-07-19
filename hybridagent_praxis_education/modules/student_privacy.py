"""FERPA + state student-privacy governance (Gap E2 — school_system pack).

School-system analogue of hipaa_governance / security_attestation for
education records. Enforces:

1. **Data class gates** — directory vs education record vs special-ed /
   APPR; minimum-necessary purpose checks.
2. **Disclosure ledger** — basis for each disclosure (consent, school
   official, health/safety, directory, studies, etc.).
3. **Operator / commercial prohibitions** — no targeted ads, no sale, no
   non-educational student profiling (SOPIPA / 2-d / §4-131 style).
4. **Collection bans** — biometrics (FL), affective computing (WV).
5. **Breach notice SLAs** — vendor→LEA days from EducationProfile
   (NY = 7 calendar days).
6. **Deletion after exit** — operator deletion window (FL/OH = 90 days).

Praxis never replaces the LEA's FERPA annual notice. This module is the
runtime evidence surface for lawful handling of education records by the
agent platform when configured as a school official / school-purpose
operator under contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from hybridagent.jurisdictions import get_education_profile

DataClass = Literal[
    "directory",
    "education_record",
    "special_education",
    "staff_appr",
    "behavioral",
]

Purpose = Literal[
    "education_delivery",
    "education_administration",
    "special_education",
    "directory_publication",
    "health_safety",
    "commercial",
    "model_training",
    "targeted_advertising",
]

DisclosureBasis = Literal[
    "parent_consent",
    "eligible_student_consent",
    "school_official",
    "directory",
    "health_safety",
    "judicial_order",
    "studies",
    "audit_evaluation",
    "other_ferpa_exception",
]


# Purpose → allowed data classes (minimum necessary)
_PURPOSE_CLASSES: dict[str, frozenset[str]] = {
    "education_delivery": frozenset({
        "directory", "education_record", "special_education",
    }),
    "education_administration": frozenset({
        "directory", "education_record", "staff_appr",
    }),
    "special_education": frozenset({
        "directory", "education_record", "special_education", "behavioral",
    }),
    "directory_publication": frozenset({"directory"}),
    "health_safety": frozenset({
        "directory", "education_record", "special_education", "behavioral",
    }),
    "commercial": frozenset(),  # never
    "model_training": frozenset(),  # never on identifiable student data
    "targeted_advertising": frozenset(),  # never
}


@dataclass(frozen=True)
class DisclosureEvent:
    event_id: str
    student_id: str
    state: str
    data_class: DataClass
    purpose: Purpose
    basis: DisclosureBasis
    recipient: str
    disclosed_at: float
    fields: tuple[str, ...] = ()


@dataclass
class PrivacyFinding:
    severity: str
    code: str
    message: str
    state: str = ""


@dataclass
class PrivacyReport:
    findings: list[PrivacyFinding] = field(default_factory=list)
    allowed: bool = True

    @property
    def blocked(self) -> bool:
        return not self.allowed or any(
            f.severity == "critical" for f in self.findings
        )


class StudentPrivacyError(Exception):
    """Hard privacy / FERPA operator violation."""


class DisclosureLedger:
    """Append-only ledger of education-record disclosures."""

    def __init__(self) -> None:
        self._events: list[DisclosureEvent] = []

    def record(self, event: DisclosureEvent) -> DisclosureEvent:
        self._events.append(event)
        return event

    def for_student(self, student_id: str) -> list[DisclosureEvent]:
        return [e for e in self._events if e.student_id == student_id]

    def all_events(self) -> list[DisclosureEvent]:
        return list(self._events)


def check_purpose_access(
    *,
    state: str,
    data_class: DataClass,
    purpose: Purpose,
    fields: tuple[str, ...] = (),
) -> PrivacyReport:
    """Minimum-necessary check for a proposed access/use of student data."""
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)

    if purpose in ("commercial", "targeted_advertising", "model_training"):
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "prohibited_purpose",
            f"purpose {purpose!r} is never permitted for student education "
            f"records (SOPIPA / Ed Law 2-d / FERPA commercial limits)",
            st,
        ))
        return report

    allowed = _PURPOSE_CLASSES.get(purpose, frozenset())
    if data_class not in allowed:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "purpose_class_mismatch",
            f"data class {data_class!r} not permitted for purpose {purpose!r}",
            st,
        ))
        return report

    # APPR only when state protects it and purpose is admin
    if data_class == "staff_appr":
        if prof is not None and not prof.teacher_appr_data_protected:
            report.findings.append(PrivacyFinding(
                "medium", "appr_not_state_protected",
                f"{st} does not encode teacher/principal APPR under 2-d-class "
                f"protection — treat as staff PII under district policy",
                st,
            ))
        if purpose != "education_administration":
            report.allowed = False
            report.findings.append(PrivacyFinding(
                "critical", "appr_wrong_purpose",
                "staff APPR data requires education_administration purpose",
                st,
            ))

    # Special education requires special_education or education_delivery purpose
    if data_class == "special_education" and purpose not in (
        "special_education", "education_delivery", "health_safety",
    ):
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "sped_purpose_required",
            "special education data requires special_education / delivery / "
            "health_safety purpose",
            st,
        ))

    if report.allowed:
        report.findings.append(PrivacyFinding(
            "info", "purpose_ok",
            f"{data_class} for {purpose} permitted under minimum-necessary map",
            st,
        ))
    return report


def check_collection(
    *,
    state: str,
    collect_biometrics: bool = False,
    collect_affective: bool = False,
    collect_political_religion: bool = False,
) -> PrivacyReport:
    """Collection bans from EducationProfile (FL biometrics, WV affective)."""
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)
    if prof is None:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "unknown_jurisdiction",
            f"state {st!r} not in education registry",
            st,
        ))
        return report

    if collect_biometrics and prof.biometric_collection_banned:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "biometric_banned",
            f"{st} bans collection of biometric information of students/"
            f"parents/siblings ({prof.privacy_citation})",
            st,
        ))
    if collect_affective and prof.affective_computing_banned:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "affective_computing_banned",
            f"{st} bans affective computing data collection "
            f"({prof.privacy_citation})",
            st,
        ))
    if collect_political_religion and prof.biometric_collection_banned:
        # FL §1002.222 bundles political/religious with biometric ban
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "sensitive_affiliation_banned",
            f"{st} restricts collection of political/religious affiliation "
            f"alongside biometric bans",
            st,
        ))
    if report.allowed:
        report.findings.append(PrivacyFinding(
            "info", "collection_ok", "collection within state bans", st,
        ))
    return report


def check_commercial_use(*, state: str, use: str) -> PrivacyReport:
    """Block commercial student-data uses for operator-law states."""
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)
    commercial_uses = {
        "targeted_advertising", "sell_student_data", "rent_student_data",
        "non_educational_profiling", "train_foundation_model_on_pii",
    }
    if use in commercial_uses:
        report.allowed = False
        cite = ""
        if prof is not None:
            cite = prof.operator_citation or prof.privacy_citation
        report.findings.append(PrivacyFinding(
            "critical", "commercial_use_prohibited",
            f"use {use!r} prohibited for K-12 student data"
            + (f" ({cite})" if cite else ""),
            st,
        ))
    else:
        report.findings.append(PrivacyFinding(
            "info", "use_ok", f"use {use!r} not a banned commercial purpose", st,
        ))
    return report


def check_vendor_breach_notice(
    *,
    state: str,
    discovered_at: float,
    notified_lea_at: float,
) -> PrivacyReport:
    """Vendor → LEA breach notice SLA from EducationProfile."""
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)
    days = prof.vendor_breach_notice_days if prof else 0
    if days <= 0:
        report.findings.append(PrivacyFinding(
            "info", "no_state_vendor_sla",
            f"{st} has no encoded vendor→LEA day SLA — use contract + ASAP",
            st,
        ))
        return report
    elapsed = (notified_lea_at - discovered_at) / 86400.0
    if elapsed > days:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "vendor_breach_late",
            f"vendor notified LEA after {elapsed:.1f} days; {st} requires "
            f"≤{days} calendar days ({prof.privacy_citation if prof else ''})",
            st,
        ))
    else:
        report.findings.append(PrivacyFinding(
            "info", "vendor_breach_timely",
            f"notified within {elapsed:.1f} days (limit {days})",
            st,
        ))
    return report


def check_operator_deletion(
    *,
    state: str,
    student_exit_at: float,
    deleted_at: float | None,
    parent_consent_retain: bool = False,
    now: float = 0.0,
) -> PrivacyReport:
    """Operator deletion window after student exit (FL/OH = 90 days)."""
    import time as _t
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)
    if prof is None or prof.deletion_days_after_exit <= 0:
        report.findings.append(PrivacyFinding(
            "info", "no_encoded_deletion_window",
            f"{st} has no encoded operator deletion-days field — follow DPA",
            st,
        ))
        return report
    if parent_consent_retain:
        report.findings.append(PrivacyFinding(
            "info", "parent_consent_retain",
            "parent consented to retain beyond exit deletion window",
            st,
        ))
        return report
    deadline = student_exit_at + prof.deletion_days_after_exit * 86400.0
    now_ts = _t.time() if now == 0.0 else now
    if deleted_at is None:
        if now_ts > deadline:
            report.allowed = False
            report.findings.append(PrivacyFinding(
                "critical", "deletion_overdue",
                f"operator has not deleted covered info within "
                f"{prof.deletion_days_after_exit} days of student exit "
                f"({prof.operator_citation or prof.privacy_citation})",
                st,
            ))
        else:
            report.findings.append(PrivacyFinding(
                "info", "deletion_pending",
                f"deletion due by {deadline} ({prof.deletion_days_after_exit}d window)",
                st,
            ))
    elif deleted_at > deadline:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "high", "deletion_late",
            f"deleted after {prof.deletion_days_after_exit}-day window",
            st,
        ))
    else:
        report.findings.append(PrivacyFinding(
            "info", "deletion_timely", "deleted within operator window", st,
        ))
    return report


def attest_privacy_controls(
    state: str,
    *,
    written_dpa: bool = False,
    encryption_at_rest: bool = False,
    encryption_in_transit: bool = False,
    no_commercial_use: bool = False,
    parent_bill_of_rights: bool = False,
    nist_aligned: bool = False,
    dpo_designated: bool = False,
) -> PrivacyReport:
    """Pass/fail attestation surface for LEA vendor controls (2-d / SOPIPA)."""
    report = PrivacyReport()
    st = state.upper()
    prof = get_education_profile(st)
    if prof is None:
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "critical", "unknown_jurisdiction", f"no profile for {st}", st,
        ))
        return report

    def need(ok: bool, code: str, msg: str, severity: str = "critical") -> None:
        if not ok:
            report.allowed = False
            report.findings.append(PrivacyFinding(severity, code, msg, st))

    if prof.privacy_tier == "ny_2d_ceiling":
        need(written_dpa, "missing_dpa", "NY 2-d requires written contractor agreement")
        need(encryption_at_rest and encryption_in_transit, "missing_encryption",
             "NY 2-d / Part 121 require encryption at rest and in transit")
        need(no_commercial_use, "commercial_use_not_attested",
             "must attest no commercial/marketing use of student or APPR data")
        need(parent_bill_of_rights, "missing_parent_bor",
             "Parents' Bill of Rights required under NY 2-d")
        need(nist_aligned, "nist_not_aligned", "Part 121 expects NIST CSF alignment")
        need(dpo_designated, "missing_dpo", "LEA DPO designation expected under Part 121")
    elif prof.privacy_tier in ("enhanced_operator", "ct_contract"):
        need(written_dpa, "missing_dpa",
             f"{st} operator/contract regime requires written agreement "
             f"({prof.operator_citation or prof.privacy_citation})")
        need(no_commercial_use, "commercial_use_not_attested",
             "must attest no targeted ads / sale / non-ed profiling")
        if prof.privacy_tier == "ct_contract":
            need(written_dpa, "ct_void_risk",
                 "CT contracts missing required clauses may be void")
    else:
        need(no_commercial_use or True, "ferpa_floor",
             "FERPA floor — still prohibit commercial reuse in product defaults",
             "info")
        if not written_dpa:
            report.findings.append(PrivacyFinding(
                "medium", "dpa_recommended",
                "written DPA recommended even on FERPA floor", st,
            ))

    if report.allowed:
        report.findings.append(PrivacyFinding(
            "info", "attestation_pass",
            f"{st} privacy controls pass for tier {prof.privacy_tier}", st,
        ))
    return report


def record_disclosure(
    ledger: DisclosureLedger,
    event: DisclosureEvent,
) -> tuple[DisclosureEvent, PrivacyReport]:
    """Validate purpose then append to the disclosure ledger."""
    report = check_purpose_access(
        state=event.state,
        data_class=event.data_class,
        purpose=event.purpose,
        fields=event.fields,
    )
    if report.blocked:
        return event, report
    # Directory basis required for directory publication
    if event.purpose == "directory_publication" and event.basis != "directory":
        report.allowed = False
        report.findings.append(PrivacyFinding(
            "high", "directory_basis_required",
            "directory publication requires directory disclosure basis",
            event.state.upper(),
        ))
        return event, report
    ledger.record(event)
    report.findings.append(PrivacyFinding(
        "info", "disclosure_recorded",
        f"disclosure {event.event_id} recorded", event.state.upper(),
    ))
    return event, report
