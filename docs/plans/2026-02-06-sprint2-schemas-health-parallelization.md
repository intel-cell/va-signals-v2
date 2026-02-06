# Sprint 2: Signal Schemas, Health Monitoring & State Parallelization

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Parallelize the state runner, create 3 new signal schemas, add email delivery health checks, and implement a dead-man's switch for zero-signal alerting.

**Architecture:** State runner parallelization uses ThreadPoolExecutor with Lock-protected counters. Signal schemas are YAML-only (no code changes). Health monitoring extends the existing /api/health endpoint with SMTP connectivity and staleness detection.

**Tech Stack:** Python 3.11, concurrent.futures, threading.Lock, YAML, FastAPI, smtplib, pytest

---

## Sprint 2 Task Summary

| Task | Summary | Agent | Files |
|------|---------|-------|-------|
| T1 | Parallelize state runner | Alpha | state/runner.py, tests/state/test_runner.py |
| T2 | regulatory_change.yaml schema | Bravo | config/signals/regulatory_change.yaml |
| T3 | claims_operations.yaml schema | Bravo | config/signals/claims_operations.yaml |
| T4 | legislative_action.yaml schema | Bravo | config/signals/legislative_action.yaml, tests |
| T5 | Email SMTP health check | Charlie | notify_email.py, dashboard_api.py, tests |
| T6 | Dead-man's switch (48h zero signals) | Charlie | dashboard_api.py, tests |
