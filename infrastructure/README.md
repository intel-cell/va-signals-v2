# VA Signals Infrastructure

## Command Dashboard Deployment

This directory contains infrastructure configuration and deployment runbooks
for the VA Signals Command Dashboard at `cmd.veteran-signals.com`.

## Contents

- `deploy-cloud-run.sh` - Deploy to Cloud Run
- `configure-dns-ssl.sh` - DNS and SSL certificate setup
- `configure-secrets.sh` - Secret Manager configuration
- `configure-monitoring.sh` - Uptime checks and alerting
- `RUNBOOK_ROLLBACK.md` - Rollback procedures

## Quick Start

```bash
# 1. Set project
export PROJECT_ID=va-signals-v2
gcloud config set project $PROJECT_ID

# 2. Deploy to Cloud Run
./infrastructure/deploy-cloud-run.sh

# 3. Configure DNS and SSL (if new domain)
./infrastructure/configure-dns-ssl.sh

# 4. Configure secrets
./infrastructure/configure-secrets.sh

# 5. Set up monitoring
./infrastructure/configure-monitoring.sh
```

## Architecture

```
                    ┌─────────────────────────┐
                    │   Cloud Load Balancer   │
                    │   (Global HTTPS LB)     │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │ Cloud Armor    │ │ SSL Certs      │ │ IAP            │
     │ (WAF)          │ │ (Managed)      │ │ (Fallback)     │
     └────────────────┘ └────────────────┘ └────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
          ┌─────────────────┐     ┌─────────────────┐
          │ app.veteran-    │     │ cmd.veteran-    │
          │ signals.com     │     │ signals.com     │
          │ (existing)      │     │ (new - command) │
          └────────┬────────┘     └────────┬────────┘
                   │                       │
                   └───────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Cloud Run         │
                    │   va-signals-       │
                    │   dashboard         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │ Cloud SQL      │ │ Secret Manager │ │ Cloud Storage  │
     │ (PostgreSQL)   │ │ (Auth Secrets) │ │ (Assets)       │
     └────────────────┘ └────────────────┘ └────────────────┘
```

## Domains

| Domain | Purpose | Status |
|--------|---------|--------|
| app.veteran-signals.com | Original dashboard | Active |
| cmd.veteran-signals.com | Command dashboard | Deploying |

## Secrets Required

| Secret Name | Description | Used By |
|-------------|-------------|---------|
| FIREBASE_ADMIN_SDK_KEY | Firebase Admin SDK credentials | Auth middleware |
| SESSION_SECRET | HMAC key for session tokens | Session management |
| CSRF_SECRET | CSRF token generation key | CSRF protection |

## Monitoring

- Uptime check: `/health` endpoint every 60s
- Alert policy: Downtime > 1 minute
- Error rate alert: > 5% in 5 minute window
- Latency alert: p95 > 2s

## Contact

- **Project Lead:** Xavier Aguiar (Commander)
- **Infrastructure:** GOLF COMMAND
- **Auth:** ECHO COMMAND
