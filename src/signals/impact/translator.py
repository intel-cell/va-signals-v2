"""Policy-to-Operations Translator.

CHARLIE COMMAND - Phase 2: Translate policy changes into operational impact.

Domain Knowledge Required (per ORDER_CHARLIE_001):
- VBA claims/appeals workflow
- M21-1 manual structure
- Accreditation framework
- Appropriations account structure (MilCon-VA)
"""

from dataclasses import dataclass

from ..envelope import Envelope
from .models import (
    ConfidenceLevel,
    ImpactMemo,
    Posture,
    RiskLevel,
    create_impact_memo,
)

# =============================================================================
# DOMAIN KNOWLEDGE: VBA OPERATIONAL WORKFLOWS
# =============================================================================

# Claims processing workflow stages
VBA_WORKFLOWS = {
    "claims_intake": {
        "name": "Claims Intake",
        "description": "Initial receipt and establishment of claim",
        "metrics": ["volume", "processing_time"],
        "systems": ["VBMS", "eBenefits", "VA.gov"],
    },
    "claims_development": {
        "name": "Claims Development",
        "description": "Evidence gathering and medical record requests",
        "metrics": ["cycle_time", "evidence_requests"],
        "systems": ["VBMS", "CAPRI", "VistA"],
    },
    "rating": {
        "name": "Rating",
        "description": "Disability evaluation using VASRD criteria",
        "metrics": ["accuracy", "cycle_time", "rework_rate"],
        "systems": ["VBMS", "RBA2000"],
    },
    "notification": {
        "name": "Notification",
        "description": "Decision letter generation and delivery",
        "metrics": ["delivery_time", "appeal_rate"],
        "systems": ["VBMS", "Letters Generator"],
    },
    "appeals": {
        "name": "Appeals & Higher Level Review",
        "description": "AMA lanes: supplemental, HLR, BVA",
        "metrics": ["pending_inventory", "average_days"],
        "systems": ["Caseflow", "VACOLS"],
    },
    "bva": {
        "name": "Board of Veterans' Appeals",
        "description": "Final administrative appeal",
        "metrics": ["pending_appeals", "decision_time"],
        "systems": ["Caseflow"],
    },
    "exam_scheduling": {
        "name": "Exam Scheduling",
        "description": "C&P examination coordination",
        "metrics": ["wait_time", "no_show_rate", "contractor_capacity"],
        "systems": ["VBMS", "VES", "QTC"],
    },
    "medical_evidence": {
        "name": "Medical Evidence Development",
        "description": "Private/VA medical records integration",
        "metrics": ["acquisition_time", "completeness"],
        "systems": ["VBMS", "VistA", "Health API"],
    },
    "accreditation": {
        "name": "Accreditation",
        "description": "Agent/attorney/VSO accreditation (38 CFR Part 14)",
        "metrics": ["active_agents", "complaints", "fee_agreements"],
        "systems": ["OGC Database", "eBenefits"],
    },
    "fee_agreements": {
        "name": "Fee Agreements",
        "description": "Attorney/agent fee review",
        "metrics": ["agreements_filed", "disputes"],
        "systems": ["OGC Database"],
    },
    "it_systems": {
        "name": "IT Systems/Modernization",
        "description": "VBA technology infrastructure",
        "metrics": ["system_uptime", "legacy_dependency"],
        "systems": ["VBMS", "Caseflow", "VA.gov"],
    },
    "training": {
        "name": "Training",
        "description": "Employee training and certification",
        "metrics": ["training_hours", "certification_rate"],
        "systems": ["TMS", "KnowVA"],
    },
    "contracting": {
        "name": "Contracting",
        "description": "VBA contracted services (exams, IT)",
        "metrics": ["contract_performance", "spending"],
        "systems": ["FPDS", "SAM.gov"],
    },
    "staffing": {
        "name": "Staffing",
        "description": "VBA workforce",
        "metrics": ["fte_count", "vacancy_rate", "overtime"],
        "systems": ["HR systems"],
    },
}


# =============================================================================
# DOMAIN KNOWLEDGE: POLICY-TO-WORKFLOW MAPPINGS
# =============================================================================

# Keywords that map to operational workflows
POLICY_WORKFLOW_MAPPINGS = {
    # Claims processing keywords
    "claims_intake": [
        "fully developed claim",
        "fdc",
        "intent to file",
        "itf",
        "claim submission",
        "application form",
        "va form 21",
        "ebenefits",
        "va.gov",
    ],
    "claims_development": [
        "duty to assist",
        "evidence",
        "medical records",
        "service treatment",
        "private medical",
        "development",
        "nexus",
        "buddy statement",
    ],
    "rating": [
        "rating",
        "disability evaluation",
        "vasrd",
        "schedule for rating",
        "percentage",
        "combined rating",
        "bilateral factor",
        "rating decision",
        "deferred rating",
    ],
    "notification": [
        "decision letter",
        "notification",
        "appeal rights",
        "effective date",
        "retroactive",
    ],
    "appeals": [
        "appeal",
        "higher level review",
        "hlr",
        "supplemental claim",
        "ama",
        "appeals modernization",
        "legacy appeal",
        "notice of disagreement",
        "nod",
    ],
    "bva": [
        "board of veterans",
        "bva",
        "board hearing",
        "virtual hearing",
        "travel board",
        "video conference",
        "bvain",
    ],
    "exam_scheduling": [
        "c&p exam",
        "compensation and pension",
        "examination",
        "medical opinion",
        "independent medical",
        "imo",
        "ves",
        "qtc",
        "lhi",
    ],
    "medical_evidence": [
        "medical evidence",
        "dbq",
        "disability benefits questionnaire",
        "medical nexus",
        "service connection",
        "secondary condition",
    ],
    "accreditation": [
        "accreditation",
        "accredited",
        "representative",
        "power of attorney",
        "poa",
        "38 cfr 14",
        "ogc",
        "agent",
        "claims agent",
    ],
    "fee_agreements": [
        "fee agreement",
        "attorney fee",
        "contingency fee",
        "direct pay",
        "fee dispute",
    ],
    "it_systems": [
        "vbms",
        "caseflow",
        "modernization",
        "digital",
        "automation",
        "artificial intelligence",
        "ai",
        "machine learning",
        "robotic process",
        "rpa",
    ],
    "training": [
        "training",
        "certification",
        "challenge exam",
        "knowva",
        "sme",
        "quality review",
    ],
    "contracting": [
        "contractor",
        "contract",
        "procurement",
        "rfp",
        "task order",
        "idiq",
        "contract modification",
    ],
    "staffing": [
        "staffing",
        "fte",
        "full time equivalent",
        "hiring",
        "vacancy",
        "regional office",
        "overtime",
    ],
}


# Policy vehicle keywords for status detection
STATUS_KEYWORDS = {
    "introduced": ["introduced", "referred to committee"],
    "committee_action": ["reported", "ordered to be reported", "markup"],
    "floor_action": ["passed", "agreed to", "motion to reconsider"],
    "proposed_rule": ["proposed rule", "nprm", "notice of proposed rulemaking"],
    "final_rule": ["final rule", "effective date"],
    "hearing_scheduled": ["hearing scheduled", "witness list"],
    "oversight": ["gao report", "oig report", "investigation", "audit"],
}


# Risk indicators
RISK_INDICATORS = {
    "high_compliance": [
        "mandatory",
        "shall",
        "must comply",
        "required",
        "enforcement",
        "penalty",
        "violation",
    ],
    "medium_compliance": [
        "should",
        "expected to",
        "encouraged",
        "guidance",
        "best practice",
    ],
    "reputational": [
        "investigation",
        "audit",
        "whistleblower",
        "media",
        "60 minutes",
        "news",
        "report",
        "vso",
        "dav",
        "vfw",
        "american legion",
    ],
}


# =============================================================================
# TRANSLATOR CLASS
# =============================================================================


@dataclass
class TranslationContext:
    """Context for policy translation."""

    source_type: str  # bill, rule, hearing, report, executive_order
    vehicle_id: str
    title: str
    body_text: str
    source_url: str
    published_at: str | None = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PolicyToOperationsTranslator:
    """Translates policy changes into operational impact assessments.

    Takes policy signals (bills, rules, hearings, reports) and generates
    CEO-grade impact memos by:
    1. Identifying affected operational workflows
    2. Assessing compliance and reputational risk
    3. Generating recommended actions and decision triggers
    """

    def __init__(self):
        self.workflow_mappings = POLICY_WORKFLOW_MAPPINGS
        self.workflows = VBA_WORKFLOWS
        self.risk_indicators = RISK_INDICATORS

    def translate_envelope(self, envelope: Envelope) -> ImpactMemo:
        """Translate a normalized envelope to an impact memo."""
        context = TranslationContext(
            source_type=self._determine_source_type(envelope.authority_type),
            vehicle_id=envelope.authority_id,
            title=envelope.title,
            body_text=envelope.body_text,
            source_url=envelope.source_url or "",
            published_at=envelope.published_at,
            metadata=envelope.metadata,
        )
        return self.translate(context)

    def translate(self, context: TranslationContext) -> ImpactMemo:
        """Translate policy context to an impact memo."""
        # Identify affected workflows
        affected_workflows = self._identify_workflows(context.title, context.body_text)
        if not affected_workflows:
            affected_workflows = ["claims_intake"]  # Default if none detected

        # Assess risks
        compliance_risk = self._assess_compliance_risk(context.body_text)
        reputational_risk = self._assess_reputational_risk(context.body_text)

        # Determine posture based on risk and source type
        posture = self._determine_posture(compliance_risk, reputational_risk, context.source_type)

        # Generate what it does summary
        what_it_does = self._generate_summary(context)

        # Generate operational impact description
        operational_impact = self._generate_operational_impact(
            affected_workflows, context.title, context.body_text
        )

        # Determine current status
        current_status = self._detect_status(context.source_type, context.body_text)

        # Generate recommended action and decision trigger
        recommended_action = self._generate_recommended_action(
            posture, compliance_risk, context.source_type
        )
        decision_trigger = self._generate_decision_trigger(context.source_type, current_status)

        # Assess confidence
        confidence = self._assess_confidence(context, affected_workflows)

        return create_impact_memo(
            issue_id=f"{context.source_type.upper()}-{context.vehicle_id}",
            vehicle=context.vehicle_id,
            vehicle_type=context.source_type,
            current_status=current_status,
            source_url=context.source_url,
            what_it_does=what_it_does,
            operational_impact=operational_impact,
            affected_workflows=affected_workflows,
            compliance_exposure=compliance_risk,
            reputational_risk=reputational_risk,
            posture=posture,
            recommended_action=recommended_action,
            decision_trigger=decision_trigger,
            confidence=confidence,
            sources=[context.source_url] if context.source_url else [],
            section_reference=context.metadata.get("section_reference"),
            effective_date=context.metadata.get("effective_date"),
            affected_veteran_count=self._estimate_affected_veterans(affected_workflows),
        )

    def _determine_source_type(self, authority_type: str) -> str:
        """Map authority_type to source type."""
        mapping = {
            "bill_text": "bill",
            "rule": "rule",
            "proposed_rule": "rule",
            "final_rule": "rule",
            "hearing_notice": "hearing",
            "report": "report",
            "press_release": "report",
            "executive_order": "executive_order",
            "memorandum": "guidance",
            "directive": "guidance",
        }
        return mapping.get(authority_type, "report")

    def _identify_workflows(self, title: str, body_text: str) -> list[str]:
        """Identify affected VBA workflows from policy text."""
        combined = f"{title} {body_text}".lower()
        affected = []

        for workflow, keywords in self.workflow_mappings.items():
            for keyword in keywords:
                if keyword in combined:
                    if workflow not in affected:
                        affected.append(workflow)
                    break

        return affected

    def _assess_compliance_risk(self, text: str) -> RiskLevel:
        """Assess compliance risk level from policy text."""
        text_lower = text.lower()

        high_count = sum(1 for kw in self.risk_indicators["high_compliance"] if kw in text_lower)
        medium_count = sum(
            1 for kw in self.risk_indicators["medium_compliance"] if kw in text_lower
        )

        if high_count >= 3:
            return RiskLevel.CRITICAL
        elif high_count >= 2:
            return RiskLevel.HIGH
        elif high_count >= 1 or medium_count >= 2:
            return RiskLevel.MEDIUM
        elif medium_count >= 1:
            return RiskLevel.LOW
        return RiskLevel.NEGLIGIBLE

    def _assess_reputational_risk(self, text: str) -> RiskLevel:
        """Assess reputational risk level from policy text."""
        text_lower = text.lower()

        rep_count = sum(1 for kw in self.risk_indicators["reputational"] if kw in text_lower)

        if rep_count >= 4:
            return RiskLevel.CRITICAL
        elif rep_count >= 3:
            return RiskLevel.HIGH
        elif rep_count >= 2:
            return RiskLevel.MEDIUM
        elif rep_count >= 1:
            return RiskLevel.LOW
        return RiskLevel.NEGLIGIBLE

    def _determine_posture(
        self, compliance: RiskLevel, reputational: RiskLevel, source_type: str
    ) -> Posture:
        """Determine organizational posture based on risk assessment."""
        # High risk items need active engagement
        if compliance in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            return Posture.OPPOSE if source_type == "rule" else Posture.NEUTRAL_ENGAGED

        if reputational in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            return Posture.NEUTRAL_ENGAGED

        # Medium risk - monitor closely
        if compliance == RiskLevel.MEDIUM or reputational == RiskLevel.MEDIUM:
            return Posture.MONITOR

        # Low risk - support if beneficial or monitor
        return Posture.MONITOR

    def _generate_summary(self, context: TranslationContext) -> str:
        """Generate plain language summary (what it does)."""
        title = context.title
        source_type = context.source_type

        summaries = {
            "bill": f"Proposed legislation: {title}. Would modify VA benefits or operations if enacted.",
            "rule": f"Regulatory change: {title}. Would establish binding requirements for VA operations.",
            "hearing": f"Congressional hearing: {title}. Signals oversight focus on this area.",
            "report": f"Oversight report: {title}. May recommend changes or highlight deficiencies.",
            "executive_order": f"Executive action: {title}. Directs VA to implement new priorities.",
            "guidance": f"VA guidance update: {title}. Clarifies policy interpretation or procedures.",
        }

        return summaries.get(source_type, f"Policy change: {title}")

    def _generate_operational_impact(self, workflows: list[str], title: str, body_text: str) -> str:
        """Generate operational impact description."""
        workflow_names = [self.workflows[w]["name"] for w in workflows if w in self.workflows]

        if not workflow_names:
            return "Potential impact on VA operations; specific workflows TBD."

        if len(workflow_names) == 1:
            return f"Primarily affects {workflow_names[0]}. May require process adjustments and staff training."

        return f"Cross-functional impact on: {', '.join(workflow_names)}. Coordination across multiple VBA divisions likely required."

    def _detect_status(self, source_type: str, body_text: str) -> str:
        """Detect current status from body text."""
        text_lower = body_text.lower()

        for status, keywords in STATUS_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return status

        # Default statuses by source type
        defaults = {
            "bill": "introduced",
            "rule": "proposed_rule",
            "hearing": "hearing_scheduled",
            "report": "published",
            "executive_order": "effective",
            "guidance": "issued",
        }
        return defaults.get(source_type, "pending")

    def _generate_recommended_action(
        self, posture: Posture, compliance: RiskLevel, source_type: str
    ) -> str:
        """Generate recommended action based on posture and risk."""
        if posture == Posture.OPPOSE:
            if source_type == "rule":
                return "Submit public comment opposing; prepare compliance contingency plan."
            return "Engage stakeholders to express concerns; coordinate with industry allies."

        if posture == Posture.NEUTRAL_ENGAGED:
            if compliance in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                return "Engage proactively with policymakers; prepare implementation scenarios."
            return "Track closely; prepare talking points for stakeholder inquiries."

        if posture == Posture.SUPPORT:
            return "Support publicly if asked; prepare implementation roadmap."

        # Monitor posture
        return "Track progress; no immediate action required but maintain awareness."

    def _generate_decision_trigger(self, source_type: str, current_status: str) -> str:
        """Generate decision trigger (if X appears, do Y)."""
        triggers = {
            (
                "bill",
                "introduced",
            ): "If bill advances to committee markup, escalate to leadership for engagement decision.",
            (
                "bill",
                "committee_action",
            ): "If bill passes committee, prepare floor strategy and stakeholder outreach.",
            ("bill", "floor_action"): "If bill passes chamber, prepare implementation planning.",
            (
                "rule",
                "proposed_rule",
            ): "If comment period closes, analyze final rule probability; prepare compliance plan.",
            (
                "rule",
                "final_rule",
            ): "If effective date within 90 days, accelerate implementation planning.",
            (
                "hearing",
                "hearing_scheduled",
            ): "If additional hearings scheduled, prepare testimony and talking points.",
            (
                "report",
                "published",
            ): "If follow-up hearings announced, prepare response to findings.",
        }

        key = (source_type, current_status)
        return triggers.get(key, "If status changes, reassess impact and update posture.")

    def _assess_confidence(
        self, context: TranslationContext, workflows: list[str]
    ) -> ConfidenceLevel:
        """Assess confidence in the impact assessment."""
        # More workflows identified = higher confidence we understand the impact
        if len(workflows) >= 3:
            confidence_base = ConfidenceLevel.HIGH
        elif len(workflows) >= 1:
            confidence_base = ConfidenceLevel.MEDIUM
        else:
            confidence_base = ConfidenceLevel.LOW

        # Longer body text = more information = higher confidence
        if len(context.body_text) > 1000:
            return confidence_base
        elif len(context.body_text) > 300:
            return confidence_base
        else:
            # Short text reduces confidence
            if confidence_base == ConfidenceLevel.HIGH:
                return ConfidenceLevel.MEDIUM
            return ConfidenceLevel.LOW

    def _estimate_affected_veterans(self, workflows: list[str]) -> str | None:
        """Estimate affected veteran count based on workflows."""
        # High-volume workflows
        high_volume = {"claims_intake", "claims_development", "rating", "notification"}
        medium_volume = {"appeals", "exam_scheduling", "medical_evidence"}

        high_count = sum(1 for w in workflows if w in high_volume)
        medium_count = sum(1 for w in workflows if w in medium_volume)

        if high_count >= 2:
            return "500K-2M annually"
        elif high_count >= 1:
            return "100K-500K annually"
        elif medium_count >= 2:
            return "50K-200K annually"
        elif medium_count >= 1:
            return "10K-100K annually"
        return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def translate_bill_to_impact(bill: dict) -> ImpactMemo:
    """Translate a bill record to an impact memo."""
    context = TranslationContext(
        source_type="bill",
        vehicle_id=bill.get("bill_id", ""),
        title=bill.get("title", ""),
        body_text=f"{bill.get('title', '')} {bill.get('latest_action_text', '')}",
        source_url=f"https://congress.gov/bill/{bill.get('congress', '')}/{bill.get('bill_type', '').lower()}/{bill.get('bill_number', '')}",
        published_at=bill.get("introduced_date"),
        metadata={
            "congress": bill.get("congress"),
            "bill_type": bill.get("bill_type"),
            "bill_number": bill.get("bill_number"),
        },
    )
    return PolicyToOperationsTranslator().translate(context)


def translate_hearing_to_impact(hearing: dict) -> ImpactMemo:
    """Translate a hearing record to an impact memo."""
    context = TranslationContext(
        source_type="hearing",
        vehicle_id=hearing.get("event_id", ""),
        title=hearing.get("title", ""),
        body_text=f"{hearing.get('title', '')} {hearing.get('committee_name', '')}",
        source_url=hearing.get("url", ""),
        published_at=hearing.get("hearing_date"),
        metadata={
            "committee_code": hearing.get("committee_code"),
            "committee_name": hearing.get("committee_name"),
        },
    )
    return PolicyToOperationsTranslator().translate(context)


def translate_fr_to_impact(fr_doc: dict) -> ImpactMemo:
    """Translate a Federal Register document to an impact memo."""
    # Combine FR summary info
    summary = fr_doc.get("summary", "")
    veteran_impact = fr_doc.get("veteran_impact", "")
    body_text = f"{summary}\n\n{veteran_impact}"

    context = TranslationContext(
        source_type="rule",
        vehicle_id=fr_doc.get("doc_id", ""),
        title=fr_doc.get("title", summary[:100] if summary else "FR Document"),
        body_text=body_text,
        source_url=fr_doc.get("source_url", ""),
        published_at=fr_doc.get("published_date"),
        metadata={
            "tags": fr_doc.get("tags", []),
        },
    )
    return PolicyToOperationsTranslator().translate(context)
