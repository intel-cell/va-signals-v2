# Rollback Runbook - VA Signals Command Dashboard

## GOLF COMMAND - Operation COMMAND POST

This runbook documents emergency procedures for rolling back the Command Dashboard.

---

## Quick Reference

| Scenario | Action | Command |
|----------|--------|---------|
| Bad deployment | Rollback Cloud Run | `gcloud run services update-traffic ... --to-revisions=PREVIOUS=100` |
| Auth broken | Disable auth | Set `AUTH_ENABLED=false` env var |
| DNS issue | Revert to app.* | Remove cmd.* host rule from LB |
| SSL issue | Use HTTP (temp) | Disable HTTPS redirect |

---

## 1. Cloud Run Rollback

### View Available Revisions

```bash
gcloud run revisions list \
    --service=va-signals-dashboard \
    --region=us-central1 \
    --format="table(name,active,creationTimestamp)"
```

### Rollback to Previous Revision

```bash
# Get previous revision name
PREVIOUS_REVISION=$(gcloud run revisions list \
    --service=va-signals-dashboard \
    --region=us-central1 \
    --format="value(name)" \
    --sort-by="~creationTimestamp" | sed -n '2p')

# Route 100% traffic to previous revision
gcloud run services update-traffic va-signals-dashboard \
    --region=us-central1 \
    --to-revisions=${PREVIOUS_REVISION}=100

echo "Rolled back to: ${PREVIOUS_REVISION}"
```

### Verify Rollback

```bash
# Check service health
curl -I https://cmd.veteran-signals.com/api/runs/stats

# Check traffic distribution
gcloud run services describe va-signals-dashboard \
    --region=us-central1 \
    --format="yaml(status.traffic)"
```

---

## 2. Authentication Rollback

### Disable Firebase Auth (Keep IAP)

```bash
gcloud run services update va-signals-dashboard \
    --region=us-central1 \
    --update-env-vars="AUTH_ENABLED=false"
```

### Re-enable Basic Auth (Emergency)

In `src/dashboard_api.py`, uncomment:
```python
# app.add_middleware(BasicAuthMiddleware)
```

Then redeploy.

### Verify Auth Status

```bash
# Should return 200 (or 401 if auth working)
curl -I https://cmd.veteran-signals.com/api/auth/me
```

---

## 3. DNS/SSL Rollback

### Remove cmd.* Host Rule

```bash
# Export current URL map
gcloud compute url-maps export va-signals-url-map \
    --global \
    --destination=/tmp/url-map-backup.yaml

# Remove host rule for cmd.veteran-signals.com
gcloud compute url-maps remove-host-rule va-signals-url-map \
    --host=cmd.veteran-signals.com \
    --global
```

### Restore from Backup

```bash
gcloud compute url-maps import va-signals-url-map \
    --global \
    --source=/tmp/url-map-backup.yaml
```

### Temporary: Disable HTTPS (Not Recommended)

Only if SSL certificate is causing issues:
1. Remove cmd.* certificate from HTTPS proxy
2. Users can access via app.veteran-signals.com

---

## 4. Database Rollback

### If Auth Tables Corrupt

```bash
# Connect to Cloud SQL
gcloud sql connect va-signals-db --user=postgres

# Drop and recreate auth tables
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS users;

# Re-run schema
\i /path/to/src/auth/schema.sql
```

### Restore from Backup

```bash
# List backups
gcloud sql backups list --instance=va-signals-db

# Restore (creates new instance)
gcloud sql backups restore BACKUP_ID \
    --restore-instance=va-signals-db \
    --backup-instance=va-signals-db
```

---

## 5. Complete Service Restoration

### Full Reset Procedure

1. **Stop new traffic**
   ```bash
   gcloud run services update va-signals-dashboard \
       --region=us-central1 \
       --no-traffic
   ```

2. **Rollback to known good revision**
   ```bash
   gcloud run services update-traffic va-signals-dashboard \
       --region=us-central1 \
       --to-revisions=va-signals-dashboard-KNOWN_GOOD=100
   ```

3. **Verify restoration**
   ```bash
   curl https://cmd.veteran-signals.com/api/runs/stats
   ```

4. **Monitor for 15 minutes**
   - Check Cloud Run logs
   - Check uptime monitoring
   - Verify no new errors

---

## 6. Emergency Contacts

| Role | Contact | When to Call |
|------|---------|--------------|
| Commander | Xavier Aguiar | Any production incident |
| GCP Support | Console > Support | Cloud infrastructure issues |

---

## 7. Post-Incident

After any rollback:

1. **Document the incident**
   - What happened
   - What was the impact
   - How it was resolved

2. **Submit SITREP**
   - File: `/Intel_Drop/SITREPS/SITREP_GOLF_[date]_EXCEPTION.md`
   - Include: Timeline, actions taken, recommendations

3. **Update runbook**
   - Add any new procedures discovered
   - Improve existing steps

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-04 | GOLF COMMAND | Initial creation |
