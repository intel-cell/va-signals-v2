"""
Generate embeddings for agenda drift utterances.

Uses sentence-transformers for local embedding generation (no API key needed).
Default model: all-MiniLM-L6-v2 (384 dimensions, fast, good quality)

Usage:
    python -m src.embed_utterances [--batch-size N] [--model MODEL]
"""

import argparse
import sys

from . import db

# Default model - good balance of speed and quality
DEFAULT_MODEL = "all-MiniLM-L6-v2"


def get_utterances_without_embeddings(limit: int = 1000) -> list[dict]:
    """Get utterances that don't have embeddings yet."""
    con = db.connect()
    cur = db.execute(
        con,
        """SELECT u.utterance_id, u.member_id, u.content
           FROM ad_utterances u
           LEFT JOIN ad_embeddings e ON u.utterance_id = e.utterance_id
           WHERE e.utterance_id IS NULL
           LIMIT :limit""",
        {"limit": limit},
    )
    rows = cur.fetchall()
    con.close()
    return [{"utterance_id": r[0], "member_id": r[1], "content": r[2]} for r in rows]


def get_embedding_stats() -> dict:
    """Get statistics about embeddings."""
    con = db.connect()

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_utterances")
    total_utterances = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(*) FROM ad_embeddings")
    total_embeddings = cur.fetchone()[0]

    cur = db.execute(con, "SELECT COUNT(DISTINCT member_id) FROM ad_utterances")
    total_members = cur.fetchone()[0]

    cur = db.execute(
        con,
        """SELECT COUNT(DISTINCT u.member_id)
           FROM ad_utterances u
           JOIN ad_embeddings e ON u.utterance_id = e.utterance_id""",
    )
    members_with_embeddings = cur.fetchone()[0]

    con.close()
    return {
        "total_utterances": total_utterances,
        "total_embeddings": total_embeddings,
        "pending": total_utterances - total_embeddings,
        "total_members": total_members,
        "members_with_embeddings": members_with_embeddings,
    }


def load_model(model_name: str):
    """Load the sentence transformer model."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("Error: sentence-transformers not installed.", file=sys.stderr)
        print("Run: pip install sentence-transformers", file=sys.stderr)
        sys.exit(1)

    print(f"Loading model: {model_name}...")
    return SentenceTransformer(model_name)


def generate_embeddings(
    model,
    utterances: list[dict],
    batch_size: int = 32,
    show_progress: bool = True,
) -> list[tuple[str, list[float]]]:
    """
    Generate embeddings for utterances.

    Returns list of (utterance_id, embedding_vector) tuples.
    """
    if not utterances:
        return []

    texts = [u["content"] for u in utterances]
    ids = [u["utterance_id"] for u in utterances]

    if show_progress:
        print(f"Generating embeddings for {len(texts)} utterances...")

    # Generate embeddings in batches
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )

    # Convert to list of floats for JSON storage
    results = []
    for i, emb in enumerate(embeddings):
        results.append((ids[i], emb.tolist()))

    return results


def store_embeddings(embeddings: list[tuple[str, list[float]]], model_id: str) -> int:
    """Store embeddings in database. Returns count stored."""
    stored = 0
    for utterance_id, vec in embeddings:
        db.upsert_ad_embedding(utterance_id, vec, model_id)
        stored += 1
    return stored


def embed_pending(
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
    limit: int = 1000,
) -> dict:
    """
    Main entry point: embed all pending utterances.

    Returns stats dict.
    """
    # Get pending utterances
    utterances = get_utterances_without_embeddings(limit=limit)

    if not utterances:
        print("No pending utterances to embed.")
        return {"embedded": 0, "model": model_name}

    print(f"Found {len(utterances)} utterances without embeddings")

    # Load model
    model = load_model(model_name)

    # Generate embeddings
    embeddings = generate_embeddings(model, utterances, batch_size=batch_size)

    # Store in database
    stored = store_embeddings(embeddings, model_id=model_name)

    print(f"Stored {stored} embeddings")

    return {
        "embedded": stored,
        "model": model_name,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for utterances")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Sentence transformer model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding (default: 32)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max utterances to embed (default: 1000)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show embedding statistics only",
    )
    args = parser.parse_args()

    # Ensure DB is initialized
    db.init_db()

    if args.stats:
        stats = get_embedding_stats()
        print("\nEmbedding Statistics")
        print("=" * 40)
        print(f"Total utterances:        {stats['total_utterances']}")
        print(f"Total embeddings:        {stats['total_embeddings']}")
        print(f"Pending:                 {stats['pending']}")
        print(f"Total members:           {stats['total_members']}")
        print(f"Members with embeddings: {stats['members_with_embeddings']}")
        return

    stats = embed_pending(
        model_name=args.model,
        batch_size=args.batch_size,
        limit=args.limit,
    )

    print("\n" + "=" * 40)
    print("SUMMARY")
    print("=" * 40)
    print(f"Embeddings generated: {stats['embedded']}")
    print(f"Model used:           {stats['model']}")

    # Show overall stats
    overall = get_embedding_stats()
    print(f"\nTotal embeddings now:  {overall['total_embeddings']}/{overall['total_utterances']}")
    if overall["pending"] > 0:
        print(f"Still pending:         {overall['pending']}")


if __name__ == "__main__":
    main()
