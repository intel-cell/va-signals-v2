"""Data models for Evidence Pack system.

These models define the structure for evidence packs, sources, excerpts, and claims.
All models enforce provenance-first design: no claim without dated, verifiable source.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class SourceType(str, Enum):
    """Types of authoritative sources."""

    FEDERAL_REGISTER = "federal_register"
    BILL = "bill"
    HEARING = "hearing"
    OIG_REPORT = "oig_report"
    GAO_REPORT = "gao_report"
    CRS_REPORT = "crs_report"
    VA_GUIDANCE = "va_guidance"
    AUTHORITY_DOC = "authority_doc"
    ECFR = "ecfr"
    NEWS = "news"


class ClaimType(str, Enum):
    """Classification of claim basis."""

    OBSERVED = "observed"  # Directly stated in source
    INFERRED = "inferred"  # Logically derived from source
    MODELED = "modeled"  # Computed/predicted, requires explanation


class Confidence(str, Enum):
    """Confidence level in claim."""

    HIGH = "high"  # Multiple corroborating sources or official statement
    MEDIUM = "medium"  # Single authoritative source
    LOW = "low"  # Indirect source or inference


class PackStatus(str, Enum):
    """Evidence pack workflow status."""

    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class EvidenceExcerpt:
    """A specific quoted passage from a source."""

    excerpt_text: str
    source_id: str
    section_reference: str | None = None  # e.g., "Section 3(a)(1)"
    page_or_line: str | None = None
    context_before: str | None = None
    context_after: str | None = None
    excerpt_id: int | None = None

    def to_citation_string(self) -> str:
        """Format as a citation reference."""
        parts = []
        if self.section_reference:
            parts.append(self.section_reference)
        if self.page_or_line:
            parts.append(f"p. {self.page_or_line}")
        location = ", ".join(parts) if parts else ""
        return (
            f'"{self.excerpt_text[:100]}..." ({location})'
            if len(self.excerpt_text) > 100
            else f'"{self.excerpt_text}" ({location})'
        )


@dataclass
class EvidenceSource:
    """An authoritative source document."""

    source_id: str
    source_type: SourceType
    title: str
    url: str
    date_accessed: str
    date_published: str | None = None
    date_effective: str | None = None
    document_hash: str | None = None
    version: int = 1

    # Source-type-specific identifiers
    fr_citation: str | None = None  # e.g., "89 FR 12345"
    fr_doc_number: str | None = None  # e.g., "2024-01234"
    bill_number: str | None = None  # e.g., "HR5"
    bill_congress: int | None = None  # e.g., 118
    report_number: str | None = None  # e.g., "GAO-24-123"

    # Metadata
    issuing_agency: str | None = None
    document_type: str | None = None
    metadata: dict = field(default_factory=dict)

    # Associated excerpts
    excerpts: list[EvidenceExcerpt] = field(default_factory=list)

    @classmethod
    def generate_source_id(cls, source_type: SourceType, identifier: str) -> str:
        """Generate a deterministic source ID."""
        raw = f"{source_type.value}:{identifier}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_citation_string(self) -> str:
        """Format as a human-readable citation."""
        parts = [self.title]

        if self.fr_citation:
            parts.append(self.fr_citation)
        elif self.bill_number and self.bill_congress:
            parts.append(f"{self.bill_number}, {self.bill_congress}th Congress")
        elif self.report_number:
            parts.append(self.report_number)

        if self.date_published:
            parts.append(f"({self.date_published})")

        parts.append(f"[{self.url}]")
        parts.append(f"(accessed {self.date_accessed})")

        return " ".join(parts)

    def to_markdown_citation(self, index: int) -> str:
        """Format as markdown footnote citation."""
        cite_id = self.fr_citation or self.report_number or self.bill_number or self.source_id[:8]
        return f"[^{index}]: {self.title}. {cite_id}. {self.date_published or 'n.d.'}. <{self.url}> (accessed {self.date_accessed})"


@dataclass
class EvidenceClaim:
    """A claim backed by evidence sources."""

    claim_text: str
    claim_type: ClaimType = ClaimType.OBSERVED
    confidence: Confidence = Confidence.HIGH
    source_ids: list[str] = field(default_factory=list)
    excerpt_ids: list[int] = field(default_factory=list)
    last_verified: str | None = None
    claim_id: int | None = None

    def is_valid(self) -> tuple[bool, list[str]]:
        """Check if claim has required supporting sources."""
        errors = []

        if not self.source_ids:
            errors.append("Claim has no supporting sources")

        if self.claim_type == ClaimType.OBSERVED and not self.source_ids:
            errors.append("Observed claim must cite at least one source")

        if self.claim_type == ClaimType.MODELED and not self.source_ids:
            errors.append("Modeled claim must explain methodology and cite basis")

        return (len(errors) == 0, errors)


@dataclass
class EvidencePack:
    """A complete evidence pack with claims and supporting sources."""

    pack_id: str
    title: str
    generated_at: str
    generated_by: str
    claims: list[EvidenceClaim] = field(default_factory=list)
    sources: dict[str, EvidenceSource] = field(default_factory=dict)
    issue_id: str | None = None
    summary: str | None = None
    status: PackStatus = PackStatus.DRAFT
    validation_errors: list[str] = field(default_factory=list)
    output_path: str | None = None

    @classmethod
    def generate_pack_id(cls, issue_id: str | None = None) -> str:
        """Generate a unique pack ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        if issue_id:
            return f"EP-{issue_id}-{timestamp}"
        return f"EP-{timestamp}"

    def add_source(self, source: EvidenceSource) -> None:
        """Add a source to the pack."""
        self.sources[source.source_id] = source

    def add_claim(self, claim: EvidenceClaim) -> None:
        """Add a claim to the pack."""
        self.claims.append(claim)

    def get_source(self, source_id: str) -> EvidenceSource | None:
        """Retrieve a source by ID."""
        return self.sources.get(source_id)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the entire evidence pack."""
        errors = []

        # Check each claim has sources
        for i, claim in enumerate(self.claims):
            is_valid, claim_errors = claim.is_valid()
            if not is_valid:
                for err in claim_errors:
                    errors.append(f"Claim {i + 1}: {err}")

            # Verify source IDs exist
            for source_id in claim.source_ids:
                if source_id not in self.sources:
                    errors.append(f"Claim {i + 1}: References unknown source {source_id}")

        # Check all sources have required fields
        for source_id, source in self.sources.items():
            if not source.date_accessed:
                errors.append(f"Source {source_id}: Missing access date")
            if not source.url:
                errors.append(f"Source {source_id}: Missing URL")

        self.validation_errors = errors
        is_valid = len(errors) == 0
        self.status = PackStatus.VALIDATED if is_valid else PackStatus.FAILED

        return (is_valid, errors)

    def to_markdown(self) -> str:
        """Generate markdown output for the evidence pack."""
        lines = []
        lines.append(f"# Evidence Pack: {self.title}")
        lines.append("")
        lines.append(f"**Pack ID:** {self.pack_id}")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append(f"**Status:** {self.status.value}")
        if self.issue_id:
            lines.append(f"**Issue ID:** {self.issue_id}")
        lines.append("")

        if self.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(self.summary)
            lines.append("")

        lines.append("## Claims")
        lines.append("")

        source_index = {}  # Map source_id to footnote number
        footnote_num = 1

        for i, claim in enumerate(self.claims, 1):
            claim_type_badge = ""
            if claim.claim_type == ClaimType.INFERRED:
                claim_type_badge = " *(inferred)*"
            elif claim.claim_type == ClaimType.MODELED:
                claim_type_badge = " *(modeled)*"

            confidence_badge = ""
            if claim.confidence == Confidence.LOW:
                confidence_badge = " [Low confidence]"
            elif claim.confidence == Confidence.MEDIUM:
                confidence_badge = " [Medium confidence]"

            # Build footnote references
            refs = []
            for source_id in claim.source_ids:
                if source_id not in source_index:
                    source_index[source_id] = footnote_num
                    footnote_num += 1
                refs.append(f"[^{source_index[source_id]}]")

            ref_str = "".join(refs) if refs else " [NO SOURCE]"

            lines.append(f"{i}. {claim.claim_text}{claim_type_badge}{confidence_badge}{ref_str}")
            lines.append("")

        lines.append("## Sources")
        lines.append("")

        # Output footnotes in order
        for source_id, idx in sorted(source_index.items(), key=lambda x: x[1]):
            source = self.sources.get(source_id)
            if source:
                lines.append(source.to_markdown_citation(idx))
            else:
                lines.append(f"[^{idx}]: Source {source_id} not found")

        lines.append("")
        lines.append("---")
        lines.append(f"*Generated by {self.generated_by}*")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "pack_id": self.pack_id,
            "title": self.title,
            "issue_id": self.issue_id,
            "summary": self.summary,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "status": self.status.value,
            "validation_errors": self.validation_errors,
            "output_path": self.output_path,
            "claims": [
                {
                    "claim_text": c.claim_text,
                    "claim_type": c.claim_type.value,
                    "confidence": c.confidence.value,
                    "source_ids": c.source_ids,
                    "last_verified": c.last_verified,
                }
                for c in self.claims
            ],
            "sources": {
                sid: {
                    "source_id": s.source_id,
                    "source_type": s.source_type.value,
                    "title": s.title,
                    "url": s.url,
                    "date_published": s.date_published,
                    "date_accessed": s.date_accessed,
                    "fr_citation": s.fr_citation,
                    "bill_number": s.bill_number,
                    "bill_congress": s.bill_congress,
                    "report_number": s.report_number,
                    "issuing_agency": s.issuing_agency,
                }
                for sid, s in self.sources.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidencePack":
        """Deserialize from dictionary."""
        pack = cls(
            pack_id=data["pack_id"],
            title=data["title"],
            generated_at=data["generated_at"],
            generated_by=data["generated_by"],
            issue_id=data.get("issue_id"),
            summary=data.get("summary"),
            status=PackStatus(data.get("status", "draft")),
            validation_errors=data.get("validation_errors", []),
            output_path=data.get("output_path"),
        )

        for claim_data in data.get("claims", []):
            claim = EvidenceClaim(
                claim_text=claim_data["claim_text"],
                claim_type=ClaimType(claim_data.get("claim_type", "observed")),
                confidence=Confidence(claim_data.get("confidence", "high")),
                source_ids=claim_data.get("source_ids", []),
                last_verified=claim_data.get("last_verified"),
            )
            pack.claims.append(claim)

        for sid, source_data in data.get("sources", {}).items():
            source = EvidenceSource(
                source_id=source_data["source_id"],
                source_type=SourceType(source_data["source_type"]),
                title=source_data["title"],
                url=source_data["url"],
                date_accessed=source_data["date_accessed"],
                date_published=source_data.get("date_published"),
                fr_citation=source_data.get("fr_citation"),
                bill_number=source_data.get("bill_number"),
                bill_congress=source_data.get("bill_congress"),
                report_number=source_data.get("report_number"),
                issuing_agency=source_data.get("issuing_agency"),
            )
            pack.sources[sid] = source

        return pack
