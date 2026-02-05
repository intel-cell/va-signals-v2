"""Evidence Pack generator.

Generates 1-page evidence packs from issues/claims by:
1. Taking an issue/claim as input
2. Querying relevant source tables
3. Extracting supporting citations
4. Validating each claim has at least one source
5. Generating markdown output
6. Outputting to /Intel_Drop/EVIDENCE_PACKS/
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.db import connect, execute, insert_returning_id
from src.evidence.models import (
    EvidencePack,
    EvidenceSource,
    EvidenceClaim,
    EvidenceExcerpt,
    SourceType,
    ClaimType,
    Confidence,
    PackStatus,
)
from src.evidence.extractors import (
    extract_fr_citation,
    extract_bill_citation,
    extract_oversight_citation,
    extract_hearing_citation,
    extract_authority_doc_citation,
    search_citations_by_keyword,
)
from src.evidence.validator import (
    validate_pack,
    require_valid_pack,
    ValidationError,
)


# Output directory for evidence packs
EVIDENCE_PACK_OUTPUT_DIR = Path(os.environ.get("EVIDENCE_PACK_OUTPUT_DIR", "outputs/evidence_packs"))


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class EvidencePackGenerator:
    """Generates evidence packs from issues and claims."""

    def __init__(self, output_dir: Optional[Path] = None, generated_by: str = "bravo_command"):
        self.output_dir = output_dir or EVIDENCE_PACK_OUTPUT_DIR
        self.generated_by = generated_by

    def create_pack(
        self,
        title: str,
        issue_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> EvidencePack:
        """
        Create a new empty evidence pack.

        Args:
            title: Pack title
            issue_id: Optional issue identifier
            summary: Optional summary text

        Returns:
            New EvidencePack instance
        """
        pack_id = EvidencePack.generate_pack_id(issue_id)
        return EvidencePack(
            pack_id=pack_id,
            title=title,
            issue_id=issue_id,
            summary=summary,
            generated_at=utc_now_iso(),
            generated_by=self.generated_by,
        )

    def add_source_by_id(
        self,
        pack: EvidencePack,
        source_type: SourceType,
        identifier: str
    ) -> Optional[EvidenceSource]:
        """
        Add a source to the pack by looking it up in the database.

        Args:
            pack: Evidence pack to add source to
            source_type: Type of source
            identifier: Source identifier (doc_id, bill_id, event_id, etc.)

        Returns:
            The added EvidenceSource or None if not found
        """
        source = None

        if source_type == SourceType.FEDERAL_REGISTER:
            source = extract_fr_citation(identifier)
        elif source_type == SourceType.BILL:
            source = extract_bill_citation(identifier)
        elif source_type in (SourceType.GAO_REPORT, SourceType.OIG_REPORT, SourceType.CRS_REPORT):
            source = extract_oversight_citation(identifier)
        elif source_type == SourceType.HEARING:
            source = extract_hearing_citation(identifier)
        elif source_type == SourceType.AUTHORITY_DOC:
            source = extract_authority_doc_citation(identifier)

        if source:
            pack.add_source(source)

        return source

    def add_claim(
        self,
        pack: EvidencePack,
        claim_text: str,
        source_ids: list[str],
        claim_type: ClaimType = ClaimType.OBSERVED,
        confidence: Confidence = Confidence.HIGH,
    ) -> EvidenceClaim:
        """
        Add a claim to the pack with supporting sources.

        Args:
            pack: Evidence pack to add claim to
            claim_text: The claim statement
            source_ids: List of source IDs supporting this claim
            claim_type: Type of claim (observed, inferred, modeled)
            confidence: Confidence level

        Returns:
            The added EvidenceClaim
        """
        claim = EvidenceClaim(
            claim_text=claim_text,
            source_ids=source_ids,
            claim_type=claim_type,
            confidence=confidence,
            last_verified=utc_now_iso(),
        )
        pack.add_claim(claim)
        return claim

    def auto_populate_sources(
        self,
        pack: EvidencePack,
        keywords: list[str],
        source_types: Optional[list[SourceType]] = None,
        limit_per_type: int = 10
    ) -> list[EvidenceSource]:
        """
        Automatically find and add relevant sources based on keywords.

        Args:
            pack: Evidence pack to populate
            keywords: Search keywords
            source_types: Optional filter by source types
            limit_per_type: Max sources per type

        Returns:
            List of added sources
        """
        added_sources = []

        for keyword in keywords:
            sources = search_citations_by_keyword(
                keyword,
                source_types=source_types,
                limit=limit_per_type
            )
            for source in sources:
                if source.source_id not in pack.sources:
                    pack.add_source(source)
                    added_sources.append(source)

        return added_sources

    def generate_markdown(self, pack: EvidencePack) -> str:
        """
        Generate markdown output for the evidence pack.

        Args:
            pack: Evidence pack to render

        Returns:
            Markdown string
        """
        return pack.to_markdown()

    def save_pack(
        self,
        pack: EvidencePack,
        validate: bool = True,
        strict: bool = False
    ) -> Path:
        """
        Save evidence pack to file and database.

        Args:
            pack: Evidence pack to save
            validate: Whether to validate before saving
            strict: Whether to fail on validation warnings

        Returns:
            Path to saved file

        Raises:
            ValidationError: If validation fails
        """
        if validate:
            require_valid_pack(pack, strict=strict)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"EVIDENCE_PACK_{pack.issue_id or 'GENERAL'}_{date_str}.md"
        filepath = self.output_dir / filename

        # Write markdown
        markdown = self.generate_markdown(pack)
        filepath.write_text(markdown)

        pack.output_path = str(filepath)
        pack.status = PackStatus.PUBLISHED

        # Save to database
        self._save_to_database(pack)

        return filepath

    def _save_to_database(self, pack: EvidencePack) -> None:
        """Save evidence pack to database tables."""
        con = connect()
        try:
            # Insert pack
            execute(
                con,
                """
                INSERT INTO evidence_packs (
                    pack_id, issue_id, title, summary, generated_at, generated_by,
                    status, validation_passed, validation_errors, output_path
                ) VALUES (
                    :pack_id, :issue_id, :title, :summary, :generated_at, :generated_by,
                    :status, :validation_passed, :validation_errors, :output_path
                ) ON CONFLICT(pack_id) DO UPDATE SET
                    status = :status,
                    validation_passed = :validation_passed,
                    validation_errors = :validation_errors,
                    output_path = :output_path,
                    updated_at = datetime('now')
                """,
                {
                    "pack_id": pack.pack_id,
                    "issue_id": pack.issue_id,
                    "title": pack.title,
                    "summary": pack.summary,
                    "generated_at": pack.generated_at,
                    "generated_by": pack.generated_by,
                    "status": pack.status.value,
                    "validation_passed": 1 if pack.status == PackStatus.VALIDATED else 0,
                    "validation_errors": json.dumps(pack.validation_errors) if pack.validation_errors else None,
                    "output_path": pack.output_path,
                }
            )

            # Insert sources
            for source in pack.sources.values():
                execute(
                    con,
                    """
                    INSERT INTO evidence_sources (
                        source_id, source_type, title, date_published, date_effective,
                        date_accessed, url, document_hash, version,
                        fr_citation, fr_doc_number, bill_number, bill_congress,
                        report_number, issuing_agency, document_type, metadata_json
                    ) VALUES (
                        :source_id, :source_type, :title, :date_published, :date_effective,
                        :date_accessed, :url, :document_hash, :version,
                        :fr_citation, :fr_doc_number, :bill_number, :bill_congress,
                        :report_number, :issuing_agency, :document_type, :metadata_json
                    ) ON CONFLICT(source_id) DO UPDATE SET
                        version = :version,
                        date_accessed = :date_accessed,
                        updated_at = datetime('now')
                    """,
                    {
                        "source_id": source.source_id,
                        "source_type": source.source_type.value,
                        "title": source.title,
                        "date_published": source.date_published,
                        "date_effective": source.date_effective,
                        "date_accessed": source.date_accessed,
                        "url": source.url,
                        "document_hash": source.document_hash,
                        "version": source.version,
                        "fr_citation": source.fr_citation,
                        "fr_doc_number": source.fr_doc_number,
                        "bill_number": source.bill_number,
                        "bill_congress": source.bill_congress,
                        "report_number": source.report_number,
                        "issuing_agency": source.issuing_agency,
                        "document_type": source.document_type,
                        "metadata_json": json.dumps(source.metadata) if source.metadata else None,
                    }
                )

            # Insert claims
            for i, claim in enumerate(pack.claims):
                cur = execute(
                    con,
                    """
                    INSERT INTO evidence_claims (
                        pack_id, claim_text, claim_type, confidence, last_verified
                    ) VALUES (
                        :pack_id, :claim_text, :claim_type, :confidence, :last_verified
                    )
                    """,
                    {
                        "pack_id": pack.pack_id,
                        "claim_text": claim.claim_text,
                        "claim_type": claim.claim_type.value,
                        "confidence": claim.confidence.value,
                        "last_verified": claim.last_verified,
                    }
                )

                # Get claim ID
                claim_id = cur.lastrowid

                # Insert claim-source links
                for source_id in claim.source_ids:
                    execute(
                        con,
                        """
                        INSERT INTO evidence_claim_sources (
                            claim_id, source_id
                        ) VALUES (
                            :claim_id, :source_id
                        ) ON CONFLICT(claim_id, source_id, excerpt_id) DO NOTHING
                        """,
                        {
                            "claim_id": claim_id,
                            "source_id": source_id,
                        }
                    )

            con.commit()
        finally:
            con.close()


def generate_evidence_pack_for_issue(
    issue_id: str,
    title: str,
    claims_with_sources: list[dict],
    summary: Optional[str] = None,
    validate: bool = True,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    High-level function to generate an evidence pack for an issue.

    Args:
        issue_id: Unique issue identifier
        title: Pack title
        claims_with_sources: List of dicts with:
            - claim_text: str
            - source_refs: list of (source_type, identifier) tuples
            - claim_type: Optional ClaimType (default: OBSERVED)
            - confidence: Optional Confidence (default: HIGH)
        summary: Optional summary text
        validate: Whether to validate before saving
        output_dir: Optional custom output directory

    Returns:
        Path to saved evidence pack file

    Example:
        generate_evidence_pack_for_issue(
            issue_id="TOXIC_EXPOSURE_RULE",
            title="Toxic Exposure PACT Act Implementation Evidence",
            claims_with_sources=[
                {
                    "claim_text": "VA published final rule on toxic exposure benefits",
                    "source_refs": [
                        (SourceType.FEDERAL_REGISTER, "2024-01234"),
                    ],
                },
                {
                    "claim_text": "Senate Veterans Affairs Committee held oversight hearing",
                    "source_refs": [
                        (SourceType.HEARING, "hvac-118-001"),
                    ],
                },
            ],
            summary="Evidence supporting toxic exposure rule monitoring"
        )
    """
    generator = EvidencePackGenerator(output_dir=output_dir)
    pack = generator.create_pack(title=title, issue_id=issue_id, summary=summary)

    # Add sources and build claim objects
    for claim_data in claims_with_sources:
        source_ids = []

        # Add each source reference
        for source_type, identifier in claim_data["source_refs"]:
            source = generator.add_source_by_id(pack, source_type, identifier)
            if source:
                source_ids.append(source.source_id)

        # Add the claim
        if source_ids:  # Only add claim if we found at least one source
            generator.add_claim(
                pack,
                claim_text=claim_data["claim_text"],
                source_ids=source_ids,
                claim_type=claim_data.get("claim_type", ClaimType.OBSERVED),
                confidence=claim_data.get("confidence", Confidence.HIGH),
            )

    # Save and return path
    return generator.save_pack(pack, validate=validate)


def generate_quick_evidence_pack(
    topic: str,
    keywords: list[str],
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Generate a quick evidence pack by searching for sources matching keywords.

    This is a convenience function for rapidly building evidence packs
    from search results.

    Args:
        topic: Topic title for the pack
        keywords: Keywords to search for sources
        output_dir: Optional custom output directory

    Returns:
        Path to saved evidence pack file
    """
    generator = EvidencePackGenerator(output_dir=output_dir)
    pack = generator.create_pack(
        title=f"Evidence Pack: {topic}",
        summary=f"Auto-generated evidence pack for topic: {topic}"
    )

    # Find sources
    sources = generator.auto_populate_sources(pack, keywords)

    # Create a single summary claim linking all sources
    if sources:
        generator.add_claim(
            pack,
            claim_text=f"Multiple sources document activity related to: {topic}",
            source_ids=[s.source_id for s in sources],
            claim_type=ClaimType.OBSERVED,
            confidence=Confidence.MEDIUM,
        )

    return generator.save_pack(pack, validate=True, strict=False)
