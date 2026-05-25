---
description: Validation sequence to run after any code change before presenting to the user for testing.
---

# Post-Change Validation Sequence

Run this **exact sequence** after every code change, in order. All steps must pass before telling the user to test.

## 1. Unit Tests (Python Backend)

```bash
# turbo
cd /Users/ajitapte/.gemini/antigravity/scratch/fink/agent && uv run pytest tests/ -v
```

**Expected**: All tests pass with exit code 0. Zero failures, zero errors.

---

## 2. Backend Server Startup

```bash
# Kill any stale process on port 8000 first
lsof -ti :8000 | xargs kill -9 2>/dev/null

# Start the backend
cd /Users/ajitapte/.gemini/antigravity/scratch/fink/agent && GEMINI_API_KEY='AIzaSyDReYOJ4EKZWcaFvnCQcJWJ5OenZzt858g' uv run uvicorn main:app --port 8000 --reload
```

**Expected**: `Application startup complete.` in output. No import errors or crashes.

---

## 3. Backend Smoke Test (curl)

```bash
# turbo
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"ticker": "AAPL", "message": "Analyze fundamentals"}' | python3 -m json.tool | head -30
```

**Expected**: Valid JSON response containing:
- `agent_pathway` (non-empty array)
- `iron_triangle_scores` (3 numeric fields: Fundamentals, Valuation, SentimentMomentum)
- `synthesis_summary` (non-empty string)
- `drilldown_matrix` with Fundamentals, Valuation, SentimentMomentum arrays

---

## 4. Frontend Dev Server

```bash
# turbo
cd /Users/ajitapte/.gemini/antigravity/scratch/fink/agent/ui && npm run dev
```

**Expected**: Vite outputs `ready in Xms` with a `Local:` URL. No build errors.

---

## 5. End-to-End Verification Checklist

After all services are running, manually verify (or use the browser tool):

- [ ] Navigate to the Vite URL (e.g. `http://localhost:5173`)
- [ ] The 3-pane layout renders (Left Sidebar, Center Canvas, Right Chat)
- [ ] Type "Analyze AAPL fundamentals" in the chat input and press Enter
- [ ] The chat shows "Executing Tripartite Orchestration..." loading state
- [ ] On response: A2A Breadcrumbs appear at the top of the chat panel
- [ ] The Iron Triangle Web (3-axis radar chart) renders with scores
- [ ] The Synthesis Summary Card populates with diagnostic text
- [ ] The Drilldown Matrix shows 3 columns of metrics

---

## Failure Protocol

If **any** step fails:
1. Fix the root cause.
2. Re-run the **entire sequence** from Step 1.
3. Do NOT tell the user to test until all 5 steps pass cleanly.
