"""13-state EDUCATION profile registry tests (Gap E1 — school_system pack)."""
from __future__ import annotations

import pytest
from hybridagent.jurisdictions import (
    EducationProfile,
    education_summary,
    get_education_profile,
    registered_states,
)

STATES = registered_states()


@pytest.mark.parametrize("state", STATES)
def test_every_state_has_education_profile(state):
    p = get_education_profile(state)
    assert p is not None
    assert isinstance(p, EducationProfile)
    assert p.state == state.upper()
    assert p.sea_name
    assert p.privacy_tier in (
        "ferpa_floor", "enhanced_operator", "ct_contract", "ny_2d_ceiling",
    )
    assert p.sped_eval_timeline_days > 0
    assert p.transition_planning_age in (14, 15, 16)


def test_only_ny_is_2d_ceiling():
    ceilings = [
        s.upper() for s in STATES
        if (p := get_education_profile(s)) and p.privacy_tier == "ny_2d_ceiling"
    ]
    assert ceilings == ["NY"]


def test_only_ct_is_contract_tier():
    cts = [
        s.upper() for s in STATES
        if (p := get_education_profile(s)) and p.privacy_tier == "ct_contract"
    ]
    assert cts == ["CT"]


def test_oh_requires_ai_policy():
    oh = get_education_profile("OH")
    assert oh is not None
    assert oh.ai_policy_required is True
    assert "3301.24" in oh.ai_policy_citation or "2026" in oh.ai_policy_citation


def test_only_oh_ai_policy_required_among_13():
    req = [
        s.upper() for s in STATES
        if (p := get_education_profile(s)) and p.ai_policy_required
    ]
    assert req == ["OH"]


def test_wv_bans_affective_computing():
    wv = get_education_profile("WV")
    assert wv is not None
    assert wv.affective_computing_banned is True
    assert "18-2-5h" in wv.privacy_citation or "18-2-5h" in wv.operator_citation


def test_fl_sopipa_deletion_and_biometrics():
    fl = get_education_profile("FL")
    assert fl is not None
    assert fl.operator_law is True
    assert fl.deletion_days_after_exit == 90
    assert fl.biometric_collection_banned is True
    assert fl.parent_ai_interaction_access is True
    assert fl.closed_system_ai_preferred is True
    assert "1006.1494" in fl.operator_citation or "1006.1494" in fl.privacy_citation


def test_oh_deletion_90():
    oh = get_education_profile("OH")
    assert oh is not None
    assert oh.deletion_days_after_exit == 90
    assert oh.operator_law is True


def test_ny_2d_features():
    ny = get_education_profile("NY")
    assert ny is not None
    assert ny.encryption_required is True
    assert ny.parent_bill_of_rights_required is True
    assert ny.teacher_appr_data_protected is True
    assert ny.vendor_breach_notice_days == 7


def test_ma_transcript_retention_60():
    ma = get_education_profile("MA")
    assert ma is not None
    assert ma.transcript_retention_years == 60
    assert ma.temporary_record_retention_years == 7


def test_va_ai_generated_content_instruction():
    va = get_education_profile("VA")
    assert va is not None
    assert va.ai_generated_content_instruction is True
    assert va.operator_law is True


def test_education_summary_has_13():
    s = education_summary()
    assert len(s) == 13
    assert {x["state"] for x in s} == {st.upper() for st in STATES}


def test_loader_case_insensitive():
    assert get_education_profile("ny") is not None
    assert get_education_profile("NY") is not None
