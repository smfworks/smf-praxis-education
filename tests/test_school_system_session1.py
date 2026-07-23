"""Student privacy (E2), SPED guardrails (E3), educator attestation (E4) tests."""
from __future__ import annotations

from datetime import datetime

import pytest

from hybridagent_praxis_education.modules.educator_attestation import (
    EducationDraft,
    EducatorAttestation,
    EducatorAttestationError,
    EducatorAttestationLedger,
)
from hybridagent_praxis_education.modules.sped_guardrails import (
    IepDraft,
    SpedCase,
    SpedGuardrailError,
    assert_not_human_decision,
    check_decision_authority,
    check_iep_draft,
    check_timeline,
)
from hybridagent_praxis_education.modules.student_privacy import (
    DisclosureEvent,
    DisclosureLedger,
    attest_privacy_controls,
    check_collection,
    check_commercial_use,
    check_operator_deletion,
    check_purpose_access,
    check_vendor_breach_notice,
    record_disclosure,
)

NOW = datetime(2026, 6, 1).timestamp()
DAY = 86400.0


# --- E2 student privacy ---

def test_commercial_purpose_blocked():
    r = check_purpose_access(
        state="FL", data_class="education_record", purpose="commercial",
    )
    assert r.blocked
    assert any(f.code == "prohibited_purpose" for f in r.findings)


def test_model_training_blocked():
    r = check_commercial_use(state="NY", use="train_foundation_model_on_pii")
    assert r.blocked


def test_education_delivery_allows_sped():
    r = check_purpose_access(
        state="PA", data_class="special_education", purpose="education_delivery",
    )
    assert r.allowed


def test_directory_only_for_directory_pub():
    r = check_purpose_access(
        state="MA", data_class="education_record", purpose="directory_publication",
    )
    assert r.blocked


def test_fl_biometric_banned():
    r = check_collection(state="FL", collect_biometrics=True)
    assert r.blocked
    assert any(f.code == "biometric_banned" for f in r.findings)


def test_wv_affective_banned():
    r = check_collection(state="WV", collect_affective=True)
    assert r.blocked


def test_ny_vendor_breach_7_days():
    r = check_vendor_breach_notice(
        state="NY", discovered_at=NOW, notified_lea_at=NOW + 8 * DAY,
    )
    assert r.blocked
    r2 = check_vendor_breach_notice(
        state="NY", discovered_at=NOW, notified_lea_at=NOW + 3 * DAY,
    )
    assert r2.allowed


def test_fl_deletion_90_days():
    r = check_operator_deletion(
        state="FL", student_exit_at=NOW - 100 * DAY, deleted_at=None, now=NOW,
    )
    assert r.blocked
    r2 = check_operator_deletion(
        state="FL", student_exit_at=NOW - 10 * DAY, deleted_at=None, now=NOW,
    )
    assert r2.allowed


def test_ny_2d_attestation_fails_without_controls():
    r = attest_privacy_controls("NY")
    assert r.blocked
    assert any(f.code == "missing_dpa" for f in r.findings)


def test_ny_2d_attestation_passes_full_controls():
    r = attest_privacy_controls(
        "NY", written_dpa=True, encryption_at_rest=True,
        encryption_in_transit=True, no_commercial_use=True,
        parent_bill_of_rights=True, nist_aligned=True, dpo_designated=True,
    )
    assert r.allowed


def test_disclosure_ledger_records():
    ledger = DisclosureLedger()
    ev = DisclosureEvent(
        "e1", "s1", "VA", "education_record", "education_delivery",
        "school_official", "teacher-1", NOW,
    )
    _, report = record_disclosure(ledger, ev)
    assert report.allowed
    assert len(ledger.for_student("s1")) == 1


# --- E3 SPED ---

def test_eval_overdue():
    case = SpedCase("c1", "s1", "PA", referral_at=NOW - 90 * DAY)
    r = check_timeline(case, now=NOW)
    assert any(f.code == "eval_overdue" for f in r.findings)


def test_eval_on_time():
    case = SpedCase(
        "c1", "s1", "PA", referral_at=NOW - 10 * DAY,
        milestones=(("eval_complete", NOW - 1 * DAY),),
    )
    r = check_timeline(case, now=NOW)
    assert not any(f.code == "eval_overdue" for f in r.findings)


def test_human_only_eligibility():
    r = check_decision_authority("eligibility")
    assert r.blocked
    with pytest.raises(SpedGuardrailError):
        assert_not_human_decision("eligibility")


def test_goal_language_draftable():
    r = check_decision_authority("goal_language")
    assert r.allowed


def test_mass_iep_flag():
    case = SpedCase("c1", "s1", "NY", NOW, has_baseline_data=False)
    draft = IepDraft("d1", "c1", "goals", "hash", has_baseline_link=False)
    r = check_iep_draft(case, draft)
    assert any(f.code == "mass_iep_risk" for f in r.findings)


def test_iep_draft_proposing_placement_blocked():
    case = SpedCase("c1", "s1", "FL", NOW, has_baseline_data=True)
    draft = IepDraft(
        "d1", "c1", "placement", "hash", has_baseline_link=True,
        proposes_decision="placement",
    )
    r = check_iep_draft(case, draft)
    assert r.blocked


def test_transition_missing():
    case = SpedCase("c1", "s1", "OH", NOW, student_age=16)
    r = check_timeline(case, now=NOW)
    assert any(f.code == "transition_missing" for f in r.findings)


# --- E4 educator attestation ---

def test_grade_post_requires_attestation():
    led = EducatorAttestationLedger()
    d = EducationDraft(
        "d1", "grade_post", "s1", "sch1", "h", drafted_at=NOW, state="MA",
    )
    led.register_draft(d)
    with pytest.raises(EducatorAttestationError):
        led.require_execute("d1")
    led.attest(EducatorAttestation(
        "a1", "d1", "t1", "teacher_of_record", "signed", NOW + 1,
    ))
    led.require_execute("d1")


def test_wrong_role_cannot_attest_discipline():
    led = EducatorAttestationLedger()
    led.register_draft(EducationDraft(
        "d2", "discipline_letter", "s1", "sch1", "h", drafted_at=NOW,
    ))
    with pytest.raises(EducatorAttestationError):
        led.attest(EducatorAttestation(
            "a2", "d2", "t1", "teacher_of_record", "signed", NOW,
        ))


def test_mandatory_report_never_auto_execute():
    led = EducatorAttestationLedger()
    led.register_draft(EducationDraft(
        "d3", "mandatory_report_draft", "s1", "sch1", "h", drafted_at=NOW,
    ))
    led.attest(EducatorAttestation(
        "a3", "d3", "t1", "teacher_of_record", "signed", NOW,
    ))
    assert not led.can_execute("d3")
    with pytest.raises(EducatorAttestationError):
        led.require_execute("d3")


def test_iep_adoption_case_manager():
    led = EducatorAttestationLedger()
    led.register_draft(EducationDraft(
        "d4", "iep_adoption", "s1", "sch1", "h", drafted_at=NOW,
    ))
    led.attest(EducatorAttestation(
        "a4", "d4", "cm1", "case_manager", "signed", NOW,
    ))
    assert led.can_execute("d4")
