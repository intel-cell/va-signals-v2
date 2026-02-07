# Data Quality — Known Limitations

## bf_vehicles: Empty columns (Issue #5)
The `purpose`, `market_survey_url`, `award_date`, and `vendor` columns are empty
because these fields represent future-phase features not yet implemented in the
procurement tracking pipeline. They are schema placeholders for planned functionality.

## lda_filings: Sparse financial data (Issue #6)
The `income` and `expenses` columns are frequently null because the OpenSecrets/LDA
API does not consistently provide financial details for all filings. This is an
upstream API data limitation, not a pipeline bug.

## Source runs: 52% NO_DATA, 21.5% ERROR (Issue #8)
NO_DATA status is expected and normal for:
- Sources that publish infrequently (e.g., GAO reports, OIG investigations)
- Weekend/holiday runs when no new content exists
- Congressional recess periods

ERROR status should be monitored via `scripts/diagnose_source_health.py` to
identify persistent failures (expired API keys, rate limiting, endpoint changes).

## State coverage: 10 states only (Issue #11)
State monitoring covers TX, CA, FL, PA, OH, NY, NC, GA, VA, AZ by design.
These represent the 10 states with the highest veteran populations per VA data.
Expansion to additional states requires adding official source scrapers, which
is a feature request, not a data quality issue.
