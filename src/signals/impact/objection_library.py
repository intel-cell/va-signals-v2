"""Objection Library.

CHARLIE COMMAND - Phase 4: Build structured objection/response database.

Seed with top 10 predictable pushbacks per issue area:
- Benefits (claims processing, rating, appeals)
- Accreditation (38 CFR Part 14, OGC, fees)
- Appropriations (MilCon-VA, budget)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import (
    Objection,
    IssueArea,
    SourceType,
)
from .db import (
    insert_objection,
    get_objection,
    get_objections,
    search_objections,
    update_objection_usage,
    get_objection_stats,
)


# =============================================================================
# SEED DATA: BENEFITS OBJECTIONS
# =============================================================================

BENEFITS_OBJECTIONS = [
    {
        "objection_id": "OBJ-BEN-001",
        "objection_text": "This will significantly increase the claims backlog.",
        "response_text": "Analysis shows 90% of affected claims are already delayed. This expedites resolution for the majority while requiring additional processing for edge cases. Net effect is reduced total wait time.",
        "source_type": SourceType.STAFF,
        "tags": ["backlog", "processing_time"],
    },
    {
        "objection_id": "OBJ-BEN-002",
        "objection_text": "We don't have the staff to handle this additional workload.",
        "response_text": "The FY26 appropriation includes $X million for VBA hiring. Additionally, automation of initial review reduces per-claim processing time by 15%, offsetting the volume increase.",
        "source_type": SourceType.VA_INTERNAL,
        "tags": ["staffing", "workload"],
    },
    {
        "objection_id": "OBJ-BEN-003",
        "objection_text": "VSOs are opposed to this change.",
        "response_text": "We've consulted with DAV, VFW, and American Legion. While they have concerns about implementation timeline, they support the policy goal of faster decisions. We're addressing their concerns through the proposed transition period.",
        "source_type": SourceType.VSO,
        "tags": ["vso_relations", "stakeholder"],
    },
    {
        "objection_id": "OBJ-BEN-004",
        "objection_text": "This creates inconsistency with existing rating criteria.",
        "response_text": "The VASRD update process is ongoing. This change aligns with the 2024 musculoskeletal updates and anticipates the neurological revisions expected in Q3. M21-1 guidance will be issued concurrently.",
        "source_type": SourceType.STAFF,
        "tags": ["vasrd", "consistency"],
    },
    {
        "objection_id": "OBJ-BEN-005",
        "objection_text": "Veterans will be confused by the new process.",
        "response_text": "We're partnering with VA.gov to update the online experience and create plain-language guides. VSO service officers will receive training before implementation. Outreach campaign launches 60 days prior.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["communication", "veteran_experience"],
    },
    {
        "objection_id": "OBJ-BEN-006",
        "objection_text": "This will increase appeals volume.",
        "response_text": "Early data from pilot regions shows appeal rates actually decreased 12% due to clearer decision rationales. The new DBQ format explicitly addresses common appeal triggers.",
        "source_type": SourceType.STAFF,
        "tags": ["appeals", "quality"],
    },
    {
        "objection_id": "OBJ-BEN-007",
        "objection_text": "The IT systems can't support this change.",
        "response_text": "VBMS enhancement was deployed in January. The new functionality is already in production for Supplemental Claims and will extend to this use case via configuration change, not code deployment.",
        "source_type": SourceType.VA_INTERNAL,
        "tags": ["it_systems", "vbms"],
    },
    {
        "objection_id": "OBJ-BEN-008",
        "objection_text": "This will cost more than projected.",
        "response_text": "CBO scoring validates our estimates within 5%. The mandatory spending is offset by processing efficiency gains. Year-over-year cost growth is below the 3% baseline assumption.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["cost", "budget"],
    },
    {
        "objection_id": "OBJ-BEN-009",
        "objection_text": "C&P exam contractors can't handle the increased volume.",
        "response_text": "Contract modifications for VES and QTC were executed in December, adding 15% capacity. New provider networks in underserved areas reduce geographic bottlenecks. Wait times have decreased 8 days since October.",
        "source_type": SourceType.INDUSTRY,
        "tags": ["exams", "contractors"],
    },
    {
        "objection_id": "OBJ-BEN-010",
        "objection_text": "This benefits some veterans at the expense of others.",
        "response_text": "The prioritization framework ensures no veteran waits longer than current averages. High-complexity cases receive dedicated resources. The net effect is improved outcomes across all cohorts, with special populations seeing the largest gains.",
        "source_type": SourceType.VSO,
        "tags": ["equity", "prioritization"],
    },
]


# =============================================================================
# SEED DATA: ACCREDITATION OBJECTIONS
# =============================================================================

ACCREDITATION_OBJECTIONS = [
    {
        "objection_id": "OBJ-ACC-001",
        "objection_text": "This regulation is too burdensome for small practitioners.",
        "response_text": "The rule includes a small entity exemption for practitioners with fewer than 50 clients annually. Larger practices have 18 months to comply, with technical assistance available from OGC.",
        "source_type": SourceType.INDUSTRY,
        "tags": ["burden", "small_business"],
    },
    {
        "objection_id": "OBJ-ACC-002",
        "objection_text": "OGC doesn't have the resources to enforce this.",
        "response_text": "The FY26 budget includes $2.4M for OGC accreditation oversight. Additionally, the new complaint portal automates triage, allowing staff to focus on substantive reviews.",
        "source_type": SourceType.VA_INTERNAL,
        "tags": ["enforcement", "ogc"],
    },
    {
        "objection_id": "OBJ-ACC-003",
        "objection_text": "This will reduce access to representation for veterans.",
        "response_text": "Data shows 85% of accredited representatives are in good standing and unaffected. The change targets the 3% with substantiated complaints while improving quality for all veterans seeking assistance.",
        "source_type": SourceType.VSO,
        "tags": ["access", "representation"],
    },
    {
        "objection_id": "OBJ-ACC-004",
        "objection_text": "The fee restrictions are unfair to attorneys.",
        "response_text": "The 20% contingency cap aligns with SSA disability practice standards. Attorneys retain ability to petition for higher fees in complex cases. Historical data shows 95% of cases fall within the cap.",
        "source_type": SourceType.INDUSTRY,
        "tags": ["fees", "attorneys"],
    },
    {
        "objection_id": "OBJ-ACC-005",
        "objection_text": "VSOs should be exempt from these requirements.",
        "response_text": "The rule already distinguishes between fee-charging representatives and free VSO assistance. VSO-specific provisions focus on training verification, not fee restrictions.",
        "source_type": SourceType.VSO,
        "tags": ["vso", "exemption"],
    },
    {
        "objection_id": "OBJ-ACC-006",
        "objection_text": "The complaint process lacks due process protections.",
        "response_text": "Accused representatives receive written notice, 60 days to respond, and right to hearing before an ALJ. The appeals process mirrors federal employee disciplinary procedures.",
        "source_type": SourceType.INDUSTRY,
        "tags": ["due_process", "complaints"],
    },
    {
        "objection_id": "OBJ-ACC-007",
        "objection_text": "This creates barriers to entering the profession.",
        "response_text": "Entry requirements (law degree or VSO certification plus exam) remain unchanged. The rule addresses conduct after accreditation, not initial qualifications.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["entry_barriers", "qualifications"],
    },
    {
        "objection_id": "OBJ-ACC-008",
        "objection_text": "The database won't be accurate or up-to-date.",
        "response_text": "OGC implemented real-time sync with state bar databases in January. Representatives can verify and update their information through eBenefits. Quarterly audits ensure accuracy.",
        "source_type": SourceType.STAFF,
        "tags": ["database", "accuracy"],
    },
    {
        "objection_id": "OBJ-ACC-009",
        "objection_text": "This will drive representation underground.",
        "response_text": "Unauthorized practice penalties were strengthened in the 2023 PACT Act. VA OIG has dedicated resources for enforcement. Public awareness campaign educates veterans on recognizing accredited representatives.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["unauthorized_practice", "enforcement"],
    },
    {
        "objection_id": "OBJ-ACC-010",
        "objection_text": "The continuing education requirements are excessive.",
        "response_text": "The 8-hour annual requirement aligns with state bar minimums and can be satisfied through free VA-provided webinars. Topic flexibility allows practitioners to focus on their practice areas.",
        "source_type": SourceType.INDUSTRY,
        "tags": ["cle", "education"],
    },
]


# =============================================================================
# SEED DATA: APPROPRIATIONS OBJECTIONS
# =============================================================================

APPROPRIATIONS_OBJECTIONS = [
    {
        "objection_id": "OBJ-APP-001",
        "objection_text": "This exceeds the discretionary spending caps.",
        "response_text": "VA mandatory spending (benefits) is exempt from caps. The discretionary request is 2.3% above the cap but qualifies for the veterans' medical care exemption under the Fiscal Responsibility Act.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["caps", "discretionary"],
    },
    {
        "objection_id": "OBJ-APP-002",
        "objection_text": "We can't support this in the current fiscal environment.",
        "response_text": "Veteran healthcare and benefits have historically received bipartisan support regardless of fiscal constraints. The FY25 MilCon-VA passed 93-0 in the Senate.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["bipartisan", "fiscal"],
    },
    {
        "objection_id": "OBJ-APP-003",
        "objection_text": "VA hasn't spent prior year appropriations efficiently.",
        "response_text": "Obligation rates improved to 97% in FY25, up from 91% in FY23. The PACT Act surge is complete; FY26 spending projections are based on normalized workload.",
        "source_type": SourceType.STAFF,
        "tags": ["execution", "obligation"],
    },
    {
        "objection_id": "OBJ-APP-004",
        "objection_text": "This account has already received emergency supplemental funding.",
        "response_text": "The FY25 supplemental addressed one-time PACT Act implementation costs. The FY26 request funds sustained operations at the new baseline, not additional emergency needs.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["supplemental", "emergency"],
    },
    {
        "objection_id": "OBJ-APP-005",
        "objection_text": "The construction project cost estimates are unreliable.",
        "response_text": "VA implemented GAO-recommended cost estimation reforms in 2024. The FY26 SCIP projects use parametric modeling validated against completed facilities. Average variance is now 8%, down from 23%.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["construction", "cost_estimates"],
    },
    {
        "objection_id": "OBJ-APP-006",
        "objection_text": "Community care is diverting funds from VA medical centers.",
        "response_text": "The MISSION Act established the Community Care account as separate from VHA Medical Services. The FY26 request maintains both at adequate levels. Community care spending is stabilizing after initial MISSION Act growth.",
        "source_type": SourceType.VSO,
        "tags": ["community_care", "mission_act"],
    },
    {
        "objection_id": "OBJ-APP-007",
        "objection_text": "IT modernization projects are over budget.",
        "response_text": "EHR modernization costs are tracked separately per congressional direction. The general IT account is on track, with cloud migration generating $45M in annual savings beginning FY26.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["it", "modernization"],
    },
    {
        "objection_id": "OBJ-APP-008",
        "objection_text": "Hiring hasn't kept pace with appropriated levels.",
        "response_text": "VBA filled 4,200 positions in FY25, exceeding target by 8%. VHA vacancy rates in critical specialties are down 12 points. The FY26 hiring plan is executable with current HR capacity.",
        "source_type": SourceType.STAFF,
        "tags": ["hiring", "vacancies"],
    },
    {
        "objection_id": "OBJ-APP-009",
        "objection_text": "This includes new programs not yet authorized.",
        "response_text": "Advance appropriation authority allows funding for programs with pending authorization. The requested programs align with committee-reported legislation expected to pass before FY26.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["authorization", "advance_appropriation"],
    },
    {
        "objection_id": "OBJ-APP-010",
        "objection_text": "The request doesn't account for potential rescissions.",
        "response_text": "Historical rescission rates for VA accounts average 0.3%, lowest among cabinet departments. The request includes 2% management reserve to absorb potential reductions.",
        "source_type": SourceType.CONGRESSIONAL,
        "tags": ["rescissions", "reserves"],
    },
]


# =============================================================================
# OBJECTION LIBRARY CLASS
# =============================================================================

class ObjectionLibrary:
    """Manages the structured objection/response database."""

    def __init__(self):
        self._seed_data_loaded = False

    def seed_database(self, force: bool = False) -> int:
        """Seed the objection database with initial entries.

        Args:
            force: If True, re-seeds even if data exists

        Returns:
            Number of objections inserted
        """
        if self._seed_data_loaded and not force:
            return 0

        stats = get_objection_stats()
        if stats["total"] >= 30 and not force:
            self._seed_data_loaded = True
            return 0

        count = 0

        # Benefits objections
        for obj_data in BENEFITS_OBJECTIONS:
            obj = Objection(
                objection_id=obj_data["objection_id"],
                issue_area=IssueArea.BENEFITS,
                source_type=obj_data["source_type"],
                objection_text=obj_data["objection_text"],
                response_text=obj_data["response_text"],
                supporting_evidence=[],
                tags=obj_data.get("tags", []),
            )
            try:
                insert_objection(obj.to_dict())
                count += 1
            except Exception:
                pass  # Already exists

        # Accreditation objections
        for obj_data in ACCREDITATION_OBJECTIONS:
            obj = Objection(
                objection_id=obj_data["objection_id"],
                issue_area=IssueArea.ACCREDITATION,
                source_type=obj_data["source_type"],
                objection_text=obj_data["objection_text"],
                response_text=obj_data["response_text"],
                supporting_evidence=[],
                tags=obj_data.get("tags", []),
            )
            try:
                insert_objection(obj.to_dict())
                count += 1
            except Exception:
                pass

        # Appropriations objections
        for obj_data in APPROPRIATIONS_OBJECTIONS:
            obj = Objection(
                objection_id=obj_data["objection_id"],
                issue_area=IssueArea.APPROPRIATIONS,
                source_type=obj_data["source_type"],
                objection_text=obj_data["objection_text"],
                response_text=obj_data["response_text"],
                supporting_evidence=[],
                tags=obj_data.get("tags", []),
            )
            try:
                insert_objection(obj.to_dict())
                count += 1
            except Exception:
                pass

        self._seed_data_loaded = True
        return count

    def find_response(
        self,
        objection_text: str,
        issue_area: Optional[IssueArea] = None,
    ) -> Optional[dict]:
        """Find the best matching response for an objection.

        Args:
            objection_text: The objection to respond to
            issue_area: Optional filter by issue area

        Returns:
            Best matching objection record or None
        """
        # Search by text similarity
        results = search_objections(objection_text, limit=5)

        if issue_area:
            results = [r for r in results if r["issue_area"] == issue_area.value]

        if results:
            return results[0]
        return None

    def get_by_area(self, issue_area: IssueArea, limit: int = 10) -> list[dict]:
        """Get objections by issue area."""
        return get_objections(issue_area=issue_area.value, limit=limit)

    def get_by_source(self, source_type: SourceType, limit: int = 10) -> list[dict]:
        """Get objections by source type."""
        return get_objections(source_type=source_type.value, limit=limit)

    def record_usage(
        self,
        objection_id: str,
        effectiveness: Optional[int] = None,
    ) -> None:
        """Record that an objection response was used.

        Args:
            objection_id: The objection that was used
            effectiveness: Optional effectiveness rating (1-5)
        """
        update_objection_usage(objection_id, effectiveness)

    def add_objection(
        self,
        issue_area: IssueArea,
        source_type: SourceType,
        objection_text: str,
        response_text: str,
        supporting_evidence: list[str] = None,
        tags: list[str] = None,
    ) -> str:
        """Add a new objection to the library.

        Returns:
            objection_id of the new entry
        """
        # Generate ID based on issue area
        area_prefix = {
            IssueArea.BENEFITS: "BEN",
            IssueArea.ACCREDITATION: "ACC",
            IssueArea.APPROPRIATIONS: "APP",
            IssueArea.OVERSIGHT: "OVR",
            IssueArea.IT_MODERNIZATION: "ITM",
            IssueArea.CLAIMS_PROCESSING: "CLP",
        }
        prefix = area_prefix.get(issue_area, "GEN")
        objection_id = f"OBJ-{prefix}-{uuid.uuid4().hex[:6].upper()}"

        obj = Objection(
            objection_id=objection_id,
            issue_area=issue_area,
            source_type=source_type,
            objection_text=objection_text,
            response_text=response_text,
            supporting_evidence=supporting_evidence or [],
            tags=tags or [],
        )

        insert_objection(obj.to_dict())
        return objection_id

    def get_stats(self) -> dict:
        """Get library statistics."""
        return get_objection_stats()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def seed_objection_library(force: bool = False) -> int:
    """Seed the objection library with initial entries."""
    library = ObjectionLibrary()
    return library.seed_database(force=force)


def find_objection_response(
    objection_text: str,
    issue_area: Optional[IssueArea] = None,
) -> Optional[dict]:
    """Find the best matching response for an objection."""
    library = ObjectionLibrary()
    return library.find_response(objection_text, issue_area)


def get_objections_for_area(issue_area: IssueArea, limit: int = 10) -> list[dict]:
    """Get objections for a specific issue area."""
    library = ObjectionLibrary()
    return library.get_by_area(issue_area, limit)


def render_objection_for_brief(objection: dict) -> str:
    """Render an objection for inclusion in CEO Brief."""
    return f"""**Objection:** "{objection['objection_text']}"

**Response:** {objection['response_text']}

_Source: {objection['source_type'].upper()} | Area: {objection['issue_area'].upper()}_
"""
