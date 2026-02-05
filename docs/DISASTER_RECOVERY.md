# Disaster Recovery Procedures

## VA Signals v2 - Business Continuity & Disaster Recovery

**Last Updated:** 2026-02-05
**Owner:** Xavier Aguiar, Commander
**Review Frequency:** Quarterly

---

## Table of Contents

1. [Overview](#overview)
2. [Recovery Objectives](#recovery-objectives)
3. [Backup Strategy](#backup-strategy)
4. [Incident Classification](#incident-classification)
5. [Recovery Procedures](#recovery-procedures)
6. [Contact Information](#contact-information)
7. [Testing Schedule](#testing-schedule)

---

## Overview

This document outlines the disaster recovery (DR) procedures for the VA Signals v2 intelligence platform. It covers data backup, system recovery, and business continuity measures.

### Scope

- **Cloud Run Services:** Dashboard API, WebSocket server
- **Cloud SQL Database:** PostgreSQL primary database
- **Cloud Storage:** Document archives, backups
- **GitHub Repository:** Source code, configurations
- **External Dependencies:** Federal Register API, Congress.gov API

### Infrastructure Summary

| Component | Provider | Region | Redundancy |
|-----------|----------|--------|------------|
| Dashboard API | Cloud Run | us-central1 | Multi-zone |
| Database | Cloud SQL | us-central1 | HA with failover |
| Storage | Cloud Storage | us-central1 | Multi-region |
| Source Code | GitHub | Global | Geo-distributed |

---

## Recovery Objectives

### Recovery Time Objective (RTO)

| Priority | Service | RTO Target |
|----------|---------|------------|
| Critical | Dashboard API | 15 minutes |
| Critical | Database | 30 minutes |
| High | Background Jobs | 2 hours |
| Medium | Historical Data | 24 hours |
| Low | Analytics/Reports | 48 hours |

### Recovery Point Objective (RPO)

| Data Type | RPO Target | Backup Frequency |
|-----------|------------|------------------|
| Database (PostgreSQL) | 1 hour | Continuous + hourly |
| Configuration | Real-time | On change (Git) |
| Audit Logs | 15 minutes | Continuous replication |
| Document Archives | 24 hours | Daily |

---

## Backup Strategy

### Database Backups

#### Automated Backups (Cloud SQL)

Cloud SQL provides:
- **Automated daily backups** with 7-day retention
- **Point-in-time recovery** up to 7 days
- **Binary logging** for continuous backup

#### Manual Backup Script

```bash
# Run manual backup
./infrastructure/backup-database.sh

# Backup to specific location
./infrastructure/backup-database.sh --output gs://va-signals-backups/manual/

# Verify backup
./infrastructure/backup-database.sh --verify
```

#### Backup Schedule

| Type | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| Automated (Cloud SQL) | Daily | 7 days | Cloud SQL |
| Hourly Snapshot | Every hour | 24 hours | GCS |
| Daily Archive | Daily 2am UTC | 30 days | GCS |
| Weekly Archive | Sunday 3am UTC | 90 days | GCS |
| Monthly Archive | 1st of month | 1 year | GCS (Nearline) |

### Configuration Backups

All configuration is version-controlled in GitHub:
- Infrastructure as Code (Terraform)
- Kubernetes/Cloud Run manifests
- Environment configurations
- Schema definitions

### External Data Sources

| Source | Backup Method | Frequency |
|--------|---------------|-----------|
| Federal Register | Local cache | On fetch |
| Congress.gov | Local cache | On fetch |
| State sources | Local cache | On fetch |

---

## Incident Classification

### Severity Levels

| Level | Description | Examples | Response Time |
|-------|-------------|----------|---------------|
| SEV-1 | Complete outage | Database down, API unreachable | Immediate |
| SEV-2 | Major degradation | Slow response, partial data loss | 15 minutes |
| SEV-3 | Minor impact | Single job failure, UI glitch | 1 hour |
| SEV-4 | Low impact | Non-critical feature unavailable | 24 hours |

### Escalation Matrix

```
SEV-1 → Commander + On-call Engineer (immediate page)
SEV-2 → On-call Engineer (immediate page)
SEV-3 → On-call Engineer (notification)
SEV-4 → Regular business hours
```

---

## Recovery Procedures

### Procedure 1: Database Recovery

#### 1.1 Point-in-Time Recovery (Cloud SQL)

```bash
# List available recovery points
gcloud sql instances describe va-signals-db --format="get(backupConfiguration)"

# Restore to specific point in time
gcloud sql instances clone va-signals-db va-signals-db-restored \
  --point-in-time="2026-02-05T10:00:00.000Z"

# Verify restored instance
gcloud sql connect va-signals-db-restored --user=postgres

# Swap instances (after verification)
gcloud sql instances patch va-signals-db --activation-policy=NEVER
gcloud sql instances patch va-signals-db-restored --display-name=va-signals-db
```

#### 1.2 Restore from Manual Backup

```bash
# Download backup from GCS
gsutil cp gs://va-signals-backups/daily/2026-02-05.sql.gz ./

# Decompress
gunzip 2026-02-05.sql.gz

# Restore to database
./infrastructure/restore-database.sh 2026-02-05.sql

# Verify data integrity
psql -c "SELECT COUNT(*) FROM fr_seen;"
psql -c "SELECT MAX(ended_at) FROM source_runs;"
```

### Procedure 2: Cloud Run Service Recovery

#### 2.1 Redeploy from Latest Image

```bash
# Get current revision
gcloud run services describe va-signals-dashboard --region us-central1

# Redeploy from latest
gcloud run deploy va-signals-dashboard \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/veteran-signals/va-signals/dashboard:latest

# Verify deployment
curl https://va-signals-dashboard-595196122440.us-central1.run.app/health
```

#### 2.2 Rollback to Previous Revision

```bash
# List revisions
gcloud run revisions list --service va-signals-dashboard --region us-central1

# Route traffic to previous revision
gcloud run services update-traffic va-signals-dashboard \
  --region us-central1 \
  --to-revisions va-signals-dashboard-00014-abc=100
```

#### 2.3 Rebuild from Source

```bash
# Clone repository
git clone https://github.com/intel-cell/va-signals-v2.git
cd va-signals-v2

# Build and push image
docker build --platform linux/amd64 -t us-central1-docker.pkg.dev/veteran-signals/va-signals/dashboard:recovery .
docker push us-central1-docker.pkg.dev/veteran-signals/va-signals/dashboard:recovery

# Deploy recovery image
gcloud run deploy va-signals-dashboard \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/veteran-signals/va-signals/dashboard:recovery
```

### Procedure 3: Complete Infrastructure Recreation

#### 3.1 Prerequisites

- GCP Project access
- GitHub repository access
- Environment secrets

#### 3.2 Step-by-Step Recreation

```bash
# 1. Clone repository
git clone https://github.com/intel-cell/va-signals-v2.git
cd va-signals-v2

# 2. Create Cloud SQL instance
gcloud sql instances create va-signals-db-new \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-auto-increase \
  --backup-start-time=02:00

# 3. Restore database from backup
./infrastructure/restore-database.sh gs://va-signals-backups/daily/latest.sql.gz

# 4. Deploy Cloud Run service
gcloud run deploy va-signals-dashboard \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --add-cloudsql-instances veteran-signals:us-central1:va-signals-db-new \
  --set-env-vars "DATABASE_URL=..."

# 5. Create Cloud Run jobs
for job in fr-delta bills hearings oversight state-monitor; do
  gcloud run jobs create $job --source . --region us-central1
done

# 6. Configure scheduler
gcloud scheduler jobs create http daily-sync \
  --schedule="0 6 * * *" \
  --uri="https://va-signals-dashboard-xxx.run.app/api/sync"

# 7. Verify all services
./scripts/verify-deployment.sh
```

### Procedure 4: Data Corruption Recovery

#### 4.1 Identify Corruption

```sql
-- Check for anomalies
SELECT source_id, COUNT(*) as runs, MAX(ended_at) as latest
FROM source_runs
GROUP BY source_id
ORDER BY latest DESC;

-- Check data integrity
SELECT 'fr_seen' as tbl, COUNT(*) FROM fr_seen
UNION ALL
SELECT 'source_runs', COUNT(*) FROM source_runs
UNION ALL
SELECT 'bf_vehicles', COUNT(*) FROM bf_vehicles;
```

#### 4.2 Selective Restore

```bash
# Export specific table from backup
pg_restore --table=corrupted_table backup.dump > table_restore.sql

# Review restoration script
cat table_restore.sql | head -50

# Apply to production (after backup!)
psql -f table_restore.sql
```

### Procedure 5: External API Failure

#### 5.1 Federal Register API Unavailable

```bash
# Check API status
curl -I https://www.federalregister.gov/api/v1/documents

# If unavailable, enable cached mode
gcloud run services update va-signals-dashboard \
  --set-env-vars "FR_API_CACHE_ONLY=true"

# Monitor for recovery
watch -n 60 'curl -s -o /dev/null -w "%{http_code}" https://www.federalregister.gov/api/v1/documents'
```

#### 5.2 Congress.gov API Unavailable

Similar procedure with `CONGRESS_API_CACHE_ONLY=true`

---

## Contact Information

### Primary Contacts

| Role | Name | Contact | Availability |
|------|------|---------|--------------|
| Commander | Xavier Aguiar | xavier@vetclaims.ai | 24/7 |
| On-Call Engineer | TBD | oncall@vetclaims.ai | Rotation |

### External Support

| Service | Support Contact | SLA |
|---------|-----------------|-----|
| Google Cloud | cloud.google.com/support | 15 min (P1) |
| GitHub | support.github.com | 24 hours |

### Communication Channels

- **Incident Channel:** #va-signals-incidents (Slack)
- **Status Page:** status.vetclaims.ai
- **Email Updates:** alerts@vetclaims.ai

---

## Testing Schedule

### Monthly Tests

- [ ] Backup restoration test (random sample)
- [ ] Cloud Run rollback test
- [ ] Alert notification test

### Quarterly Tests

- [ ] Full database restoration
- [ ] Complete service recreation
- [ ] Runbook walkthrough with team
- [ ] Update contact information

### Annual Tests

- [ ] Full DR simulation
- [ ] Multi-region failover (if applicable)
- [ ] Documentation review and update

---

## Runbook Checklist

### Pre-Incident Preparation

- [ ] Verify backup status in GCS
- [ ] Confirm on-call contacts are current
- [ ] Test monitoring alerts are functioning
- [ ] Review recent changes in deployment log

### During Incident

- [ ] Acknowledge incident in tracking system
- [ ] Assess severity and classify
- [ ] Notify stakeholders per escalation matrix
- [ ] Document all actions taken
- [ ] Implement recovery procedure
- [ ] Verify service restoration
- [ ] Update status page

### Post-Incident

- [ ] Conduct post-mortem within 48 hours
- [ ] Document root cause
- [ ] Identify preventive measures
- [ ] Update runbooks if needed
- [ ] Schedule follow-up items

---

## Appendix

### A. Recovery Commands Quick Reference

```bash
# Database
gcloud sql instances clone SOURCE TARGET --point-in-time="TIME"
./infrastructure/restore-database.sh BACKUP_FILE

# Cloud Run
gcloud run services update-traffic SERVICE --to-revisions REV=100
gcloud run deploy SERVICE --image IMAGE

# Monitoring
gcloud logging read "resource.type=cloud_run_revision" --limit=50
gcloud monitoring dashboards list
```

### B. Important URLs

- Dashboard: https://va-signals-dashboard-595196122440.us-central1.run.app
- GCP Console: https://console.cloud.google.com/run?project=veteran-signals
- GitHub: https://github.com/intel-cell/va-signals-v2
- Backup Bucket: gs://va-signals-backups/

### C. Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-02-05 | 1.0 | Initial document | Xavier Aguiar |
