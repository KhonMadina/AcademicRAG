# AcademicRAG Production Runbook

This runbook is the minimum operational guide for starting, stopping, recovering, and maintaining AcademicRAG.

## 1) Scope and Service Map

- Launcher: `python run_system.py`
- Frontend: port `3000`
- Backend API: port `8000`
- RAG API: port `8001`
- Ollama: port `11434`
- Logs directory: `logs/`
- Primary data:
  - SQLite chat/session DB: `backend/chat_data.db`
  - Vector store: `lancedb/`
  - Index metadata/artifacts: `index_store/`
  - Uploaded files: `shared_uploads/`

## 2) Startup Procedure

### Preconditions

1. Confirm Python and Node dependencies are installed.
2. Confirm Ollama models are available:
   - `gemma3:12b-cloud`
   - `gemma3:27b-cloud`
3. Confirm required paths are writable:
   - `logs/`, `backend/`, `lancedb/`, `index_store/`, `shared_uploads/`

### Start all services

1. From repo root:
   - `python run_system.py`
2. Wait for services to report healthy in launcher output.
3. Validate health manually:
   - Backend liveness: `GET http://localhost:8000/health`
   - Backend readiness: `GET http://localhost:8000/health/ready`
   - RAG liveness: `GET http://localhost:8001/health`
   - RAG readiness: `GET http://localhost:8001/health/ready`
4. Validate metrics endpoints:
   - Backend metrics: `GET http://localhost:8000/metrics`
   - RAG metrics: `GET http://localhost:8001/metrics`

### Startup failure quick triage

1. If a port is already in use, stop conflicting process and restart.
2. If readiness fails, verify Ollama is running and models are present.
3. If backend fails, inspect `logs/backend_server.log` and `logs/system.log`.
4. If RAG API fails, inspect `logs/rag_api_server.log` and `logs/system.log`.

## 3) Shutdown Procedure

### Preferred (graceful)

- In the terminal running launcher, press `Ctrl+C`.
- Or run: `python run_system.py --stop`

### Forced shutdown (only if graceful stop fails)

- Terminate service processes by PID and confirm ports `3000/8000/8001/11434` are released.
- Re-run health checks to confirm no stale process is serving old state.

### Post-shutdown checks

1. Confirm no active writes are happening in `backend/chat_data.db`.
2. Confirm no indexing jobs remain active.
3. Archive logs if needed before restart.

## 4) Backup Procedure

Run backups during low activity windows. If possible, stop writes first (graceful shutdown recommended).

### What to back up

- `backend/chat_data.db`
- `lancedb/`
- `index_store/`
- `shared_uploads/`
- Optional: `logs/`

### Backup steps

1. Create timestamped backup directory, for example: `backups/YYYYMMDD_HHMMSS/`.
2. Copy the data paths listed above into that directory.
3. Generate checksums for copied files (or at minimum for `chat_data.db`).
4. Store backup metadata: timestamp, operator, host, commit SHA (if available).

### Backup verification

1. Confirm backup folder contains all expected paths.
2. Verify checksum output exists.
3. Perform periodic restore drill (see Section 5).

## 5) Restore Procedure

Use restore when data corruption, accidental deletion, or unrecoverable index state occurs.

### Restore steps

1. Stop all services (`Ctrl+C` or `python run_system.py --stop`).
2. Move current data paths to a quarantine folder (do not delete immediately).
3. Copy backup contents into original locations:
   - `backend/chat_data.db`
   - `lancedb/`
   - `index_store/`
   - `shared_uploads/`
4. Start services (`python run_system.py`).
5. Run validation:
   - `GET /health` and `GET /health/ready` on ports `8000` and `8001`
   - open UI and verify sessions/indexes render
   - run one index query and one chat query
6. If validation fails, rollback using quarantine data and investigate logs.

## 6) Incident Response Checklist

Use this checklist for service degradation, failures, or data integrity concerns.

### A) Detect and classify

1. Identify impact scope: frontend only, backend only, RAG only, or full outage.
2. Record first-seen timestamp and affected endpoints.
3. Capture request correlation ID (`X-Request-ID`) from failing client/API response.

### B) Triage and diagnose

1. Check liveness/readiness endpoints.
2. Check metrics spikes in:
   - `requests.by_status` (`4xx`/`5xx`)
   - endpoint latency (`avg_ms`, `max_ms`)
   - indexing failures/duration
   - semantic cache hit-rate anomalies
3. Inspect logs using correlation ID in:
   - `logs/backend_server.log`
   - `logs/rag_api_server.log`
   - `logs/system.log`

### C) Stabilize

1. If indexing is failing repeatedly, pause new indexing traffic.
2. If one service is unhealthy, restart only that service first.
3. If repeated model-call errors occur, verify Ollama process and model availability.
4. If needed, perform full stack restart.

### D) Recover

1. Re-run health/readiness checks.
2. Re-test critical flows:
   - session create/list
   - index upload/build
   - chat and chat stream
3. Monitor metrics for 10–15 minutes for reoccurrence.

### E) Close-out

1. Document root cause, trigger, and time-to-recovery.
2. Record affected users/sessions/indexes.
3. Add one concrete prevention task to the implementation board.

## 7) Operational SLO Guardrails (Lightweight)

Use these as practical alerts for operator action:

- Readiness not ready for > 2 minutes.
- Any endpoint sustained `5xx` > 5% over 5 minutes.
- `max_ms` latency sudden jump > 3x normal baseline.
- Indexing `failed` count increases within same hour.

## 8) Operator Handover Notes

At shift end or incident handoff, record:

- Current service health/readiness status
- Open incidents and current mitigation
- Last successful backup timestamp
- Any quarantined data paths
- Pending follow-up tasks
