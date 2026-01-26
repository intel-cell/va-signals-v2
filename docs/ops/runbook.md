# VA Signals Runbook

## Purpose & Scope
- Enable any employee to operate and troubleshoot VA Signals reliably.
- Provide decision-support and risk awareness across VA-relevant federal, oversight, and state signals.
- Current baseline is a local macOS runtime (cron, local SQLite, and dashboard).
- This is a stepping-stone to a hosted MVP with company-wide access; hosting/auth are out of scope here.
- Non-negotiable: no demo or mock data in runtime paths.
- Success means runs are repeatable, observable, and recoverable when failures occur.

## Prerequisites
- macOS host with cron and newsyslog available.
- Python 3.x installed (used by `make init` to create `.venv`).
- Ability to run `sudo` to install the newsyslog config.
- Network access to upstream sources and APIs.

## Quick Start
1) From repo root, install dependencies:
   - `make init`
2) Initialize the local SQLite schema (first run only):
   - `make db-init`
3) Start the dashboard:
   - `make dashboard`
4) If port 8000 is busy:
   - `PORT=8001 make dashboard`
5) Open the UI:
   - `http://localhost:8000` (or your chosen port)
6) Stop the server with Ctrl+C.

Keychain prerequisites (macOS):
- `claude-api` (Anthropic key for summarization)
- `congress-api` (Congress.gov key for bills/transcripts)

To add keys:
- `security add-generic-password -s "claude-api" -a "$USER" -w "<API_KEY>"`
- `security add-generic-password -s "congress-api" -a "$USER" -w "<API_KEY>"`

## Scheduling & Logs
### Schedule (cron)
Runs twice daily at 6:00 and 18:00 local time, in 5‑minute offsets to reduce overlap.
Replace `/path/to/va-signals` and `/path/to/logs/va-signals` with absolute paths.

```cron
# VA Signals - 6am runs
0 6 * * * cd "/path/to/va-signals" && make fr-delta >> "/path/to/logs/va-signals/fr-delta.log" 2>&1
5 6 * * * cd "/path/to/va-signals" && make ecfr-delta >> "/path/to/logs/va-signals/ecfr-delta.log" 2>&1
10 6 * * * cd "/path/to/va-signals" && make bills >> "/path/to/logs/va-signals/bills.log" 2>&1
15 6 * * * cd "/path/to/va-signals" && make hearings >> "/path/to/logs/va-signals/hearings.log" 2>&1

# VA Signals - 6pm runs
0 18 * * * cd "/path/to/va-signals" && make fr-delta >> "/path/to/logs/va-signals/fr-delta.log" 2>&1
5 18 * * * cd "/path/to/va-signals" && make ecfr-delta >> "/path/to/logs/va-signals/ecfr-delta.log" 2>&1
10 18 * * * cd "/path/to/va-signals" && make bills >> "/path/to/logs/va-signals/bills.log" 2>&1
15 18 * * * cd "/path/to/va-signals" && make hearings >> "/path/to/logs/va-signals/hearings.log" 2>&1

# VA Signals - Oversight/State
20 6 * * * cd "/path/to/va-signals" && ./.venv/bin/python -m src.run_oversight --all >> "/path/to/logs/va-signals/oversight.log" 2>&1
25 6 * * * cd "/path/to/va-signals" && make state-monitor-morning >> "/path/to/logs/va-signals/state.log" 2>&1
20 18 * * * cd "/path/to/va-signals" && ./.venv/bin/python -m src.run_oversight --all >> "/path/to/logs/va-signals/oversight.log" 2>&1
25 18 * * * cd "/path/to/va-signals" && make state-monitor-evening >> "/path/to/logs/va-signals/state.log" 2>&1
```

### Log directory
```bash
mkdir -p "$HOME/Library/Logs/va-signals"
```
If you use the helper script, this is the default log directory.

### Log rotation (newsyslog)
Use the same log directory path you configured above.
```bash
sudo tee /etc/newsyslog.d/va-signals.conf >/dev/null <<'EOF'
/path/to/logs/va-signals/fr-delta.log    640 14 5120 * Z
/path/to/logs/va-signals/ecfr-delta.log  640 14 5120 * Z
/path/to/logs/va-signals/bills.log       640 14 5120 * Z
/path/to/logs/va-signals/hearings.log    640 14 5120 * Z
/path/to/logs/va-signals/oversight.log   640 14 5120 * Z
/path/to/logs/va-signals/state.log       640 14 5120 * Z
EOF
```

### Helper script
```bash
./install_cron_macos.sh --repo-dir "/path/to/va-signals" --log-dir "$HOME/Library/Logs/va-signals"
```
The script creates the log directory, writes the newsyslog config, and updates
crontab. It will prompt for `sudo` once if needed.

### Verify
```bash
crontab -l
sudo newsyslog -n
ls -l "$HOME/Library/Logs/va-signals"
```

### Notes
- The Mac must be awake at schedule time or cron jobs will be skipped.
- Legacy logging to `/tmp/va-signals-cron.log` is deprecated in favor of per‑pipeline logs.
- Cron uses local time; confirm the machine time zone is correct.
- If a job runs long, the next job may overlap; check logs for duration.

## Pipelines & Data Flow
- Data flow: External sources → fetch/run modules → SQLite (`data/signals.db`) → dashboard + Slack.
- Scheduling is twice daily via cron (see Scheduling & Logs).

### Pipelines (commands)
- Federal Register: `make fr-delta`
- eCFR Title 38: `make ecfr-delta`
- VA Bills: `make bills`
- Hearings: `make hearings`
- Oversight Monitor (all agents): `./.venv/bin/python -m src.run_oversight --all`
- State Intelligence: `make state-monitor-morning` / `make state-monitor-evening`

### Run status meanings
- `SUCCESS`: new data found and processed
- `NO_DATA`: source checked, nothing new
- `ERROR`: failure occurred (alerts)

### Oversight pipeline stages
Raw events → quality gate → deduplication → escalation/deviation checks → `om_events`

### State sources (default)
- TX: TVC News, Texas Register, RSS, NewsAPI
- CA: CalVet Newsroom, OAL Notice Register, RSS, NewsAPI
- FL: Florida DVA News, Florida Administrative Register, RSS, NewsAPI

### Key tables
- `source_runs` (all runs), `fr_seen`, `ecfr_seen`
- `om_events` (oversight), `state_signals` + `state_runs`

## Dashboard & APIs
- Dashboard: `http://localhost:8000` (or your configured port).
- Tabs: Federal, Oversight, State — all data is read from SQLite.
- Auto‑refreshes every 60s; reload the page if UI feels stale.
- Errors: click “View” in Recent Runs to inspect error details.
- Remote access requires hosting + auth (planned for MVP).

### Key API endpoints
- `/api/runs`, `/api/runs/stats`
- `/api/documents/fr`, `/api/documents/ecfr`
- `/api/errors`, `/api/summaries`
- `/api/oversight/stats`, `/api/oversight/events`
- `/api/state/stats`, `/api/state/signals`, `/api/state/runs`

## Troubleshooting & Known Issues
### Port already in use
- Symptom: `Address already in use` when starting dashboard.
- Fix: `PORT=8001 make dashboard` or stop the process:
  - `lsof -i :8000` then `kill <PID>`

### Missing API keys (Keychain)
- Symptom: failures when running summarization or Congress.gov fetches.
- Check: `security find-generic-password -s "claude-api" -a "$USER" -w`
  and `security find-generic-password -s "congress-api" -a "$USER" -w`
- Fix: add the missing Keychain entry.

### DB schema missing / tables not found
- Symptom: API errors mentioning missing tables.
- Fix: `make db-init`

### Cron jobs not running
- Symptom: no fresh runs, logs stale.
- Check: Mac sleep or closed lid; verify `crontab -l`.
- Fix: keep Mac awake at schedule time or run manually.

### Oversight tab empty
- Symptom: Oversight shows no events.
- Check: has `run_oversight` executed?
- Fix: run `./.venv/bin/python -m src.run_oversight --all`.

### Slack alerts failing
- Symptom: jobs run but no Slack alerts on ERROR/NEW_DOCS.
- Check: `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` (GitHub Actions or local env).
  For local cron, export these in the crontab or run jobs in a wrapper script.

### Network/API failures
- Symptom: timeouts/5xx from upstream sources.
- Fix: retry later; confirm network access and rate limits.

### Logs not rotating
- Symptom: logs grow indefinitely.
- Check: `sudo newsyslog -n` and verify `/etc/newsyslog.d/va-signals.conf`.

## Recovery / Reset
### Restart dashboard
- Stop: Ctrl+C
- Start: `make dashboard`

### Reset SQLite DB (destructive)
- Remove DB: `rm -f data/signals.db`
- Recreate schema: `make db-init`
- Note: this clears historical runs and documents.

### Rerun pipelines manually
- Federal: `make fr-delta`, `make ecfr-delta`, `make bills`, `make hearings`
- Oversight: `./.venv/bin/python -m src.run_oversight --all`
- State: `make state-monitor-morning` / `make state-monitor-evening`

### Logs and scheduling reset
- Clear logs manually if needed: `> ~/Library/Logs/va-signals/<file>.log`
- Reapply cron/newsyslog using `install_cron_macos.sh` (or manual steps)

## Ownership / Next Steps
This runbook covers the current local operational baseline. The next milestone is
company‑wide access via hosted infrastructure and user authentication.

Next steps (post‑runbook):
- Choose hosting target (cloud VM vs container).
- Define auth model (SSO/IdP) and roles (leadership vs employees).
- Plan centralized logs/monitoring and alert routing.
- Document secret management and rotation policy.
- Assign interim owners for cron, Keychain/API keys, and dashboard uptime.
