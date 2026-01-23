# Decision Log

Architecture and implementation decisions with rationale. Newest first.

---

## 2026-01-22: VA OIG domain migration fix

**Context:** OIG agent RSS feed at `va.gov/oig/rss/pubs-all.xml` returning 404. VA OIG site non-functional.

**Analysis:**
- VA OIG migrated from `va.gov/oig` to standalone domain `vaoig.gov`
- Redirect (302) from old to new domain
- New RSS feed at `vaoig.gov/rss.xml` - 10 items, RSS 2.0 format

**Decision:** Update OIG_RSS_URL from `https://www.va.gov/oig/rss/pubs-all.xml` to `https://www.vaoig.gov/rss.xml`

**Result:** OIG agent now fetching 10 reports successfully.

**Files:** `src/oversight/agents/oig.py:12`

---

## 2026-01-22: CRS agent data source (everycrsreport.com)

**Context:** CRS agent was a placeholder with no data source. crsreports.congress.gov has no RSS or API.

**Analysis:**
- Official CRS site (crsreports.congress.gov) requires search, no programmatic access
- everycrsreport.com provides RSS feed at `/rss.xml` with 25 recent items
- Feed lacks content/description, only metadata (title, link, pubDate)
- Need to filter for VA-related reports

**Decision:** Use everycrsreport.com RSS with keyword filter (veteran, VA, GI Bill, TRICARE, VHA, VBA).

**Result:** Agent configured. 0 VA reports in current feed (expected - CRS covers many topics).

**Files:** `src/oversight/agents/crs.py` (rewritten)

---

## 2026-01-21: Agenda drift minimum utterance length (100 chars)

**Context:** Agenda drift detection was flagging 15 deviations, but 87% were short procedural statements (greetings, "yield back", brief responses like "I would have to get that for the record").

**Analysis:**
- 13 of 15 flagged utterances were < 100 characters
- Short statements naturally cluster differently than substantive policy statements
- They're not agenda drift - they're just brief

**Decision:** Filter out utterances < 100 characters from both baseline building and deviation detection.

**Result:**
- Deviations reduced from 15 to 9
- Substantive detection rate improved from 13% to 56%
- Some procedural noise remains (greetings just over 100 chars, "yield back" phrases)

**Future consideration:** Could add keyword filtering for procedural phrases, but 100-char filter is sufficient for now.

**Files:** `src/db.py`, `src/run_agenda_drift.py`
