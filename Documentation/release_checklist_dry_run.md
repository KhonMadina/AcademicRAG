# AcademicRAG Release Checklist + Dry Run

This checklist is the release gate for Sprint 8 / T8.3.

## 1) Release Checklist (Go/No-Go)

### A. Environment and Dependencies

- [ ] Python environment created and dependencies installed (`requirements.txt`)
- [ ] Node dependencies installed (`package.json`)
- [ ] Ollama installed and running
- [ ] Required Ollama models available:
  - [ ] `gemma3:4b-cloud`
  - [ ] `gemma3:12b-cloud`

### B. Configuration and Paths

- [ ] `.env` present and validated by launcher
- [ ] Required writable paths exist:
  - [ ] `logs/`
  - [ ] `backend/`
  - [ ] `lancedb/`
  - [ ] `index_store/`
  - [ ] `shared_uploads/`

### C. Service Startup and Health

- [ ] `python run_system.py` starts services without fatal errors
- [ ] `python run_system.py --health` reports expected service status
- [ ] Backend liveness/readiness pass (`/health`, `/health/ready`)
- [ ] RAG API liveness/readiness pass (`/health`, `/health/ready`)
- [ ] Metrics endpoints respond (`/metrics` on 8000 and 8001)

### D. Functional Smoke

- [ ] Session create/list flow works
- [ ] Index create/upload/build flow works
- [ ] Chat flow works (answer returned)
- [ ] Streaming chat flow works (`/chat/stream`)

### E. Observability and Recovery

- [ ] Logs present (`logs/system.log`, `logs/backend_server.log`, `logs/rag_api_server.log`)
- [ ] `X-Request-ID` visible in API responses/log traces
- [ ] Backup/restore procedure reviewed against runbook
- [ ] Incident checklist reviewed by operator

### F. Release Readiness

- [ ] Known limits reviewed (`Documentation/known_limits_capacity_guide.md`)
- [ ] Deployment guide and quick-start followed without contradiction
- [ ] No critical unresolved regressions in tests/health checks

---

## 2) Dry Run Execution (2026-03-06)

### Scope

- Performed in current workspace environment (not a fresh machine image).
- Goal: smoke validate startup/health/observability path from current docs.

### Commands Executed

1. `D:/dev_final_project/AcademicRAG/.venv/Scripts/python.exe run_system.py --no-frontend`
2. `D:/dev_final_project/AcademicRAG/.venv/Scripts/python.exe run_system.py --health`
3. `D:/dev_final_project/AcademicRAG/.venv/Scripts/python.exe system_health_check.py`
4. `curl` endpoint probes:
   - `http://localhost:8000/health`
   - `http://localhost:8000/health/ready`
   - `http://localhost:8000/metrics`
   - `http://localhost:8001/health`
   - `http://localhost:8001/health/ready`
   - `http://localhost:8001/metrics`

### Observed Results

- `run_system.py --health`: backend and rag-api reported **Ready**, frontend **Stopped** (expected for no-frontend dry run).
- Endpoint probes: all six returned HTTP `200`.
- `system_health_check.py`: summary reported **5/6 checks passed** and "System mostly healthy with minor issues".

### Noted Minor Issues (Non-blocking for this dry run)

1. `system_health_check.py` emits deprecation warnings (`table_names()`, `cgi`).
2. During sample query path, one model request returned `400` from Ollama generate endpoint after retrieval/reranking stage.
3. HuggingFace SSL warning appeared during initial model metadata request and retried.

### Dry Run Verdict

- **Result:** PASS with minor issues to track.
- **Release impact:** No blocker found for health/readiness/metrics startup path.

---

## 3) Clean-Machine Repro Protocol (Target < 30 minutes)

To satisfy acceptance strictly, the team should perform one timed clean-machine run:

1. Start timer at clone.
2. Follow `Documentation/installation_guide.md` exactly.
3. Start with `python run_system.py`.
4. Execute health/readiness/metrics checks.
5. Execute one index build and one chat request.
6. Record elapsed time and attach evidence in this file.

### Evidence to attach

- Start/end timestamps
- Command transcript or screenshots
- Health check outputs
- One successful index build response
- One successful chat response

---

## 4) Follow-up Items

- [ ] Stabilize `system_health_check.py` sample query path to avoid intermittent Ollama 400 outcome.
- [ ] Remove or replace deprecated API usage warnings where practical.
- [ ] Add a short CI/nightly smoke target that exercises `/health`, `/health/ready`, `/metrics` for backend and RAG API.
