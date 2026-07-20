---
name: fink-open-webui-testing
description: Guidelines and instructions for testing and deploying the Fink Open WebUI Integration stack.
---
# Fink Open WebUI Testing & Deployment Skill

This skill provides step-by-step developer guidelines for maintaining, testing, and deploying the Fink Open WebUI dynamic financial analytics middleware integration.

---

## 1. Local Development & Testing

### Running Unit and Integration Tests
We use `pytest` inside the virtual environment for unit and integration testing:
```bash
# Set PYTHONPATH to search inside the isolated package namespace
export PYTHONPATH=$(pwd)/open_webui

# Execute the test suite using the virtual environment python interpreter
agent/.venv/bin/pytest open_webui/tests
```
This suite covers:
*   SQLite cache writes, reads, and 24-hour TTL invalidation.
*   Offline local JSON cache fallbacks (verifying AMZN, AAPL, etc.).
*   Monthly adjusted time-series simulation/translation format mapping.
*   Pre-flight Gemini stock ticker and date bounds (`start_date`, `end_date`) preferences extraction logic.
*   Context payload injection and stream generation.

### Running the E2E Verification Script
Use the unified `test_pipeline_e2e.py` script to verify pipeline execution:
```bash
# Runs both the local python simulation and the live HTTP API test against Docker
python3 open_webui/test_pipeline_e2e.py both

# Run ONLY the local in-memory simulation
python3 open_webui/test_pipeline_e2e.py local

# Run ONLY the live container HTTP API test
python3 open_webui/test_pipeline_e2e.py live
```

---

## 2. Docker Deployment Checklist

### Step 1: Configure Credentials
Ensure your API keys are added in the root `.env` file:
```ini
ALPHAVANTAGE_API_KEY=your_key
GEMINI_API_KEY=your_key
```

### Step 2: Spin Up Container
Launch the containerized environment on port 3000:
```bash
docker-compose up -d
```

### Step 3: Seed/Register the custom model
To register the Pipe middleware automatically without using the UI import tool, execute the seeding script inside the running container:
```bash
docker exec open-webui-analyst python3 /app/backend/open_webui_analyst/seed_db.py
```
This registers the **`Fink Finance Due Diligence Agent`** model globally.

### Step 4: Verify Server Health
Check the container logs to ensure Uvicorn and ASGI applications booted cleanly:
```bash
docker logs open-webui-analyst --tail 50
```
Ensure you see `"INFO: Started server process [1]"` and HTTP 200 responses.

---

## 3. Verification Outcome & Detailed Report

The following verification metrics detail what was checked, the execution results, and measured latencies of the dynamic dashboard system:

| Verification Target | Scope Checked | Result | Measured Latency |
| :--- | :--- | :--- | :--- |
| **Unit & Integration Tests** | SQLite TTL cache, offline fallbacks, date translations, and payload overrides. | **PASS** (17 tests passed) | `~13.22s` (total run) |
| **Pre-flight Preferences Extraction** | Gemini JSON model intent parser (ticker, metrics, start/end dates). | **PASS** (unified user prompt) | `~1.2s to 1.8s` |
| **E2E Simulated Pipeline** | Local in-memory execution of Active, Ticker Clarification, and Dormant states. | **PASS** | `~50ms` (excluding pre-flight) |
| **E2E Container HTTP API** | Live HTTP completions request to container port 3000 for all 3 states. | **PASS** | `~120ms` (faked text completion) |
| **Static HTML Integrity** | Inlined `chartUtils.js` checks, processedMetrics values, and Chart.js initialization tags. | **PASS** | `0ms` (instant static parsing) |
| **Static Assets Web Service** | Uvicorn serving static `/static/chartUtils.js` and live container compiled dynamic `/static/chart-{ticker}.html`. | **PASS** (HTTP 200 OK) | `~2ms` (HTTP response) |
| **Static Files Clean-up** | Automatic deletion of stale/expired `chart-*.html` files. | **PASS** | `<2ms` (SQLite scan & delete) |
