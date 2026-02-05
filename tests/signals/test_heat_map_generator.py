"""Tests for Heat Map Generator.

CHARLIE COMMAND - Phase 3: Heat Map Generator validation.
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.signals.impact.heat_map_generator import (
    HeatMapGenerator,
    generate_heat_map,
    render_heat_map_for_brief,
    assess_bill_likelihood,
    assess_bill_impact,
    assess_hearing_likelihood,
    assess_hearing_impact,
    assess_generic_likelihood,
    assess_generic_impact,
    calculate_urgency_days,
)
from src.signals.impact.models import HeatMapQuadrant


class TestLikelihoodAssessment:
    """Test likelihood scoring functions."""

    def test_bill_likelihood_introduced(self):
        """Test likelihood for newly introduced bill."""
        bill = {
            "latest_action_text": "Introduced in House",
            "cosponsors_count": 5,
        }
        likelihood = assess_bill_likelihood(bill)
        assert likelihood == 1

    def test_bill_likelihood_committee(self):
        """Test likelihood for bill in committee."""
        bill = {
            "latest_action_text": "Reported by Committee on Veterans' Affairs",
            "cosponsors_count": 20,
        }
        likelihood = assess_bill_likelihood(bill)
        assert likelihood >= 4

    def test_bill_likelihood_passed(self):
        """Test likelihood for passed bill."""
        bill = {
            "latest_action_text": "Passed House",
            "cosponsors_count": 100,
        }
        likelihood = assess_bill_likelihood(bill)
        assert likelihood == 5

    def test_bill_likelihood_bipartisan_boost(self):
        """Test likelihood boost for high cosponsor count."""
        bill_low = {
            "latest_action_text": "Referred to committee",
            "cosponsors_count": 5,
        }
        bill_high = {
            "latest_action_text": "Referred to committee",
            "cosponsors_count": 60,
        }
        likelihood_low = assess_bill_likelihood(bill_low)
        likelihood_high = assess_bill_likelihood(bill_high)
        assert likelihood_high > likelihood_low

    def test_hearing_likelihood_oversight(self):
        """Test likelihood for oversight hearing."""
        hearing = {
            "title": "Examining VA Claims Processing Backlogs",
            "committee_code": "HVAC",
        }
        likelihood = assess_hearing_likelihood(hearing)
        assert likelihood >= 3

    def test_hearing_likelihood_appropriations(self):
        """Test likelihood for appropriations hearing."""
        hearing = {
            "title": "FY2027 VA Appropriations",
            "committee_code": "HVAC",
        }
        likelihood = assess_hearing_likelihood(hearing)
        assert likelihood >= 4


class TestImpactAssessment:
    """Test impact scoring functions."""

    def test_bill_impact_reform(self):
        """Test impact for reform legislation."""
        bill = {
            "title": "Comprehensive Veterans Benefits Reform Act",
            "policy_area": "Veterans Affairs",
        }
        impact = assess_bill_impact(bill)
        assert impact == 5

    def test_bill_impact_study(self):
        """Test impact for study/report bill."""
        bill = {
            "title": "VA Claims Processing Study Act",
            "policy_area": "Veterans Affairs",
        }
        impact = assess_bill_impact(bill)
        assert impact <= 3

    def test_hearing_impact_investigation(self):
        """Test impact for investigation hearing."""
        hearing = {
            "title": "Investigation into VA Claims Accuracy",
        }
        impact = assess_hearing_impact(hearing)
        assert impact >= 4

    def test_hearing_impact_budget(self):
        """Test impact for budget hearing."""
        hearing = {
            "title": "FY2027 VA Budget Review",
        }
        impact = assess_hearing_impact(hearing)
        assert impact == 5

    def test_generic_impact_workflows(self):
        """Test generic impact with multiple workflows."""
        context = {
            "reputational_risk": "medium",
            "affected_workflows": ["claims_intake", "rating", "appeals", "bva"],
        }
        impact = assess_generic_impact(context)
        assert impact >= 3


class TestUrgencyCalculation:
    """Test urgency/days calculation."""

    def test_urgency_with_effective_date(self):
        """Test urgency calculation with effective date."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
        context = {
            "effective_date": future_date,
        }
        urgency = calculate_urgency_days(context)
        assert 28 <= urgency <= 32  # Allow some variance

    def test_urgency_with_hearing_date(self):
        """Test urgency calculation with hearing date."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        context = {
            "hearing_date": future_date,
        }
        urgency = calculate_urgency_days(context)
        assert 5 <= urgency <= 9

    def test_urgency_default_bill(self):
        """Test default urgency for bill."""
        context = {"source_type": "bill"}
        urgency = calculate_urgency_days(context)
        assert urgency == 90

    def test_urgency_default_hearing(self):
        """Test default urgency for hearing."""
        context = {"source_type": "hearing"}
        urgency = calculate_urgency_days(context)
        assert urgency == 14


class TestHeatMapGenerator:
    """Test HeatMapGenerator class."""

    @pytest.fixture
    def generator(self):
        return HeatMapGenerator()

    def test_generate_from_bills(self, generator):
        """Test heat map generation from bills."""
        bills = [
            {
                "bill_id": "hr-100",
                "title": "Veterans Benefits Reform Act",
                "latest_action_text": "Reported by committee",
                "cosponsors_count": 30,
            },
            {
                "bill_id": "hr-101",
                "title": "VA Study Act",
                "latest_action_text": "Introduced",
                "cosponsors_count": 5,
            },
        ]

        heat_map = generator.generate_from_bills(bills)

        assert heat_map.heat_map_id.startswith("HMAP-")
        assert len(heat_map.issues) == 2

    def test_generate_from_hearings(self, generator):
        """Test heat map generation from hearings."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
        hearings = [
            {
                "event_id": "hvac-001",
                "title": "Examining VA Claims Backlog",
                "committee_code": "HVAC",
                "hearing_date": future_date,
            },
        ]

        heat_map = generator.generate_from_hearings(hearings)

        assert len(heat_map.issues) == 1
        assert heat_map.issues[0].issue_id == "HEARING-hvac-001"

    def test_generate_combined(self, generator):
        """Test combined heat map from multiple sources."""
        bills = [
            {
                "bill_id": "hr-200",
                "title": "Test Bill",
                "latest_action_text": "Introduced",
                "cosponsors_count": 1,
            },
        ]
        hearings = [
            {
                "event_id": "svac-001",
                "title": "Test Hearing",
                "committee_code": "SVAC",
            },
        ]

        heat_map = generator.generate_combined(bills=bills, hearings=hearings)

        assert len(heat_map.issues) == 2

    def test_issue_scoring(self, generator):
        """Test that issues are properly scored."""
        bills = [
            {
                "bill_id": "hr-300",
                "title": "Comprehensive Reform",
                "latest_action_text": "Passed House",
                "cosponsors_count": 100,
            },
        ]

        heat_map = generator.generate_from_bills(bills)
        issue = heat_map.issues[0]

        assert issue.likelihood == 5  # Passed = max likelihood
        assert issue.impact == 5      # Reform = max impact
        assert issue.score > 0        # Score should be calculated
        assert issue.quadrant == HeatMapQuadrant.HIGH_PRIORITY

    def test_quadrant_assignment(self, generator):
        """Test quadrant assignment based on likelihood and impact."""
        bills = [
            # High likelihood, high impact -> HIGH_PRIORITY
            {
                "bill_id": "hr-hp",
                "title": "Major Reform Bill",
                "latest_action_text": "Passed House",
                "cosponsors_count": 100,
            },
            # Low likelihood, low impact -> LOW
            {
                "bill_id": "hr-low",
                "title": "Minor Study",
                "latest_action_text": "Introduced",
                "cosponsors_count": 1,
            },
        ]

        heat_map = generator.generate_from_bills(bills)

        high_priority = [i for i in heat_map.issues if i.quadrant == HeatMapQuadrant.HIGH_PRIORITY]
        low = [i for i in heat_map.issues if i.quadrant == HeatMapQuadrant.LOW]

        assert len(high_priority) >= 1
        assert len(low) >= 1


class TestHeatMapOutput:
    """Test heat map output rendering."""

    def test_render_for_brief(self):
        """Test heat map rendering for CEO Brief."""
        bills = [
            {
                "bill_id": "hr-400",
                "title": "Veterans Benefits Enhancement Act",
                "latest_action_text": "Reported by committee",
                "cosponsors_count": 50,
            },
            {
                "bill_id": "hr-401",
                "title": "VA Claims Study",
                "latest_action_text": "Introduced",
                "cosponsors_count": 3,
            },
        ]

        heat_map = generate_heat_map(bills=bills)
        output = render_heat_map_for_brief(heat_map)

        assert "RISK HEAT MAP" in output
        assert "Generated:" in output
        assert "Total Issues Tracked:" in output

    def test_ascii_render(self):
        """Test ASCII visualization output."""
        bills = [
            {
                "bill_id": "hr-500",
                "title": "Test Bill for ASCII",
                "latest_action_text": "Passed",
                "cosponsors_count": 50,
            },
        ]

        heat_map = generate_heat_map(bills=bills)
        ascii_output = heat_map.render_ascii()

        assert "HIGH IMPACT" in ascii_output
        assert "HIGH PRIORITY" in ascii_output
        assert "HEAT MAP" in ascii_output


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_generate_heat_map_no_save(self):
        """Test generate_heat_map without saving."""
        bills = [
            {
                "bill_id": "hr-600",
                "title": "Test Bill",
                "latest_action_text": "Introduced",
                "cosponsors_count": 1,
            },
        ]

        heat_map = generate_heat_map(bills=bills, save=False)

        assert heat_map is not None
        assert len(heat_map.issues) == 1

    def test_generate_heat_map_empty_sources(self):
        """Test generate_heat_map with no sources."""
        heat_map = generate_heat_map()

        assert heat_map is not None
        assert len(heat_map.issues) == 0
