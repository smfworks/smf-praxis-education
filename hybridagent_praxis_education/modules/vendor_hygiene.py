"""Vendor / edtech contract hygiene (Gap E10 — school_system pack).

Checklist surface for LEA contracts with AI/edtech operators under:
- NY Ed Law 2-d / Part 121
- CT CGS 10-234aa–dd (void if missing clauses)
- FL §1006.1494 / VA §22.1-289.01 / MD Educ. §4-131 / OH §§3319.325–.327

Does not replace counsel. Produces findings for DPA completeness.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hybridagent.jurisdictions import get_education_profile


@dataclass(frozen=True)
class VendorContract:
    contract_id: str
    vendor_name: str
    state: str
    written_agreement: bool = False
    parent_bill_of_rights: bool = False
    no_sale_of_student_data: bool = False
    no_targeted_ads: bool = False
    no_non_ed_profiling: bool = False
    encryption_at_rest: bool = False
    encryption_in_transit: bool = False
    deletion_on_exit: bool = False
    breach_notice_days: int = 0  # 0 = not specified
    nist_aligned: bool = False
    data_security_plan: bool = False
    board_owns_data: bool = False  # CT
    model_tos_clauses: bool = False  # CT Model TOS
    no_train_on_customer_pii: bool = False
    posted_for_parents: bool = False  # CT notice/posting


@dataclass
class VendorFinding:
    severity: str
    code: str
    message: str
    state: str = ""


@dataclass
class VendorReport:
    contract: VendorContract
    findings: list[VendorFinding] = field(default_factory=list)
    passed: bool = True


def check_vendor_contract(contract: VendorContract) -> VendorReport:
    """Evaluate contract controls against the state's education privacy tier."""
    report = VendorReport(contract=contract)
    st = contract.state.upper()
    prof = get_education_profile(st)
    if prof is None:
        report.passed = False
        report.findings.append(VendorFinding(
            "critical", "unknown_jurisdiction",
            f"state {st!r} not in education registry", st,
        ))
        return report

    def need(ok: bool, code: str, msg: str, severity: str = "critical") -> None:
        if not ok:
            report.passed = False
            report.findings.append(VendorFinding(severity, code, msg, st))

    # Universal product defaults for school operators
    need(contract.written_agreement, "missing_written_agreement",
         "written agreement required when vendor receives student PII")
    need(contract.no_sale_of_student_data, "sale_not_prohibited",
         "contract must prohibit sale/rent of student data")
    need(contract.no_targeted_ads, "ads_not_prohibited",
         "contract must prohibit targeted advertising based on student data")
    need(contract.no_non_ed_profiling, "profiling_not_prohibited",
         "contract must prohibit non-educational student profiling")
    need(contract.no_train_on_customer_pii, "training_not_prohibited",
         "contract should prohibit training foundation models on identifiable student PII")

    if prof.privacy_tier == "ny_2d_ceiling":
        need(contract.parent_bill_of_rights, "missing_parent_bor",
             "NY 2-d requires Parents' Bill of Rights in/with contract")
        need(contract.encryption_at_rest and contract.encryption_in_transit,
             "missing_encryption", "NY 2-d / Part 121 require encryption")
        need(contract.nist_aligned, "nist_not_aligned",
             "Part 121 expects NIST CSF-aligned safeguards")
        need(contract.data_security_plan, "missing_security_plan",
             "NY 2-d requires data security and privacy plan")
        need(contract.breach_notice_days > 0 and contract.breach_notice_days <= 7,
             "breach_sla_missing",
             "vendor→LEA breach notice must be ≤7 calendar days (NY 2-d)")
    elif prof.privacy_tier == "ct_contract":
        need(contract.model_tos_clauses, "missing_model_tos",
             "CT requires Model TOS / statutory clauses — missing clauses may void contract")
        need(contract.board_owns_data, "board_ownership_missing",
             "CT: board owns student data / student-generated content")
        need(contract.posted_for_parents or contract.written_agreement,
             "parent_notice_missing",
             "CT requires parent notice / contract posting for contractors",
             "high")
        need(contract.deletion_on_exit, "deletion_missing",
             "CT contractor deletion duties at end of services", "high")
    elif prof.operator_law:
        need(contract.deletion_on_exit or prof.deletion_days_after_exit == 0,
             "deletion_missing",
             f"{st} operator law expects deletion-on-exit / on district notice "
             f"({prof.operator_citation})",
             "high" if prof.deletion_days_after_exit > 0 else "medium")
        if prof.deletion_days_after_exit > 0:
            need(contract.deletion_on_exit, "deletion_window_required",
                 f"{st} encodes {prof.deletion_days_after_exit}-day deletion after exit")

    if prof.ai_policy_required:
        report.findings.append(VendorFinding(
            "info", "ai_policy_reminder",
            f"{st} requires a district AI policy ({prof.ai_policy_citation}) — "
            f"confirm tool is listed/approved under that policy",
            st,
        ))

    if report.passed:
        report.findings.append(VendorFinding(
            "info", "vendor_check_pass",
            f"contract meets encoded {st} hygiene checklist", st,
        ))
    return report
