"""Tests for expanded program detection, LLM program wiring, and notification routing.

Note: 10-state coverage (TX, CA, FL, PA, OH, NY, NC, GA, VA, AZ) in state
monitoring is by design (issue #11). This test file covers program detection
patterns added for all 11 categories (3 existing + 8 new).
"""

import pytest
from unittest.mock import patch

from src.state.common import detect_program
from src.state.classify import ClassificationResult, classify_by_llm
from src.state.db_helpers import (
    insert_state_signal,
    insert_state_classification,
    get_unnotified_signals,
    mark_signal_notified,
)


# --- Original 3 program categories ---


class TestProgramDetectionOriginal:
    """Tests for the original 3 program categories."""

    def test_pact_act_pact_act(self):
        assert detect_program("New PACT Act outreach event in Texas") == "pact_act"

    def test_pact_act_toxic_exposure(self):
        assert detect_program("Toxic exposure screening available") == "pact_act"

    def test_pact_act_burn_pit(self):
        assert detect_program("Burn pit registry update") == "pact_act"

    def test_community_care_keyword(self):
        assert detect_program("VA community care network expansion") == "community_care"

    def test_community_care_mission_act(self):
        assert detect_program("MISSION Act implementation update") == "community_care"

    def test_community_care_ccn(self):
        assert detect_program("New CCN providers added") == "community_care"

    def test_vha_keyword(self):
        assert detect_program("Veterans Health Administration report") == "vha"

    def test_vha_hospital(self):
        assert detect_program("VA hospital expansion project") == "vha"

    def test_vha_vamc(self):
        assert detect_program("VAMC renovation complete") == "vha"


# --- 8 new program categories ---


class TestProgramDetectionNew:
    """Tests for the 8 new program categories."""

    def test_disability_compensation_rating(self):
        assert detect_program("Disability rating increase announced") == "disability_compensation"

    def test_disability_compensation_cp_exam(self):
        assert detect_program("C&P exam scheduling changes") == "disability_compensation"

    def test_disability_compensation_service_connected(self):
        assert detect_program("Service-connected disability claim backlog") == "disability_compensation"

    def test_education_gi_bill(self):
        assert detect_program("GI Bill benefits expanded for veterans") == "education"

    def test_education_chapter_33(self):
        assert detect_program("Chapter 33 education benefit update") == "education"

    def test_education_post_911(self):
        assert detect_program("Post-9/11 GI Bill changes") == "education"

    def test_education_voc_rehab(self):
        assert detect_program("Voc rehab program accepting applications") == "education"

    def test_mental_health_ptsd(self):
        assert detect_program("PTSD treatment options expanding") == "mental_health"

    def test_mental_health_suicide_prevention(self):
        assert detect_program("Suicide prevention hotline funding") == "mental_health"

    def test_mental_health_vet_center(self):
        assert detect_program("New vet center opening in Dallas") == "mental_health"

    def test_mental_health_behavioral(self):
        assert detect_program("Behavioral health services expanded") == "mental_health"

    def test_housing_hud_vash(self):
        assert detect_program("HUD-VASH vouchers available") == "housing"

    def test_housing_voucher(self):
        assert detect_program("Housing voucher program for veterans") == "housing"

    def test_housing_ssvf(self):
        assert detect_program("SSVF grants awarded to providers") == "housing"

    def test_caregiver_keyword(self):
        assert detect_program("Caregiver support program update") == "caregiver"

    def test_caregiver_aid_attendance(self):
        assert detect_program("Aid and attendance benefit changes") == "caregiver"

    def test_caregiver_respite(self):
        assert detect_program("Respite care services expanded") == "caregiver"

    def test_homelessness_homeless(self):
        assert detect_program("Homeless veteran services funding") == "homelessness"

    def test_homelessness_stand_down(self):
        assert detect_program("Annual stand down event planned") == "homelessness"

    def test_homelessness_grant_per_diem(self):
        assert detect_program("Grant and per diem program update") == "homelessness"

    def test_homelessness_hchv(self):
        assert detect_program("HCHV outreach workers deployed") == "homelessness"

    def test_employment_vre(self):
        assert detect_program("VR&E program accepting applications") == "employment"

    def test_employment_vocational_rehab(self):
        assert detect_program("Vocational rehabilitation services") == "employment"

    def test_employment_hire_heroes(self):
        assert detect_program("Hire Heroes USA partnership") == "employment"

    def test_employment_veteran_readiness(self):
        assert detect_program("Veteran readiness program launch") == "employment"

    def test_burial_benefit(self):
        assert detect_program("Burial benefit eligibility expanded") == "burial"

    def test_burial_national_cemetery(self):
        assert detect_program("National cemetery dedication ceremony") == "burial"

    def test_burial_headstone(self):
        assert detect_program("Headstone application process updated") == "burial"

    def test_burial_pre_need(self):
        assert detect_program("Pre-need eligibility determination") == "burial"


class TestProgramDetectionEdgeCases:
    """Edge cases for program detection."""

    def test_no_match(self):
        assert detect_program("Local bakery opens new location") is None

    def test_empty_string(self):
        assert detect_program("") is None

    def test_case_insensitive(self):
        assert detect_program("PTSD TREATMENT AVAILABLE") == "mental_health"

    def test_first_match_wins(self):
        """When text matches multiple programs, first defined wins."""
        # "pact_act" is defined before others
        result = detect_program("PACT Act burn pit disability claim")
        assert result == "pact_act"


# --- LLM program field wiring ---


class TestLLMProgramField:
    """Test that classify_by_llm returns program field from LLM response."""

    def test_llm_returns_program_field(self):
        mock_response = {
            "is_specific_event": True,
            "federal_program": "community_care",
            "severity": "medium",
            "reasoning": "Policy shift in community care",
        }

        with patch("src.state.classify._call_haiku") as mock_haiku:
            mock_haiku.return_value = mock_response
            result = classify_by_llm(
                title="CalVet community care changes",
                content="The state is modifying...",
                state="CA",
            )

        assert result.program == "community_care"
        assert result.severity == "medium"
        assert result.method == "llm"

    def test_llm_returns_none_program(self):
        mock_response = {
            "is_specific_event": True,
            "federal_program": None,
            "severity": "low",
            "reasoning": "Routine news",
        }

        with patch("src.state.classify._call_haiku") as mock_haiku:
            mock_haiku.return_value = mock_response
            result = classify_by_llm(
                title="Veterans day parade",
                content="Annual event...",
                state="TX",
            )

        assert result.program is None
        assert result.severity == "low"

    def test_llm_noise_still_captures_program(self):
        mock_response = {
            "is_specific_event": False,
            "federal_program": "pact_act",
            "severity": "noise",
            "reasoning": "General explainer",
        }

        with patch("src.state.classify._call_haiku") as mock_haiku:
            mock_haiku.return_value = mock_response
            result = classify_by_llm(
                title="What is the PACT Act",
                content="Explainer article...",
                state="TX",
            )

        assert result.severity == "noise"
        assert result.program == "pact_act"

    def test_keyword_classification_has_no_program(self):
        """Keyword classification does not set program field."""
        from src.state.classify import classify_by_keywords

        result = classify_by_keywords(
            title="Investigation into VA facility",
            content="Officials launched...",
        )
        assert result.program is None


# --- Notification routing ---


class TestNotificationRouting:
    """Test that medium/low severity signals get marked as digest_queued."""

    def _insert_signal_and_classify(self, signal_id, severity):
        """Helper to insert a signal and its classification."""
        insert_state_signal({
            "signal_id": signal_id,
            "state": "TX",
            "source_id": "tx_tvc_news",
            "title": f"Test signal {severity}",
            "url": f"https://example.com/{signal_id}",
        })
        insert_state_classification({
            "signal_id": signal_id,
            "severity": severity,
            "classification_method": "keyword",
        })

    def test_medium_signals_get_digest_queued(self):
        self._insert_signal_and_classify("sig_medium_001", "medium")

        # Verify signal appears as unnotified
        unnotified = get_unnotified_signals(severity="medium")
        assert len(unnotified) == 1
        assert unnotified[0]["signal_id"] == "sig_medium_001"

        # Mark as digest_queued (same as runner does)
        mark_signal_notified("sig_medium_001", "digest_queued")

        # Should no longer appear as unnotified
        unnotified = get_unnotified_signals(severity="medium")
        assert len(unnotified) == 0

    def test_low_signals_get_digest_queued(self):
        self._insert_signal_and_classify("sig_low_001", "low")

        unnotified = get_unnotified_signals(severity="low")
        assert len(unnotified) == 1

        mark_signal_notified("sig_low_001", "digest_queued")

        unnotified = get_unnotified_signals(severity="low")
        assert len(unnotified) == 0

    def test_high_signals_not_affected_by_digest(self):
        """High severity signals use email, not digest_queued."""
        self._insert_signal_and_classify("sig_high_001", "high")

        unnotified = get_unnotified_signals(severity="high")
        assert len(unnotified) == 1

        # High signals get marked with "email" channel, not digest_queued
        mark_signal_notified("sig_high_001", "email")

        unnotified = get_unnotified_signals(severity="high")
        assert len(unnotified) == 0

    def test_multiple_severity_levels_queued(self):
        """Verify mixed severity signals are routed correctly."""
        self._insert_signal_and_classify("sig_mix_high", "high")
        self._insert_signal_and_classify("sig_mix_med", "medium")
        self._insert_signal_and_classify("sig_mix_low", "low")

        # All three should be unnotified
        all_unnotified = get_unnotified_signals()
        assert len(all_unnotified) == 3

        # Route: high -> email, medium/low -> digest_queued
        mark_signal_notified("sig_mix_high", "email")
        for severity_level in ("medium", "low"):
            digest_signals = get_unnotified_signals(severity=severity_level)
            for sig_data in digest_signals:
                mark_signal_notified(sig_data["signal_id"], "digest_queued")

        # All should now be notified
        all_unnotified = get_unnotified_signals()
        assert len(all_unnotified) == 0
