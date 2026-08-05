"""School system Session 2 modules + teacher credentials tests."""
from __future__ import annotations

from datetime import datetime

from hybridagent_praxis_education.modules.credentials import (
    CESession,
    compliance_status,
    credential_for,
    record_hours,
)
from hybridagent_praxis_education.modules.school_comms import (
    AUTONOMOUS_LOGISTICS_TEMPLATES,
    ParentMessage,
    ParentReplyDraft,
    check_academic_integrity,
    scan_for_mandatory_report_signals,
    triage_parent_message,
)
from hybridagent_praxis_education.modules.school_records import (
    ParentAccessRequest,
    StudentRecordSet,
    assess_student_record_retention,
    fulfill_access,
    open_parent_access_request,
)
from hybridagent_praxis_education.modules.vendor_hygiene import (
    VendorContract,
    check_vendor_contract,
)

NOW = datetime(2026, 6, 1).timestamp()
DAY = 86400.0


# --- E5 teacher credentials ---

def test_teacher_credential_fl_has_pd_hours():
    c = credential_for("t1", "teacher", "FL", "T-123", "2025-07-01")
    assert c is not None
    assert c.profession == "teacher"
    assert c.required_hours == 120.0
    assert c.renewal_cycle_years == 5
    assert "FL DOE" in c.notes or "1012" in c.notes


def test_teacher_credential_ma_exists():
    c = credential_for("t1", "teacher", "MA", "T-9", "2025-01-01")
    assert c is not None
    assert c.profession == "teacher"
    # MA PD hours not encoded → 0 → no_requirement for hour tracking
    assert compliance_status(c) == "no_requirement"


def test_teacher_ce_deficient_when_hours_required():
    c = credential_for("t1", "teacher", "FL", "T-1", "2025-07-01")
    assert c is not None
    assert compliance_status(c) == "ce_deficient"
    record_hours(c, CESession(date="2025-08-01", hours=120.0))
    assert compliance_status(c) in ("current", "expiring_soon")


# --- E10 vendor hygiene ---

def test_ny_vendor_fails_without_2d_controls():
    r = check_vendor_contract(VendorContract(
        "c1", "EdTechCo", "NY", written_agreement=True,
        no_sale_of_student_data=True, no_targeted_ads=True,
        no_non_ed_profiling=True, no_train_on_customer_pii=True,
    ))
    assert not r.passed
    codes = {f.code for f in r.findings}
    assert "missing_parent_bor" in codes or "missing_encryption" in codes


def test_ny_vendor_passes_full_2d():
    r = check_vendor_contract(VendorContract(
        "c1", "EdTechCo", "NY",
        written_agreement=True, parent_bill_of_rights=True,
        no_sale_of_student_data=True, no_targeted_ads=True,
        no_non_ed_profiling=True, encryption_at_rest=True,
        encryption_in_transit=True, deletion_on_exit=True,
        breach_notice_days=7, nist_aligned=True, data_security_plan=True,
        no_train_on_customer_pii=True,
    ))
    assert r.passed


def test_ct_requires_model_tos():
    r = check_vendor_contract(VendorContract(
        "c1", "EdTechCo", "CT",
        written_agreement=True, no_sale_of_student_data=True,
        no_targeted_ads=True, no_non_ed_profiling=True,
        no_train_on_customer_pii=True, board_owns_data=True,
        deletion_on_exit=True,
    ))
    assert not r.passed
    assert any(f.code == "missing_model_tos" for f in r.findings)


def test_fl_deletion_required():
    r = check_vendor_contract(VendorContract(
        "c1", "EdTechCo", "FL",
        written_agreement=True, no_sale_of_student_data=True,
        no_targeted_ads=True, no_non_ed_profiling=True,
        no_train_on_customer_pii=True,
    ))
    assert not r.passed
    assert any("deletion" in f.code for f in r.findings)


# --- E7 records ---

def test_ma_transcript_60_years():
    rec = StudentRecordSet("r1", "s1", "MA", "transcript", NOW - 10 * DAY)
    rep = assess_student_record_retention(rec, now=NOW)
    assert rep.retain_years == 60
    assert rep.status == "active"


def test_legal_hold_blocks_disposal():
    rec = StudentRecordSet(
        "r1", "s1", "MA", "temporary", NOW - 20 * 365.25 * DAY, legal_hold=True,
    )
    rep = assess_student_record_retention(rec, now=NOW)
    assert rep.status == "legal_hold"


def test_parent_access_ferpa_45():
    wf = open_parent_access_request(ParentAccessRequest(
        "a1", "s1", "PA", NOW,
    ))
    assert wf.access_days == 45
    assert wf.refresh(now=NOW + 10 * DAY) == "open"
    assert wf.refresh(now=NOW + 50 * DAY) == "overdue"
    fulfill_access(wf, fulfilled_at=NOW + 10 * DAY)
    assert wf.status == "fulfilled" or wf.fulfilled_at > 0


# --- E6 parent triage ---

def test_academic_parent_message_held():
    msg = ParentMessage("m1", "s1", "Grades", "Why is my child failing math?", "NY")
    r = triage_parent_message(msg)
    assert r.classification == "academic"
    assert not r.autonomous_allowed


def test_logistics_allowlisted_autonomous():
    msg = ParentMessage("m2", "s1", "Calendar", "When is spirit week?", "FL")
    body = AUTONOMOUS_LOGISTICS_TEMPLATES["calendar_hours"]
    reply = ParentReplyDraft("d1", "m2", body, template_id="calendar_hours")
    r = triage_parent_message(msg, reply)
    assert r.classification == "logistics"
    assert r.autonomous_allowed


def test_sped_parent_message_held():
    msg = ParentMessage("m3", "s1", "IEP meeting", "About my child's IEP placement", "PA")
    r = triage_parent_message(msg)
    assert r.classification == "sped_sensitive"
    assert not r.autonomous_allowed


# --- E8 integrity ---

def test_complete_answers_blocked():
    r = check_academic_integrity(
        context="summative_graded", student_facing=True,
        provides_complete_answers=True, state="OH",
    )
    assert not r.allowed


def test_teacher_lesson_plan_ok():
    r = check_academic_integrity(
        context="lesson_plan_teacher", student_facing=False,
        provides_complete_answers=True, state="OH",
    )
    assert r.allowed


def test_oh_ai_policy_reminder():
    r = check_academic_integrity(
        context="formative_feedback", student_facing=True,
        provides_complete_answers=False, state="OH",
    )
    assert r.allowed
    assert any("AI policy" in f for f in r.findings)


# --- E9 mandatory report ---

def test_mandatory_report_remind_not_file():
    rem = scan_for_mandatory_report_signals(
        "Student disclosed abuse at home", state="FL",
    )
    assert rem.should_remind
    assert rem.may_auto_file is False
    assert "never file" in rem.message.lower() or "reporter of record" in rem.message.lower()


def test_no_false_positive_report():
    rem = scan_for_mandatory_report_signals("Student loves science class", state="FL")
    assert not rem.should_remind
