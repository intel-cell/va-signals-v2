"""
Agenda Drift Detection Runner

Builds baselines for members and detects deviations in utterances.

Usage:
    python -m src.run_agenda_drift [--build-baselines] [--detect] [--all]
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from . import db
from .agenda_drift import build_baseline, detect_deviation, explain_deviation, DEVIATION_THRESHOLD_Z


MIN_EMBEDDINGS_FOR_BASELINE = 5


def get_members_with_embeddings() -> list[dict]:
    """Get all members who have at least one embedding."""
    con = db.connect()
    cur = db.execute(
        con,
        """SELECT m.member_id, m.name, m.party, m.committee, COUNT(e.utterance_id) as embedding_count
           FROM ad_members m
           JOIN ad_utterances u ON m.member_id = u.member_id
           JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
           GROUP BY m.member_id
           ORDER BY embedding_count DESC"""
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "member_id": r[0],
            "name": r[1],
            "party": r[2],
            "committee": r[3],
            "embedding_count": r[4],
        }
        for r in rows
    ]


MIN_UTTERANCE_LENGTH = 100  # Filter out short procedural statements


def get_utterances_for_detection(member_id: str = None, limit: int = 500) -> list[dict]:
    """
    Get utterances with embeddings that haven't been checked for deviation yet.

    An utterance is considered "unchecked" if it has an embedding but no deviation event
    (regardless of whether it would trigger one - we track all checks).

    Filters out short utterances (< MIN_UTTERANCE_LENGTH chars) to exclude
    procedural statements like greetings and brief responses.
    """
    con = db.connect()

    if member_id:
        cur = db.execute(
            con,
            """SELECT u.utterance_id, u.member_id, u.hearing_id, u.content, e.vec
               FROM ad_utterances u
               JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
               LEFT JOIN ad_deviation_events d ON u.utterance_id = d.utterance_id
               WHERE u.member_id = :member_id AND d.id IS NULL AND LENGTH(u.content) >= :min_length
               ORDER BY u.spoken_at DESC
               LIMIT :limit""",
            {"member_id": member_id, "min_length": MIN_UTTERANCE_LENGTH, "limit": limit},
        )
    else:
        cur = db.execute(
            con,
            """SELECT u.utterance_id, u.member_id, u.hearing_id, u.content, e.vec
               FROM ad_utterances u
               JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
               LEFT JOIN ad_deviation_events d ON u.utterance_id = d.utterance_id
               WHERE d.id IS NULL AND LENGTH(u.content) >= :min_length
               ORDER BY u.spoken_at DESC
               LIMIT :limit""",
            {"min_length": MIN_UTTERANCE_LENGTH, "limit": limit},
        )

    rows = cur.fetchall()
    con.close()

    return [
        {
            "utterance_id": r[0],
            "member_id": r[1],
            "hearing_id": r[2],
            "content": r[3],
            "vec": json.loads(r[4]),
        }
        for r in rows
    ]


def get_baseline_stats() -> dict:
    """Get statistics about baselines."""
    con = db.connect()

    cur = db.execute(con, "SELECT COUNT(DISTINCT member_id) FROM ad_baselines")
    members_with_baselines = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_baselines")
    total_baselines = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_deviation_events")
    total_deviations = cur.fetchone()[0]

    cur = db.execute(
        con,
        f"SELECT COUNT(*) FROM ad_deviation_events WHERE zscore >= {DEVIATION_THRESHOLD_Z}",
    )
    significant_deviations = cur.fetchone()[0]

    con.close()
    return {
        "members_with_baselines": members_with_baselines,
        "total_baselines": total_baselines,
        "total_deviations": total_deviations,
        "significant_deviations": significant_deviations,
    }


def build_all_baselines(min_embeddings: int = MIN_EMBEDDINGS_FOR_BASELINE) -> dict:
    """
    Build baselines for all members with enough embeddings.

    Returns stats dict.
    """
    members = get_members_with_embeddings()

    stats = {
        "total_members": len(members),
        "eligible_members": 0,
        "baselines_built": 0,
        "skipped_insufficient": 0,
        "errors": [],
    }

    for member in members:
        if member["embedding_count"] < min_embeddings:
            stats["skipped_insufficient"] += 1
            continue

        stats["eligible_members"] += 1

        try:
            result = build_baseline(member["member_id"])
            if result:
                stats["baselines_built"] += 1
                print(f"  Built baseline for {member['name']}: n={result['n']}, mu={result['mu']:.4f}, sigma={result['sigma']:.4f}")
            else:
                stats["errors"].append(f"Failed to build baseline for {member['member_id']}")
        except Exception as e:
            stats["errors"].append(f"Error building baseline for {member['member_id']}: {e}")

    return stats


def run_detection(limit: int = 500, generate_explanations: bool = True) -> dict:
    """
    Run deviation detection on unchecked utterances.

    Args:
        limit: Maximum utterances to check
        generate_explanations: If True, use LLM to generate explanations for deviations

    Returns stats dict.
    """
    stats = {
        "utterances_checked": 0,
        "deviations_found": 0,
        "explanations_generated": 0,
        "no_baseline": 0,
        "errors": [],
    }

    # Get utterances to check
    utterances = get_utterances_for_detection(limit=limit)

    if not utterances:
        print("No unchecked utterances found.")
        return stats

    print(f"Checking {len(utterances)} utterances for deviations...")

    # Group by member for efficiency
    by_member = {}
    for u in utterances:
        by_member.setdefault(u["member_id"], []).append(u)

    for member_id, member_utterances in by_member.items():
        # Check if member has a baseline
        baseline = db.get_latest_ad_baseline(member_id)
        if not baseline:
            stats["no_baseline"] += len(member_utterances)
            continue

        for u in member_utterances:
            try:
                result = detect_deviation(
                    member_id=member_id,
                    utterance_id=u["utterance_id"],
                    vec=u["vec"],
                    hearing_id=u["hearing_id"],
                )

                stats["utterances_checked"] += 1

                if result:
                    stats["deviations_found"] += 1
                    print(f"  DEVIATION: {member_id} in {u['hearing_id']}: z={result['zscore']:.2f}, dist={result['cos_dist']:.4f}")

                    # Generate LLM explanation and update the note field
                    if generate_explanations:
                        explanation = explain_deviation(member_id, u["utterance_id"])
                        if explanation:
                            db.update_ad_deviation_note(result["id"], explanation)
                            stats["explanations_generated"] += 1
                            print(f"    Explanation: {explanation}")

            except Exception as e:
                stats["errors"].append(f"Error checking {u['utterance_id']}: {e}")

    return stats


def get_recent_deviations(limit: int = 10) -> list[dict]:
    """Get recent deviation events for display."""
    return db.get_ad_deviation_events(limit=limit, min_zscore=0)


def backfill_explanations(limit: int = 50) -> dict:
    """Generate explanations for existing deviations that don't have them."""
    stats = {
        "checked": 0,
        "generated": 0,
        "errors": [],
    }

    deviations = db.get_ad_deviations_without_notes(limit=limit)
    if not deviations:
        print("No deviations need explanations.")
        return stats

    print(f"Backfilling explanations for {len(deviations)} deviations...")

    for d in deviations:
        stats["checked"] += 1
        try:
            explanation = explain_deviation(d["member_id"], d["utterance_id"])
            if explanation:
                db.update_ad_deviation_note(d["id"], explanation)
                stats["generated"] += 1
                print(f"  {d['member_name']}: {explanation}")
            else:
                stats["errors"].append(f"No explanation for {d['utterance_id']}")
        except Exception as e:
            stats["errors"].append(f"Error for {d['utterance_id']}: {e}")

    return stats


def print_summary():
    """Print overall system summary."""
    # Embedding stats
    con = db.connect()
    cur = db.execute(con, "SELECT COUNT(*) FROM ad_members")
    total_members = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_utterances")
    total_utterances = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_embeddings")
    total_embeddings = cur.fetchone()[0]

    con.close()

    baseline_stats = get_baseline_stats()

    print("\n" + "=" * 60)
    print("AGENDA DRIFT DETECTION - SYSTEM STATUS")
    print("=" * 60)
    print(f"Members:              {total_members}")
    print(f"Utterances:           {total_utterances}")
    print(f"Embeddings:           {total_embeddings}")
    print(f"Members w/ baselines: {baseline_stats['members_with_baselines']}")
    print(f"Total deviations:     {baseline_stats['total_deviations']}")
    print(f"Significant (z≥{DEVIATION_THRESHOLD_Z}):  {baseline_stats['significant_deviations']}")

    # Show recent deviations
    recent = get_recent_deviations(limit=5)
    if recent:
        print("\nRecent Deviations:")
        print("-" * 60)
        for d in recent:
            print(f"  {d['member_name']}: z={d['zscore']:.2f} in {d['hearing_id']}")


def main():
    parser = argparse.ArgumentParser(description="Run agenda drift detection")
    parser.add_argument("--build-baselines", action="store_true", help="Build baselines for all eligible members")
    parser.add_argument("--detect", action="store_true", help="Run deviation detection on unchecked utterances")
    parser.add_argument("--all", action="store_true", help="Build baselines AND run detection")
    parser.add_argument("--summary", action="store_true", help="Show system summary only")
    parser.add_argument("--limit", type=int, default=500, help="Max utterances to check (default: 500)")
    parser.add_argument("--min-embeddings", type=int, default=MIN_EMBEDDINGS_FOR_BASELINE,
                        help=f"Min embeddings required for baseline (default: {MIN_EMBEDDINGS_FOR_BASELINE})")
    parser.add_argument("--no-explanations", action="store_true",
                        help="Skip LLM explanation generation for deviations")
    parser.add_argument("--backfill-explanations", action="store_true",
                        help="Generate explanations for existing deviations that don't have them")
    args = parser.parse_args()

    # Ensure DB is initialized
    db.init_db()

    if args.summary:
        print_summary()
        return

    if args.backfill_explanations:
        print("\n" + "=" * 60)
        print("BACKFILLING EXPLANATIONS")
        print("=" * 60)

        stats = backfill_explanations(limit=args.limit)

        print(f"\nBackfill Summary:")
        print(f"  Checked:   {stats['checked']}")
        print(f"  Generated: {stats['generated']}")
        if stats["errors"]:
            print(f"  Errors:    {len(stats['errors'])}")

        print_summary()
        return

    # Default to --all if nothing specified
    if not args.build_baselines and not args.detect and not args.all:
        args.all = True

    if args.all or args.build_baselines:
        print("\n" + "=" * 60)
        print("BUILDING BASELINES")
        print("=" * 60)

        stats = build_all_baselines(min_embeddings=args.min_embeddings)

        print(f"\nBaseline Summary:")
        print(f"  Total members:      {stats['total_members']}")
        print(f"  Eligible (≥{args.min_embeddings} emb): {stats['eligible_members']}")
        print(f"  Baselines built:    {stats['baselines_built']}")
        print(f"  Skipped (too few):  {stats['skipped_insufficient']}")

        if stats["errors"]:
            print(f"  Errors: {len(stats['errors'])}")

    if args.all or args.detect:
        print("\n" + "=" * 60)
        print("RUNNING DEVIATION DETECTION")
        print("=" * 60)

        generate_explanations = not args.no_explanations
        stats = run_detection(limit=args.limit, generate_explanations=generate_explanations)

        print(f"\nDetection Summary:")
        print(f"  Utterances checked: {stats['utterances_checked']}")
        print(f"  Deviations found:   {stats['deviations_found']}")
        if generate_explanations:
            print(f"  Explanations gen:   {stats['explanations_generated']}")
        print(f"  Skipped (no base):  {stats['no_baseline']}")

        if stats["errors"]:
            print(f"  Errors: {len(stats['errors'])}")

    # Always show final summary
    print_summary()


if __name__ == "__main__":
    main()
