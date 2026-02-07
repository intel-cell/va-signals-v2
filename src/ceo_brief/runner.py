"""
CEO Brief Pipeline Runner.

Orchestrates the full pipeline: aggregation -> analysis -> generation.
Provides CLI interface for manual runs and scheduling hooks.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .aggregator import aggregate_deltas
from .analyst import analyze_deltas
from .db_helpers import get_latest_brief, list_briefs
from .generator import (
    DEFAULT_OUTPUT_DIR,
    generate_and_save_brief,
    generate_and_save_enhanced_brief,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ceo_brief")


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    success: bool
    brief_id: str | None
    markdown_path: str | None
    json_path: str | None
    validation_errors: list[str]
    stats: dict
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "brief_id": self.brief_id,
            "markdown_path": self.markdown_path,
            "json_path": self.json_path,
            "validation_errors": self.validation_errors,
            "stats": self.stats,
            "error": self.error,
        }


def run_pipeline(
    period_start: date | None = None,
    period_end: date | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
    enhanced: bool = True,
) -> PipelineResult:
    """
    Run the full CEO Brief generation pipeline.

    Args:
        period_start: Start of reporting period (default: 7 days ago)
        period_end: End of reporting period (default: today)
        output_dir: Directory for output files (default: Intel_Drop/CEO_BRIEFS)
        dry_run: If True, don't save to files or database
        enhanced: If True, use cross-command integration (BRAVO, CHARLIE, DELTA)

    Returns:
        PipelineResult with success status and file paths
    """
    try:
        # Set default period
        if period_end is None:
            period_end = date.today()
        if period_start is None:
            period_start = period_end - timedelta(days=7)

        logger.info(f"Starting CEO Brief pipeline for {period_start} to {period_end}")

        # Phase 1: Aggregation
        logger.info("Phase 1: Aggregating deltas from all sources...")
        aggregation = aggregate_deltas(period_start, period_end)
        logger.info(
            f"Aggregation complete: {aggregation.total_count} deltas found "
            f"(FR: {len(aggregation.fr_deltas)}, Bills: {len(aggregation.bill_deltas)}, "
            f"Hearings: {len(aggregation.hearing_deltas)}, Oversight: {len(aggregation.oversight_deltas)}, "
            f"State: {len(aggregation.state_deltas)})"
        )

        # Phase 2: Analysis
        logger.info("Phase 2: Analyzing deltas and drafting content...")
        analysis = analyze_deltas(aggregation)
        logger.info(
            f"Analysis complete: {analysis.issues_identified} top issues identified, "
            f"{len(analysis.draft_messages)} messages drafted"
        )

        # Phase 3: Generation
        logger.info("Phase 3: Generating CEO Brief...")

        if dry_run:
            logger.info("Dry run mode - skipping file and database writes")
            return PipelineResult(
                success=True,
                brief_id=None,
                markdown_path=None,
                json_path=None,
                validation_errors=[],
                stats={
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "total_deltas": aggregation.total_count,
                    "top_issues": analysis.issues_identified,
                    "dry_run": True,
                },
            )

        if enhanced:
            logger.info("Using enhanced generation with cross-command integration...")
            result = generate_and_save_enhanced_brief(
                analysis, period_start, period_end, output_dir, use_cross_command=True
            )
        else:
            result = generate_and_save_brief(analysis, period_start, period_end, output_dir)

        logger.info(f"Brief generated: {result['brief_id']}")
        logger.info(f"Markdown output: {result['markdown_path']}")

        if result["validation_errors"]:
            logger.warning(f"Validation warnings: {len(result['validation_errors'])}")
            for err in result["validation_errors"]:
                logger.warning(f"  - {err}")

        return PipelineResult(
            success=True,
            brief_id=result["brief_id"],
            markdown_path=result["markdown_path"],
            json_path=result["json_path"],
            validation_errors=result["validation_errors"],
            stats={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "total_deltas": aggregation.total_count,
                "top_issues": analysis.issues_identified,
                "enhanced": enhanced,
                "sources": {
                    "federal_register": len(aggregation.fr_deltas),
                    "bills": len(aggregation.bill_deltas),
                    "hearings": len(aggregation.hearing_deltas),
                    "oversight": len(aggregation.oversight_deltas),
                    "state": len(aggregation.state_deltas),
                },
            },
        )

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return PipelineResult(
            success=False,
            brief_id=None,
            markdown_path=None,
            json_path=None,
            validation_errors=[],
            stats={},
            error=str(e),
        )


def show_status() -> dict:
    """Show pipeline status and recent briefs."""
    latest = get_latest_brief()
    recent = list_briefs(limit=5)

    return {
        "latest_brief": latest,
        "recent_briefs": recent,
        "output_directory": str(DEFAULT_OUTPUT_DIR),
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CEO Brief Pipeline - Generate weekly decision instruments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate brief for last 7 days
  python -m src.ceo_brief.runner

  # Generate brief for specific period
  python -m src.ceo_brief.runner --start 2026-01-28 --end 2026-02-04

  # Dry run (no files written)
  python -m src.ceo_brief.runner --dry-run

  # Check status
  python -m src.ceo_brief.runner --status
        """,
    )

    parser.add_argument(
        "--start",
        type=str,
        help="Period start date (YYYY-MM-DD). Default: 7 days ago",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="Period end date (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without saving files or database",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline status and recent briefs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--enhanced",
        action="store_true",
        default=True,
        help="Use enhanced generation with cross-command integration (default: True)",
    )
    parser.add_argument(
        "--no-enhanced",
        action="store_true",
        help="Disable cross-command integration (use basic generation)",
    )

    args = parser.parse_args()

    # Handle --no-enhanced flag
    if args.no_enhanced:
        args.enhanced = False

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Status command
    if args.status:
        status = show_status()
        if args.json:
            print(json.dumps(status, indent=2, default=str))
        else:
            print("\n=== CEO Brief Pipeline Status ===\n")
            print(f"Output Directory: {status['output_directory']}")

            if status["latest_brief"]:
                latest = status["latest_brief"]
                print("\nLatest Brief:")
                print(f"  ID: {latest['brief_id']}")
                print(f"  Generated: {latest['generated_at']}")
                print(f"  Period: {latest['period_start']} to {latest['period_end']}")
                print(f"  Status: {latest['status']}")
            else:
                print("\nNo briefs generated yet.")

            if status["recent_briefs"]:
                print("\nRecent Briefs:")
                for b in status["recent_briefs"]:
                    print(f"  - {b['brief_id']} ({b['status']})")
        return 0

    # Parse dates
    period_start = None
    period_end = None

    if args.start:
        try:
            period_start = date.fromisoformat(args.start)
        except ValueError:
            print(f"Error: Invalid start date format: {args.start}")
            return 1

    if args.end:
        try:
            period_end = date.fromisoformat(args.end)
        except ValueError:
            print(f"Error: Invalid end date format: {args.end}")
            return 1

    output_dir = Path(args.output_dir) if args.output_dir else None

    # Run pipeline
    result = run_pipeline(
        period_start=period_start,
        period_end=period_end,
        output_dir=output_dir,
        dry_run=args.dry_run,
        enhanced=args.enhanced,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("\n=== CEO Brief Pipeline Result ===\n")
        if result.success:
            print("Status: SUCCESS")
            if result.brief_id:
                print(f"Brief ID: {result.brief_id}")
                print(f"Markdown: {result.markdown_path}")
                print(f"JSON: {result.json_path}")
            print("\nStats:")
            print(
                f"  Period: {result.stats.get('period_start')} to {result.stats.get('period_end')}"
            )
            print(f"  Total Deltas: {result.stats.get('total_deltas', 0)}")
            print(f"  Top Issues: {result.stats.get('top_issues', 0)}")

            if result.validation_errors:
                print(f"\nValidation Warnings ({len(result.validation_errors)}):")
                for err in result.validation_errors:
                    print(f"  - {err}")
        else:
            print("Status: FAILED")
            print(f"Error: {result.error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
