---
name: congressional-record-agent
overview: Implement the Congressional Record oversight agent using the Congress.gov API to track VA-related floor activity and remarks.
todos:
  - id: verify-api
    content: Create and run a script to verify Congress.gov API access to Congressional Record endpoints and inspect data structure
    status: pending
  - id: implement-agent
    content: Implement fetch_new in src/oversight/agents/congressional_record.py using the API
    status: pending
  - id: add-filtering
    content: Add logic to filter CR entries by VA-related keywords (veterans, VA, etc.) and extract metadata
    status: pending
  - id: integration-test
    content: Run the agent in isolation to verify it fetches and stores events correctly
    status: pending
isProject: false
---

# Congressional Record Agent Implementation Plan

**Goal:** Complete the "Congressional Record" oversight agent (LOE 2) to detect VA-related floor speeches, debates, and insertions.

## Context

- **Phase:** I (Consolidation)
- **Status:** Currently a placeholder stub.
- **Dependency:** Requires `CONGRESS_API_KEY` (already available).

## Implementation Details

### 1. API Strategy

- Use `https://api.congress.gov/v3/congressional-record`
- Endpoints to explore:
  - `/?y={year}&m={month}&d={day}`: Get daily issues.
  - `/article/{volume}/{issue}/{section}`: Get article text/summary.
- **Filtering:** Since the API might not support server-side keyword search for CR, we will:
  1. Fetch the daily digest/list for recent days.
  2. Filter titles/summaries for keywords: "Veterans", "VA", "Department of Veterans Affairs".
  3. Fetch full text only for matches (if needed/possible).

### 2. Agent Logic (`src/oversight/agents/congressional_record.py`)

- `**fetch_new(since)`**:
  - Iterate back from today to `since` (or last 7 days if None).
  - Call API for each day.
  - Parse response.
  - Filter for keywords.
  - Create `RawEvent` objects.
- `**RawEvent` mapping**:
  - `title`: CR Article Title
  - `description`: Summary or snippet
  - `url`: Link to Congress.gov text
  - `source_id`: CR volume/issue/article ID
  - `metadata`: Speaker, Chamber (House/Senate), Date

### 3. Verification

- Create `scripts/test_cr_api.py` to validate the API response shape before coding the agent.
- Run `python -m src.run_oversight --agent congressional_record` to verify end-to-end.

## Next Steps

1. Create verification script.
2. Implement agent.
3. Verify.

