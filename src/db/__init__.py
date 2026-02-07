"""Database access layer -- domain-organized package.

All public functions are re-exported here so that existing consumer
imports (``from src.db import connect, execute, ...``) continue to work.
"""

from .ad import (
    bulk_insert_ad_utterances,
    get_ad_deviation_events,
    get_ad_deviations_without_notes,
    get_ad_embeddings_for_member,
    get_ad_member_deviation_history,
    get_ad_recent_deviations_for_hearing,
    get_ad_typical_utterances,
    get_ad_utterance_by_id,
    get_ad_utterances_for_member,
    get_latest_ad_baseline,
    insert_ad_baseline,
    insert_ad_deviation_event,
    update_ad_deviation_note,
    upsert_ad_embedding,
    upsert_ad_member,
)
from .authority import (
    fetch_unrouted_authority_docs,
    get_authority_doc,
    get_authority_doc_by_hash,
    get_authority_docs,
    mark_authority_doc_routed,
    upsert_authority_doc,
)
from .bills import (
    get_bill,
    get_bill_actions,
    get_bill_stats,
    get_bills,
    get_new_actions_since,
    get_new_bills_since,
    insert_bill_action,
    update_committees_json,
    upsert_bill,
)
from .compound import (
    get_compound_signal,
    get_compound_signals,
    get_compound_stats,
    insert_compound_signal,
    resolve_compound_signal,
)
from .core import (
    DB_PATH,
    ROOT,
    SCHEMA_PATH,
    SCHEMA_POSTGRES_PATH,
    _count_inserted_rows,
    _is_postgres,
    _normalize_db_url,
    _prepare_query,
    assert_tables_exist,
    connect,
    execute,
    executemany,
    get_db_backend,
    get_schema_path,
    init_db,
    insert_returning_id,
    table_exists,
)
from .fr import (
    bulk_insert_fr_seen,
    get_existing_fr_doc_ids,
    update_fr_seen_dates,
    upsert_ecfr_seen,
    upsert_fr_seen,
)
from .hearings import (
    _hearing_row_to_dict,
    get_hearing,
    get_hearing_changes_since,
    get_hearing_stats,
    get_hearing_updates,
    get_hearings,
    get_new_hearings_since,
    insert_hearing_update,
    upsert_hearing,
)
from .helpers import (
    _utc_now_iso,
    insert_source_run,
)
from .lda import (
    get_lda_stats,
    get_new_lda_filings_since,
    insert_lda_alert,
    upsert_lda_filing,
)
