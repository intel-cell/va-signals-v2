#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/xa/Work_VC/va-signals-v2"
LOG_DIR="$HOME/Library/Logs/va-signals"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./install_cron_macos.sh [--repo-dir PATH] [--log-dir PATH] [--dry-run]

Defaults:
  --repo-dir /Users/xa/Work_VC/va-signals-v2
  --log-dir  $HOME/Library/Logs/va-signals
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="$2"
      shift 2
      ;;
    --log-dir)
      LOG_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$LOG_DIR"

NEWSYSLOG_CONF="/etc/newsyslog.d/va-signals.conf"
NEWSYSLOG_CONTENT=$(cat <<EOF
${LOG_DIR}/fr-delta.log    640 14 5120 * Z
${LOG_DIR}/ecfr-delta.log  640 14 5120 * Z
${LOG_DIR}/bills.log       640 14 5120 * Z
${LOG_DIR}/hearings.log    640 14 5120 * Z
${LOG_DIR}/oversight.log   640 14 5120 * Z
${LOG_DIR}/state.log       640 14 5120 * Z
EOF
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Would write newsyslog config to $NEWSYSLOG_CONF"
  echo "$NEWSYSLOG_CONTENT"
else
  if [[ -w /etc/newsyslog.d ]]; then
    printf "%s\n" "$NEWSYSLOG_CONTENT" > "$NEWSYSLOG_CONF"
  else
    printf "%s\n" "$NEWSYSLOG_CONTENT" | sudo tee "$NEWSYSLOG_CONF" >/dev/null
  fi
fi

export REPO_DIR LOG_DIR DRY_RUN
python3 - <<'PY'
import os
import re
import subprocess

repo_dir = os.environ["REPO_DIR"]
log_dir = os.environ["LOG_DIR"]
dry_run = os.environ.get("DRY_RUN") == "1"

def read_crontab() -> list[str]:
    try:
        return subprocess.check_output(["crontab", "-l"], text=True).splitlines()
    except subprocess.CalledProcessError:
        return []

existing = read_crontab()
headers = {
    "# VA Signals - 6am runs",
    "# VA Signals - 6pm runs",
    "# VA Signals - Oversight/State",
}
patterns = [
    r"make fr-delta",
    r"make ecfr-delta",
    r"make bills",
    r"make hearings",
    r"src\.run_oversight",
    r"state-monitor-morning",
    r"state-monitor-evening",
]

filtered = []
for line in existing:
    if line.strip() in headers:
        continue
    if any(re.search(pat, line) for pat in patterns):
        continue
    filtered.append(line)

while filtered and filtered[-1].strip() == "":
    filtered.pop()

new_block = [
    "# VA Signals - 6am runs",
    f'0 6 * * * cd "{repo_dir}" && make fr-delta >> "{log_dir}/fr-delta.log" 2>&1',
    f'5 6 * * * cd "{repo_dir}" && make ecfr-delta >> "{log_dir}/ecfr-delta.log" 2>&1',
    f'10 6 * * * cd "{repo_dir}" && make bills >> "{log_dir}/bills.log" 2>&1',
    f'15 6 * * * cd "{repo_dir}" && make hearings >> "{log_dir}/hearings.log" 2>&1',
    "",
    "# VA Signals - 6pm runs",
    f'0 18 * * * cd "{repo_dir}" && make fr-delta >> "{log_dir}/fr-delta.log" 2>&1',
    f'5 18 * * * cd "{repo_dir}" && make ecfr-delta >> "{log_dir}/ecfr-delta.log" 2>&1',
    f'10 18 * * * cd "{repo_dir}" && make bills >> "{log_dir}/bills.log" 2>&1',
    f'15 18 * * * cd "{repo_dir}" && make hearings >> "{log_dir}/hearings.log" 2>&1',
    "",
    "# VA Signals - Oversight/State",
    f'20 6 * * * cd "{repo_dir}" && ./.venv/bin/python -m src.run_oversight --all >> "{log_dir}/oversight.log" 2>&1',
    f'25 6 * * * cd "{repo_dir}" && make state-monitor-morning >> "{log_dir}/state.log" 2>&1',
    f'20 18 * * * cd "{repo_dir}" && ./.venv/bin/python -m src.run_oversight --all >> "{log_dir}/oversight.log" 2>&1',
    f'25 18 * * * cd "{repo_dir}" && make state-monitor-evening >> "{log_dir}/state.log" 2>&1',
]

new_cron = filtered + [""] + new_block if filtered else new_block
cron_text = "\n".join(new_cron) + "\n"

if dry_run:
    print("Would update crontab to:\n")
    print(cron_text)
else:
    subprocess.run(["crontab", "-"], input=cron_text, text=True, check=True)
    print("Updated crontab.")
PY
