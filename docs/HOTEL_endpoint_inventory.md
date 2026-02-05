# API Endpoint Inventory for RBAC Integration
## HOTEL COMMAND - Preparatory Assessment
## DTG: 2026-02-04 2215

================================================================================

## ENDPOINT COUNT SUMMARY

| Module | GET | POST | PATCH | Total |
|--------|-----|------|-------|-------|
| Main Dashboard API | 23 | 0 | 0 | 23 |
| Battlefield Router | 8 | 4 | 1 | 13 |
| **TOTAL** | **31** | **4** | **1** | **36** |

================================================================================

## PROPOSED ROLE-BASED ACCESS CONTROL

### Role Definitions (per OPLAN 002)

| Role | Level | Description |
|------|-------|-------------|
| COMMANDER | 1 | Full access - all read/write, admin functions |
| LEADERSHIP | 2 | Read access + limited write (update vehicle posture) |
| ANALYST | 3 | Read access + report generation |
| VIEWER | 4 | Dashboard read-only |

================================================================================

## ENDPOINT CATEGORIZATION

### PUBLIC (No Auth Required)
- None - all endpoints require authentication

### VIEWER (Level 4) - Read-Only Dashboard
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/runs/stats | GET | System stats overview |
| /api/health | GET | Source health check |
| /api/documents/fr | GET | FR documents list |
| /api/documents/ecfr | GET | eCFR documents list |
| /api/summaries | GET | Document summaries |
| /api/summaries/{doc_id} | GET | Single summary |
| /api/bills | GET | Bills list |
| /api/bills/stats | GET | Bill statistics |
| /api/hearings | GET | Hearings list |
| /api/hearings/stats | GET | Hearing statistics |
| /api/state/signals | GET | State intelligence |
| /api/state/stats | GET | State stats |
| /api/oversight/stats | GET | Oversight stats |
| /api/oversight/events | GET | Oversight events |
| /api/battlefield/stats | GET | Battlefield summary |
| /api/battlefield/vehicles | GET | Vehicle list |
| /api/battlefield/vehicles/{id} | GET | Single vehicle |
| /api/battlefield/calendar | GET | Calendar view |
| /api/battlefield/critical-gates | GET | Critical gates |
| /api/battlefield/dashboard | GET | Full dashboard |

### ANALYST (Level 3) - Read + Reports
| Endpoint | Method | Description |
|----------|--------|-------------|
| *All VIEWER endpoints* | | |
| /api/runs | GET | Detailed run history |
| /api/errors | GET | Error details |
| /api/summaries/check/{id} | GET | Summary existence check |
| /api/summaries/doc-ids | GET | All summarized doc IDs |
| /api/reports/generate | GET | Generate reports |
| /api/agenda-drift/events | GET | AD deviation events |
| /api/agenda-drift/stats | GET | AD statistics |
| /api/agenda-drift/members/{id}/history | GET | Member deviation history |
| /api/state/runs | GET | State run history |
| /api/battlefield/alerts | GET | Alert history |

### LEADERSHIP (Level 2) - Read + Limited Write
| Endpoint | Method | Description |
|----------|--------|-------------|
| *All ANALYST endpoints* | | |
| /api/battlefield/vehicles/{id} | PATCH | Update posture/owner/task |
| /api/battlefield/alerts/{id}/acknowledge | POST | Acknowledge alerts |

### COMMANDER (Level 1) - Full Access
| Endpoint | Method | Description |
|----------|--------|-------------|
| *All LEADERSHIP endpoints* | | |
| /api/battlefield/sync | POST | Trigger full sync |
| /api/battlefield/detect | POST | Run gate detection |
| /api/battlefield/init | POST | Initialize tables |
| /api/audit/* (future) | GET | Audit log access |
| /api/users/* (future) | ALL | User management |

================================================================================

## CURRENT AUTHENTICATION

**Status:** BasicAuthMiddleware is **DISABLED** (line 399 in dashboard_api.py)
**Current Method:** Cloud Run IAP handles authentication externally

**Code Reference:**
```python
# 2. Basic Auth - DISABLED (Cloud Run IAM handles authentication)
# app.add_middleware(BasicAuthMiddleware)
```

================================================================================

## INTEGRATION REQUIREMENTS FROM ECHO

For HOTEL to integrate auth, ECHO must provide:

1. **Auth Middleware**
   - Validates Firebase tokens
   - Extracts user info from token
   - Attaches user to request.state

2. **RBAC Decorators**
   - `@require_role(Role.VIEWER)`
   - `@require_role(Role.ANALYST)`
   - `@require_role(Role.LEADERSHIP)`
   - `@require_role(Role.COMMANDER)`

3. **User Model**
   - email
   - role
   - created_at
   - last_login

4. **Audit Interface**
   - log_action(user, action, resource, result)

================================================================================

## TEST FRAMEWORK STRUCTURE

```
tests/
├── auth/
│   ├── __init__.py
│   ├── conftest.py           # Auth test fixtures
│   ├── test_authentication.py  # Login flows
│   └── test_authorization.py   # RBAC tests
├── integration/
│   ├── __init__.py
│   ├── conftest.py           # Integration fixtures
│   └── test_end_to_end.py    # Full flow tests
└── performance/
    ├── __init__.py
    └── test_load.py          # Performance tests
```

================================================================================

## NOTES

1. Order mentions 48 endpoints; actual count is 36. Difference may include:
   - Static file serving endpoint
   - Future CEO Brief endpoints
   - Future Evidence Pack endpoints
   - Health check endpoints not yet implemented

2. BasicAuthMiddleware exists but is disabled; may be useful reference for
   implementing Firebase auth middleware.

3. LoggingMiddleware already captures access logs; can be extended for audit.

================================================================================

PREPARED BY: HOTEL COMMAND
DTG: 2026-02-04 2215
STATUS: PREPARATORY ASSESSMENT COMPLETE
================================================================================
