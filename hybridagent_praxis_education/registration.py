"""Registration — wire the education vertical into the Praxis base registry."""

from __future__ import annotations

from pathlib import Path

from hybridagent.broker import RiskClass
from hybridagent.evals import EvalCase
from hybridagent.verticals.registry import (
    VerticalSpec,
    register_vertical_eval_cases,
    register_vertical_pack_root,
    register_vertical_spec,
)

_SCHOOL_SYSTEM_SPEC = VerticalSpec(
    name="school_system",
    persona_keyword="school system",
    compliance_mode="enforced",
    autonomous={RiskClass.READ, RiskClass.DRAFT},
    held={RiskClass.SEND, RiskClass.DESTRUCTIVE},
    version="0.1.2",
)

_EDUCATION_TUTOR_SPEC = VerticalSpec(
    name="education",
    persona_keyword="tutor",
    compliance_mode="autonomous",
    autonomous={RiskClass.READ, RiskClass.DRAFT},
    held={RiskClass.DESTRUCTIVE},
    version="0.1.2",
)


def _draft_not_decide_case():
    def run() -> tuple[bool, str]:
        from .modules.sped_guardrails import DecisionType, check_decision_authority
        human: tuple[DecisionType, ...] = (
            "eligibility", "placement", "fape", "manifestation",
        )
        blocked = all(check_decision_authority(d).blocked for d in human)
        draftable = check_decision_authority("goal_language").allowed
        return blocked and draftable, f"blocked={blocked} draftable={draftable}"
    return run


def _ny_2d_case():
    def run() -> tuple[bool, str]:
        from .modules.student_privacy import attest_privacy_controls
        bare = attest_privacy_controls("NY")
        full = attest_privacy_controls(
            "NY", written_dpa=True, encryption_at_rest=True,
            encryption_in_transit=True, no_commercial_use=True,
            parent_bill_of_rights=True, nist_aligned=True, dpo_designated=True,
        )
        ok = bare.blocked and full.allowed
        return ok, f"bare_blocked={bare.blocked} full_ok={full.allowed}"
    return run


def _educator_attestation_case():
    def run() -> tuple[bool, str]:
        from .modules.educator_attestation import (
            EducationDraft,
            EducatorAttestation,
            EducatorAttestationError,
            EducatorAttestationLedger,
        )
        led = EducatorAttestationLedger()
        led.register_draft(EducationDraft(
            "d1", "grade_post", "s1", "sch1", "h", drafted_at=1_780_000_000.0,
        ))
        blocked = False
        try:
            led.require_execute("d1")
        except EducatorAttestationError:
            blocked = True
        led.attest(EducatorAttestation(
            "a1", "d1", "t1", "teacher_of_record", "signed", 1_780_000_001.0,
        ))
        return blocked and led.can_execute("d1"), f"blocked={blocked} after={led.can_execute('d1')}"
    return run


def _parent_triage_case():
    def run() -> tuple[bool, str]:
        from .modules.school_comms import (
            AUTONOMOUS_LOGISTICS_TEMPLATES,
            ParentMessage,
            ParentReplyDraft,
            triage_parent_message,
        )
        academic = triage_parent_message(
            ParentMessage("m1", "s1", "Grades", "Why is my child failing?"),
        )
        tid = "calendar_hours"
        logistics = triage_parent_message(
            ParentMessage("m2", "s1", "Calendar", "spirit week schedule"),
            ParentReplyDraft(
                "d1", "m2", AUTONOMOUS_LOGISTICS_TEMPLATES[tid], tid,
            ),
        )
        ok = (not academic.autonomous_allowed) and logistics.autonomous_allowed
        return ok, f"acad_auto={academic.autonomous_allowed} logi_auto={logistics.autonomous_allowed}"
    return run


def _vendor_hygiene_case():
    def run() -> tuple[bool, str]:
        from .modules.vendor_hygiene import VendorContract, check_vendor_contract
        r = check_vendor_contract(VendorContract(
            "c1", "EdTech", "CT",
            written_agreement=True, no_sale_of_student_data=True,
            no_targeted_ads=True, no_non_ed_profiling=True,
            no_train_on_customer_pii=True, board_owns_data=True,
            deletion_on_exit=True,
        ))
        fails = any(f.code == "missing_model_tos" for f in r.findings)
        return fails and not r.passed, f"missing_tos={fails}"
    return run


def _manual_cases() -> list[EvalCase]:
    return [
        EvalCase("vertical.school_system.draft_not_decide", "vertical",
                 "SPED FAPE/placement/eligibility cannot be finalized autonomously.",
                 _draft_not_decide_case()),
        EvalCase("vertical.school_system.ny_2d_privacy", "vertical",
                 "NY 2-d attestation fails without encryption/DPA/Bill of Rights.",
                 _ny_2d_case()),
        EvalCase("vertical.school_system.educator_attestation", "vertical",
                 "Grade post blocked without educator attestation.",
                 _educator_attestation_case()),
        EvalCase("vertical.school_system.parent_triage", "vertical",
                 "Academic parent message is not autonomous; allowlisted logistics is.",
                 _parent_triage_case()),
        EvalCase("vertical.school_system.vendor_hygiene", "vertical",
                 "CT vendor contract missing Model TOS clauses fails hygiene check.",
                 _vendor_hygiene_case()),
    ]


def register() -> None:
    register_vertical_spec(_SCHOOL_SYSTEM_SPEC)
    register_vertical_spec(_EDUCATION_TUTOR_SPEC)
    register_vertical_eval_cases(_manual_cases)
    register_vertical_pack_root(Path(__file__).resolve().parent / "packs")