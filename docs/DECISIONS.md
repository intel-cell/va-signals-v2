# Architecture Decision Records

This document records significant architectural decisions for the VA Signals project.

---

## ADR-001: Remove Slack Integration, Use Email-Only Notifications

**Date:** 2026-02-04

**Status:** Accepted

**Context:**
The VA Signals system originally used Slack as the primary notification channel for alerts (new documents, errors, escalations, state intelligence alerts). This required:
- A Slack workspace with bot token configuration
- `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` environment variables
- Maintenance of Slack-specific formatting code

**Decision:**
Remove all Slack integration and use email as the sole notification channel.

**Rationale:**
1. **Simplified infrastructure**: Email requires only SMTP credentials, no third-party workspace setup
2. **Reduced dependencies**: Fewer external services to maintain and monitor
3. **Better accessibility**: Email is universally accessible without requiring Slack workspace membership
4. **Audit trail**: Email provides built-in archival and searchability
5. **Cost reduction**: No Slack workspace fees or API rate limits to manage

**Consequences:**

### Removed Components
- `src/notify_slack.py` - Slack notification module
- `src/signals/output/slack.py` - Signals routing Slack formatter
- `tests/test_notify_slack_format.py` - Slack formatting tests
- `tests/signals/test_output/test_slack.py` - Signals Slack output tests

### Modified Components
- `src/run_fr_delta.py` - Uses `notify_email` instead of `notify_slack`
- `src/run_bills.py` - Uses `notify_email` for error alerts
- `src/run_hearings.py` - Uses `notify_email` for error alerts
- `src/run_ecfr_delta.py` - Uses `notify_email` for error alerts
- `src/run_signals.py` - Removed Slack alert sending, logs instead
- `src/state/runner.py` - Uses `notify_email` for high-severity alerts
- `src/oversight/output/formatters.py` - Removed Slack-specific formatters
- `src/signals/output/__init__.py` - Removed Slack exports
- `.github/workflows/daily_fr_delta.yml` - Uses email secrets instead of Slack

### Configuration Changes
- `.env.cron` - Removed Slack config, email config only
- Required secrets changed from `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` to:
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`

### Documentation Updates
- `CLAUDE.md` - Updated module list and alerting description
- `README.md` - Updated secrets section and module descriptions
- `docs/ops/runbook.md` - Updated troubleshooting and configuration

**Migration Notes:**
For existing deployments:
1. Remove `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` from GitHub Actions secrets
2. Add email secrets: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`
3. For Gmail, create an App Password at https://myaccount.google.com/apppasswords

---
