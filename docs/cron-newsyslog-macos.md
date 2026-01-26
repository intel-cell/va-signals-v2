# macOS cron + newsyslog setup

This document sets up local scheduling and log rotation on macOS without
changing runtime behavior. The same commands run on the same cadence; only the
log location and rotation policy change.

## Prerequisites

- Repo checked out and initialized: `make init`
- Mac is awake at 06:00/18:00 local time
- Update the repo path in examples if yours differs from:
  `/Users/xa/Work_VC/va-signals-v2`

## 1) Create log directory

```bash
mkdir -p "$HOME/Library/Logs/va-signals"
```

## 2) Install newsyslog config (requires sudo)

Create `/etc/newsyslog.d/va-signals.conf` to rotate logs (14 files, 5MB each,
compressed):

```bash
sudo tee /etc/newsyslog.d/va-signals.conf >/dev/null <<'EOF'
/Users/xa/Library/Logs/va-signals/fr-delta.log    640 14 5120 * Z
/Users/xa/Library/Logs/va-signals/ecfr-delta.log  640 14 5120 * Z
/Users/xa/Library/Logs/va-signals/bills.log       640 14 5120 * Z
/Users/xa/Library/Logs/va-signals/hearings.log    640 14 5120 * Z
/Users/xa/Library/Logs/va-signals/oversight.log   640 14 5120 * Z
/Users/xa/Library/Logs/va-signals/state.log       640 14 5120 * Z
EOF
```

If your home directory differs, update the paths accordingly.

## 3) Update crontab

Edit your crontab and set per-pipeline logs:

```bash
crontab -e
```

Paste this block (update the repo path if needed):

```cron
# VA Signals - 6am runs
0 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make fr-delta >> "/Users/xa/Library/Logs/va-signals/fr-delta.log" 2>&1
5 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make ecfr-delta >> "/Users/xa/Library/Logs/va-signals/ecfr-delta.log" 2>&1
10 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make bills >> "/Users/xa/Library/Logs/va-signals/bills.log" 2>&1
15 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make hearings >> "/Users/xa/Library/Logs/va-signals/hearings.log" 2>&1

# VA Signals - 6pm runs
0 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make fr-delta >> "/Users/xa/Library/Logs/va-signals/fr-delta.log" 2>&1
5 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make ecfr-delta >> "/Users/xa/Library/Logs/va-signals/ecfr-delta.log" 2>&1
10 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make bills >> "/Users/xa/Library/Logs/va-signals/bills.log" 2>&1
15 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make hearings >> "/Users/xa/Library/Logs/va-signals/hearings.log" 2>&1

# VA Signals - Oversight/State
20 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && ./.venv/bin/python -m src.run_oversight --all >> "/Users/xa/Library/Logs/va-signals/oversight.log" 2>&1
25 6 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make state-monitor-morning >> "/Users/xa/Library/Logs/va-signals/state.log" 2>&1
20 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && ./.venv/bin/python -m src.run_oversight --all >> "/Users/xa/Library/Logs/va-signals/oversight.log" 2>&1
25 18 * * * cd "/Users/xa/Work_VC/va-signals-v2" && make state-monitor-evening >> "/Users/xa/Library/Logs/va-signals/state.log" 2>&1
```

## 4) Verify

```bash
sudo newsyslog -n
crontab -l
ls -l "$HOME/Library/Logs/va-signals"
```

## Optional: one-shot manual run

```bash
cd "/Users/xa/Work_VC/va-signals-v2"
make fr-delta
make ecfr-delta
make bills
make hearings
./.venv/bin/python -m src.run_oversight --all
make state-monitor-morning
```

## Optional script

Use `install_cron_macos.sh` at the repo root to automate the steps:

```bash
./install_cron_macos.sh --repo-dir "/Users/xa/Work_VC/va-signals-v2" --log-dir "$HOME/Library/Logs/va-signals"
```

For a dry run:

```bash
./install_cron_macos.sh --dry-run
```

## Future migration (Linux/systemd/Docker)

- **Linux**: replace cron with systemd timers or cron, and replace newsyslog
  with logrotate.
- **Docker**: use CronJobs (K8s) or a scheduler container, and ship logs to a
  centralized logger (CloudWatch/ELK/etc.).
- **Config parity**: keep the same cadence and command list; only the scheduler
  and log rotation mechanism change.
