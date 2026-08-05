"""School System pack — 13-state integration (Session 2)."""
from __future__ import annotations

from pathlib import Path

import pytest
from hybridagent import config as cfg
from hybridagent import pack
from hybridagent.jurisdictions import get_education_profile, registered_states

from hybridagent_praxis_education.modules.educator_attestation import (
    EducationDraft,
    EducatorAttestation,
    EducatorAttestationLedger,
)
from hybridagent_praxis_education.modules.school_comms import check_academic_integrity
from hybridagent_praxis_education.modules.sped_guardrails import (
    check_decision_authority,
)
from hybridagent_praxis_education.modules.student_privacy import (
    attest_privacy_controls,
    check_collection,
    check_commercial_use,
)
from hybridagent_praxis_education.modules.vendor_hygiene import (
    VendorContract,
    check_vendor_contract,
)

STATES = registered_states()
NOW = 1_780_000_000.0


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv(cfg.ENV_HOME, str(tmp_path / ".praxis"))


def test_school_system_pack_activates(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    p = pack.activate("school_system")
    assert p is not None
    assert p.name == "school_system"
    assert cfg.get_active_pack_name() == "school_system"
    pack.deactivate()


@pytest.mark.parametrize("state", STATES)
def test_every_state_education_profile_usable(state):
    p = get_education_profile(state)
    assert p is not None
    assert p.privacy_tier
    assert p.sped_eval_timeline_days >= 30


@pytest.mark.parametrize("state", STATES)
def test_commercial_blocked_in_all_states(state):
    r = check_commercial_use(state=state, use="targeted_advertising")
    assert r.blocked


@pytest.mark.parametrize("state", STATES)
def test_fape_never_autonomous(state):
    # state unused — human-only is federal/product rule
    r = check_decision_authority("fape")
    assert r.blocked


def test_wv_affective_and_fl_biometric_across_pack():
    assert check_collection(state="WV", collect_affective=True).blocked
    assert check_collection(state="FL", collect_biometrics=True).blocked


def test_ny_attestation_stricter_than_pa():
    bare = {"written_dpa": True, "no_commercial_use": True}
    ny = attest_privacy_controls("NY", **bare)
    pa = attest_privacy_controls("PA", **bare)
    assert ny.blocked  # needs encryption, BOR, NIST, DPO
    assert pa.allowed or not pa.blocked


def test_grade_post_needs_attestation_in_pack_flow():
    led = EducatorAttestationLedger()
    led.register_draft(EducationDraft(
        "d1", "grade_post", "s1", "sch1", "h", drafted_at=NOW, state="NY",
    ))
    assert not led.can_execute("d1")
    led.attest(EducatorAttestation(
        "a1", "d1", "t1", "teacher_of_record", "signed", NOW,
    ))
    assert led.can_execute("d1")


def test_oh_ai_policy_and_fl_deletion_in_vendor_checks():
    oh_prof = get_education_profile("OH")
    fl_prof = get_education_profile("FL")
    assert oh_prof is not None and oh_prof.ai_policy_required
    assert fl_prof is not None and fl_prof.deletion_days_after_exit == 90
    r = check_vendor_contract(VendorContract(
        "c1", "AITutor", "FL",
        written_agreement=True, no_sale_of_student_data=True,
        no_targeted_ads=True, no_non_ed_profiling=True,
        no_train_on_customer_pii=True, deletion_on_exit=True,
    ))
    assert r.passed


def test_integrity_blocks_student_cheatsheet():
    r = check_academic_integrity(
        context="homework_complete_answers", student_facing=True,
        provides_complete_answers=True, state="MA",
    )
    assert not r.allowed


def test_school_system_persona_guardrails(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    p = pack.load_pack("school_system")
    assert p is not None
    text = p.system_prompt.lower()
    assert "fape" in text or "placement" in text
    assert "ferpa" in text or "2-d" in text or "education records" in text
    assert p.compliance_mode == "enforced"


def test_school_system_knowledge_covers_13_states(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    loaded = pack.load_pack("school_system")
    assert loaded is not None
    kb = (Path(loaded.path) / "knowledge.md").read_text(encoding="utf-8")
    for st in ("FL", "GA", "SC", "TN", "VA", "WV", "MD", "PA", "OH", "NJ", "NY", "CT", "MA"):
        assert st in kb


def test_school_system_skills_present(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    p = pack.load_pack("school_system")
    assert p is not None
    names = {s["name"] if isinstance(s, dict) else s.name for s in p.skills}
    assert "sped-draft-not-decide" in names
    assert "ferpa-operator-privacy" in names
    assert "educator-attestation" in names


def test_school_system_risk_policy_holds_send(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    p = pack.load_pack("school_system")
    assert p is not None
    dual = {x.lower() for x in p.risk_policy.get("dualApprovalRisks", [])}
    assert "send" in dual
    assert "destructive" in dual
