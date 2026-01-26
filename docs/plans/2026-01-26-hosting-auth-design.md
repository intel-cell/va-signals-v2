# VA Signals Hosting + Auth (Internal MVP) Design

Date: 2026-01-26

## Goals & Scope
- Internal-only access for vetclaims.ai leadership/employees at `va-signals.vetclaims.ai`.
- Access gated by Google Workspace Groups (e.g., `leadership@vetclaims.ai`, `employees@vetclaims.ai`).
- New dedicated GCP project under the `vetclaims.ai` organization.
- Cloud-native runtime with automated scheduling, centralized logging, and auditable access.
- No public landing page in MVP; public site will be a separate service later.

## Architecture Overview
- **Runtime:** Cloud Run service hosting the FastAPI dashboard + `/api/*` endpoints.
- **Auth:** Identity-Aware Proxy (IAP) in front of Cloud Run; Workspace SSO only.
- **Database:** Cloud SQL (Postgres) for durable storage and concurrency safety.
- **Pipelines:** Cloud Run Jobs (FR, eCFR, bills, hearings, oversight, state).
- **Scheduler:** Cloud Scheduler triggers each job on existing cadence.
- **Secrets:** Secret Manager for Slack token/channel, Congress API, Anthropic key.
- **Logs:** Cloud Logging + Error Reporting; optional alerting in Phase 2.
- **Domain:** Cloud Run domain mapping for `va-signals.vetclaims.ai`.

## Data Migration & Storage
SQLite cannot be used as the primary database on Cloud Run because the filesystem is
ephemeral and not concurrency-safe. The MVP requires a migration to Postgres (Cloud SQL).
We will keep SQLite for local development, but production will use Postgres via
`DATABASE_URL` / Cloud SQL connector. The `schema.sql` file will be split into
SQLite and Postgres variants to avoid dialect conflicts (e.g., `INSERT OR IGNORE`,
`sqlite_master` references, and type defaults). A small migration utility will export
from local SQLite and import into Postgres, preserving existing data where needed
(`source_runs`, `fr_seen`, `bills`, `hearings`, `om_events`, `state_*`).

Migration will be a one-time cutover:
1. Provision Postgres, apply Postgres schema.
2. Export SQLite data to CSV or stream rows in a Python migration script.
3. Import into Postgres with idempotent inserts (`ON CONFLICT DO NOTHING`).
4. Verify row counts per table and smoke-test API endpoints.
5. Freeze SQLite for archival only.

Backups: enable automated daily backups + point-in-time recovery on Cloud SQL.
Retention target: 7-30 days (tune after MVP usage).

## Auth & IAP Configuration
IAP provides Workspace SSO without embedding auth logic in the app. The Cloud Run
service is configured to **deny unauthenticated access**, and IAP grants access
only to Google Groups. We will create or verify two groups:
`leadership@vetclaims.ai` and `employees@vetclaims.ai`. Access will be granted by
assigning the IAM role `IAP-secured Web App User` to those groups on the Cloud Run
resource. The IAP brand and OAuth consent screen will live under the
`vetclaims.ai` organization.

IAP constraints:
- Only Google accounts can authenticate (no public users).
- The app should not expose unauthenticated paths in the same service.
- The public site must be a **separate service/domain** later.

## Operations & Scheduling
Local cron/newsyslog is replaced with:
- Cloud Run Jobs (one per pipeline) using the same container image.
- Cloud Scheduler HTTP triggers with a service account.
- Logs emitted to stdout/stderr and captured by Cloud Logging.

## Future Public Site
The eventual public-facing site should be **separate from the internal app**:
either a different Cloud Run service or a static site on a different subdomain.
This prevents any accidental exposure of internal data and avoids conflicts with
IAP restrictions.

## Assumptions
- Region: `us-central1` unless data residency requires otherwise.
- Workspace domain is already verified and linked to a GCP organization.
- Google Groups for access control exist or can be created.
