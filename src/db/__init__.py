"""Database access layer -- domain-organized package.

All public functions are re-exported here so that existing consumer
imports (``from src.db import connect, execute, ...``) continue to work.
"""

from .core import (
    connect,
    execute,
    executemany,
    table_exists,
    insert_returning_id,
    get_db_backend,
    get_schema_path,
    init_db,
    assert_tables_exist,
    _prepare_query,
    _is_postgres,
    _count_inserted_rows,
    _normalize_db_url,
    DB_PATH,
    ROOT,
    SCHEMA_PATH,
    SCHEMA_POSTGRES_PATH,
)
from .helpers import (
    insert_source_run,
    _utc_now_iso,
)
from .fr import (
    upsert_fr_seen,
    update_fr_seen_dates,
    get_existing_fr_doc_ids,
    bulk_insert_fr_seen,
    upsert_ecfr_seen,
)
from .ad import (
    upsert_ad_member,
    bulk_insert_ad_utterances,
    get_ad_utterances_for_member,
    upsert_ad_embedding,
    get_ad_embeddings_for_member,
    insert_ad_baseline,
    get_latest_ad_baseline,
    insert_ad_deviation_event,
    get_ad_deviation_events,
    get_ad_member_deviation_history,
    get_ad_recent_deviations_for_hearing,
    get_ad_utterance_by_id,
    get_ad_typical_utterances,
    update_ad_deviation_note,
    get_ad_deviations_without_notes,
)
from .bills import (
    upsert_bill,
    get_bill,
    get_bills,
    insert_bill_action,
    get_bill_actions,
    get_new_bills_since,
    get_new_actions_since,
    get_bill_stats,
)
from .hearings import (
    _hearing_row_to_dict,
    upsert_hearing,
    get_hearing,
    get_hearings,
    insert_hearing_update,
    get_hearing_updates,
    get_new_hearings_since,
    get_hearing_changes_since,
    get_hearing_stats,
)
from .authority import (
    upsert_authority_doc,
    fetch_unrouted_authority_docs,
    mark_authority_doc_routed,
    get_authority_doc,
    get_authority_docs,
    get_authority_doc_by_hash,
)
from .lda import (
    upsert_lda_filing,
    insert_lda_alert,
    get_new_lda_filings_since,
    get_lda_stats,
)
from .compound import (
    insert_compound_signal,
    get_compound_signal,
    get_compound_signals,
    resolve_compound_signal,
    get_compound_stats,
)
