---
name: committee-press-agent
overview: Implement the Committee Press oversight agent to scrape press releases from House and Senate Veterans' Affairs Committees.
todos:
  - id: verify-sources
    content: Verify RSS feeds for HVAC and SVAC are working and check their structure
    status: completed
  - id: implement-agent
    content: Update src/oversight/agents/committee_press.py to use HTML scraping (RSS feeds are defunct)
    status: completed
  - id: integration-test
    content: Run the agent in isolation to verify it fetches and stores events correctly
    status: completed
isProject: false
---

# Committee Press Agent Implementation Plan

**Goal:** Complete the "Committee Press" oversight agent (LOE 2) to detect press releases from House and Senate Veterans' Affairs Committees.

## Context
- **Phase:** I (Consolidation)
- **Status:** COMPLETE - Switched from RSS to HTML scraping (RSS feeds are 404).
- **Sources:**
  - HVAC: `https://veterans.house.gov/news/documentquery.aspx?DocumentTypeID=2613`
  - SVAC: `https://www.veterans.senate.gov/` (homepage with news links)

## Implementation Details

### 1. Source Verification (DONE)
- RSS feeds returned 404 errors for both committees.
- Identified HTML news pages as alternative sources.

### 2. Agent Logic (`src/oversight/agents/committee_press.py`)
- **`fetch_new(since)`**:
  - Scrapes HVAC press releases page (`article.newsblocker` elements).
  - Scrapes SVAC homepage for news links (filtered by URL patterns).
  - Extracts dates from `time[datetime]` attributes (HVAC) or URL paths (SVAC).
  - Creates `RawEvent` objects with proper metadata.
- **`RawEvent` mapping**:
  - `title`: Article title
  - `excerpt`: Summary text
  - `url`: Full link to press release
  - `metadata.published`: Date string (YYYY-MM-DD from HVAC, inferred from URL for SVAC)
  - `metadata.committee`: hvac or svac

### 3. Verification (DONE)
- Agent successfully fetches 15 events (10 HVAC + 5 SVAC).
- 10 processed into `om_events` table (5 SVAC were deduplicated from prior run).
- 1 escalation detected (fraud signal).

## Results
- **HVAC**: 10 press releases with full date precision
- **SVAC**: 5 press releases with month precision (from URL paths)
- Escalation detection working (detected "fraud" keyword)
