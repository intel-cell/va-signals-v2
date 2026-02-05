"""Tests for Policy-to-Operations Translator.

CHARLIE COMMAND - Phase 2: Translator validation.
"""

import pytest

from src.signals.impact.translator import (
    PolicyToOperationsTranslator,
    TranslationContext,
    translate_bill_to_impact,
    translate_hearing_to_impact,
    translate_fr_to_impact,
)
from src.signals.impact.models import (
    Posture,
    ConfidenceLevel,
    RiskLevel,
)
from src.signals.envelope import Envelope


class TestPolicyToOperationsTranslator:
    """Test the main translator class."""

    @pytest.fixture
    def translator(self):
        return PolicyToOperationsTranslator()

    def test_identify_claims_workflows(self, translator):
        """Test workflow identification for claims-related text."""
        text = "This bill addresses the disability rating process and appeals backlog"
        workflows = translator._identify_workflows("VA Claims Bill", text)

        assert "rating" in workflows
        assert "appeals" in workflows

    def test_identify_accreditation_workflows(self, translator):
        """Test workflow identification for accreditation-related text."""
        text = "Amends 38 CFR Part 14 regarding accreditation of agents and attorneys"
        workflows = translator._identify_workflows("Accreditation Reform", text)

        assert "accreditation" in workflows

    def test_identify_exam_workflows(self, translator):
        """Test workflow identification for C&P exam-related text."""
        text = "Addresses C&P examination wait times and contractor performance"
        workflows = translator._identify_workflows("Exam Quality", text)

        assert "exam_scheduling" in workflows

    def test_assess_compliance_risk_high(self, translator):
        """Test high compliance risk detection."""
        text = "Veterans must comply with the new requirements. Mandatory reporting shall be enforced with penalties for violation."
        risk = translator._assess_compliance_risk(text)

        assert risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_assess_compliance_risk_low(self, translator):
        """Test low compliance risk detection."""
        text = "This informational notice provides updates on claims processing improvements."
        risk = translator._assess_compliance_risk(text)

        assert risk in (RiskLevel.LOW, RiskLevel.NEGLIGIBLE)

    def test_assess_reputational_risk(self, translator):
        """Test reputational risk detection."""
        text = "GAO investigation found deficiencies. VSO groups including DAV and VFW have expressed concerns in the media."
        risk = translator._assess_reputational_risk(text)

        assert risk in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_determine_posture_high_compliance(self, translator):
        """Test posture for high compliance risk."""
        posture = translator._determine_posture(
            RiskLevel.HIGH, RiskLevel.LOW, "rule"
        )
        assert posture == Posture.OPPOSE

    def test_determine_posture_monitoring(self, translator):
        """Test monitoring posture for low risk."""
        posture = translator._determine_posture(
            RiskLevel.LOW, RiskLevel.LOW, "bill"
        )
        assert posture == Posture.MONITOR

    def test_translate_context_to_memo(self, translator):
        """Test full translation from context to impact memo."""
        context = TranslationContext(
            source_type="bill",
            vehicle_id="hr-1234",
            title="Veterans Benefits Modernization Act",
            body_text="This legislation requires VA to modernize claims processing systems and reduce the disability rating backlog.",
            source_url="https://congress.gov/bill/119/hr/1234",
            published_at="2026-01-15",
        )

        memo = translator.translate(context)

        assert memo.memo_id.startswith("MEMO-")
        assert memo.issue_id == "BILL-hr-1234"
        assert memo.policy_hook.vehicle == "hr-1234"
        assert memo.policy_hook.vehicle_type == "bill"
        assert len(memo.why_it_matters.affected_workflows) > 0
        assert memo.our_posture in [Posture.MONITOR, Posture.NEUTRAL_ENGAGED, Posture.SUPPORT, Posture.OPPOSE]

    def test_translate_envelope(self, translator):
        """Test translation from Envelope to impact memo."""
        envelope = Envelope(
            event_id="bill-hr-5678",
            authority_id="hr-5678",
            authority_source="congress_gov",
            authority_type="bill_text",
            title="VA Appeals Modernization Enhancement Act",
            body_text="Addresses higher level review and Board of Veterans Appeals processing times.",
            source_url="https://congress.gov/bill/119/hr/5678",
        )

        memo = translator.translate_envelope(envelope)

        assert "appeals" in memo.why_it_matters.affected_workflows or "bva" in memo.why_it_matters.affected_workflows
        assert memo.policy_hook.vehicle == "hr-5678"


class TestBillTranslation:
    """Test bill-specific translation."""

    def test_translate_claims_bill(self):
        """Test translation of a claims-related bill."""
        bill = {
            "bill_id": "hr-101",
            "congress": 119,
            "bill_type": "HR",
            "bill_number": 101,
            "title": "Veterans Claims Processing Acceleration Act",
            "latest_action_text": "Referred to the Committee on Veterans' Affairs",
            "introduced_date": "2026-01-10",
        }

        memo = translate_bill_to_impact(bill)

        assert memo.policy_hook.vehicle_type == "bill"
        assert "claims" in memo.what_it_does.lower() or "bill" in memo.what_it_does.lower()
        assert memo.decision_trigger  # Should have a decision trigger

    def test_translate_bill_generates_unique_memo_id(self):
        """Test that each translation generates a unique memo ID."""
        bill = {
            "bill_id": "hr-102",
            "congress": 119,
            "bill_type": "HR",
            "bill_number": 102,
            "title": "Test Bill",
            "latest_action_text": "Introduced",
        }

        memo1 = translate_bill_to_impact(bill)
        memo2 = translate_bill_to_impact(bill)

        assert memo1.memo_id != memo2.memo_id


class TestHearingTranslation:
    """Test hearing-specific translation."""

    def test_translate_oversight_hearing(self):
        """Test translation of an oversight hearing."""
        hearing = {
            "event_id": "hvac-2026-001",
            "title": "Examining VA Claims Backlog and Processing Times",
            "committee_code": "HVAC",
            "committee_name": "House Committee on Veterans' Affairs",
            "hearing_date": "2026-02-15",
            "url": "https://veterans.house.gov/hearing/2026-001",
        }

        memo = translate_hearing_to_impact(hearing)

        assert memo.policy_hook.vehicle_type == "hearing"
        assert "hearing" in memo.what_it_does.lower()
        assert memo.why_it_matters.affected_workflows  # Should identify workflows


class TestFRTranslation:
    """Test Federal Register document translation."""

    def test_translate_proposed_rule(self):
        """Test translation of a proposed rule."""
        fr_doc = {
            "doc_id": "FR-2026-01-15-001",
            "summary": "The Department of Veterans Affairs proposes to amend its disability rating schedule.",
            "veteran_impact": "Would affect how disability ratings are calculated for musculoskeletal conditions.",
            "source_url": "https://federalregister.gov/d/2026-00123",
            "published_date": "2026-01-15",
            "tags": ["disability", "rating", "vasrd"],
        }

        memo = translate_fr_to_impact(fr_doc)

        assert memo.policy_hook.vehicle_type == "rule"
        assert "rating" in memo.why_it_matters.affected_workflows
        assert memo.confidence_level  # Should have confidence level


class TestDomainKnowledge:
    """Test domain knowledge mappings."""

    @pytest.fixture
    def translator(self):
        return PolicyToOperationsTranslator()

    def test_workflow_mappings_coverage(self, translator):
        """Test that key VBA workflows have keyword mappings."""
        expected_workflows = [
            "claims_intake",
            "claims_development",
            "rating",
            "appeals",
            "bva",
            "exam_scheduling",
            "accreditation",
        ]

        for workflow in expected_workflows:
            assert workflow in translator.workflow_mappings
            assert len(translator.workflow_mappings[workflow]) > 0

    def test_workflows_have_descriptions(self, translator):
        """Test that VBA workflows have proper metadata."""
        for workflow_id, workflow in translator.workflows.items():
            assert "name" in workflow
            assert "description" in workflow
            assert "metrics" in workflow

    def test_status_detection(self, translator):
        """Test policy status detection."""
        introduced_text = "The bill was introduced and referred to committee"
        status = translator._detect_status("bill", introduced_text)
        assert status == "introduced"

        markup_text = "The committee ordered to be reported"
        status = translator._detect_status("bill", markup_text)
        assert status == "committee_action"

    def test_affected_veterans_estimation(self, translator):
        """Test affected veteran count estimation."""
        # High volume workflows
        high_volume = ["claims_intake", "rating"]
        estimate = translator._estimate_affected_veterans(high_volume)
        assert estimate is not None
        assert "annually" in estimate

        # Low volume workflows
        low_volume = ["accreditation"]
        estimate = translator._estimate_affected_veterans(low_volume)
        # May return None or a lower estimate

    def test_recommended_action_generation(self, translator):
        """Test recommended action is generated based on posture."""
        action_oppose = translator._generate_recommended_action(
            Posture.OPPOSE, RiskLevel.HIGH, "rule"
        )
        assert "comment" in action_oppose.lower() or "oppose" in action_oppose.lower()

        action_monitor = translator._generate_recommended_action(
            Posture.MONITOR, RiskLevel.LOW, "bill"
        )
        assert "track" in action_monitor.lower() or "monitor" in action_monitor.lower()


class TestIntegration:
    """Integration tests for the translator."""

    def test_end_to_end_bill_translation(self):
        """Test complete bill translation pipeline."""
        bill = {
            "bill_id": "hr-999",
            "congress": 119,
            "bill_type": "HR",
            "bill_number": 999,
            "title": "Comprehensive Veterans Benefits Reform Act of 2026",
            "latest_action_text": "Passed House; received in Senate and referred to Committee on Veterans' Affairs",
            "introduced_date": "2026-01-05",
            "policy_area": "Armed Forces and National Security",
        }

        memo = translate_bill_to_impact(bill)

        # Verify all required fields are populated
        assert memo.memo_id
        assert memo.issue_id
        assert memo.generated_date
        assert memo.policy_hook.vehicle
        assert memo.what_it_does
        assert memo.why_it_matters.operational_impact
        assert memo.our_posture
        assert memo.recommended_action
        assert memo.decision_trigger
        assert memo.confidence_level

        # Verify serialization works
        memo_dict = memo.to_dict()
        assert "memo_id" in memo_dict
        assert "policy_hook" in memo_dict
        assert "why_it_matters" in memo_dict
