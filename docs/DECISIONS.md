# Decision Log

Architecture and implementation decisions with rationale. Newest first.

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
