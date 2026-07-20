# Open WebUI Dynamic Financial Analytics Pipe (Gemini + Alpha Vantage Cache-First Modular Integration)

This project integrates Open WebUI with the Google Gemini API (v1beta/openai) and Alpha Vantage utilizing an Open WebUI native Pipe Function middleware. The stack is fully containerized, self-contained, and secure.

---

## 1. System Architecture

The following diagram illustrates how chat messages, preference extraction, data retrieval, local database caching, static assets compilation, and frontend rendering coordinate:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Open WebUI Frontend
    participant Pipe as Pipe Middleware (data_pipe.py)
    participant Gemini as Google Gemini API
    participant Cache as SQLite Cache (alphavantage_cache.db)
    participant AV as Alpha Vantage API
    participant FS as Static File Folder

    User->>Frontend: Submit query "Show FCF and EPS for UNH from 2016 to 2022"
    Frontend->>Pipe: Pass message payload history
    
    rect rgb(220, 235, 255)
        Note over Pipe, Gemini: Pass 1: Preferences & Ticker Extraction
        Pipe->>Gemini: Pre-flight extraction prompt (history context)
        Gemini-->>Pipe: Return JSON: {"ticker": "UNH", "metrics": ["free_cash_flow", "eps"], "start_date": "2016-01-01", "end_date": "2022-12-31"}
    end
    
    rect rgb(240, 240, 240)
        Note over Pipe, Cache: Cache-First Retrieval (Multi-Ticker Check)
        Pipe->>Cache: Query cached data for UNH
        alt Cache Hit & Fresh (< 24h)
            Cache-->>Pipe: Return cached JSON (No network call!)
        else Cache Miss or Expired
            Pipe->>AV: Query Alpha Vantage API
            alt AV Fetch Success
                AV-->>Pipe: Return raw metrics
                Pipe->>Cache: Write raw metrics & timestamp
            else AV Network Offline
                Pipe->>Cache: Retrieve stale database cache (expired fallback)
                Note over Cache: Optional: Map Monthly to Daily adjusted close
            end
        end
    end

    Note over Pipe: Clean up stale static HTML files matching cache TTL

    rect rgb(235, 255, 235)
        Note over Pipe, FS: Dynamic HTML Dashboard Generation
        Pipe->>FS: Write chart-unh.html (checkboxes checked for FCF/EPS, slider set to 2016-2022)
    end

    Note over Pipe: Align metrics & format [DATA OVERRIDE LAYER]
    
    rect rgb(235, 255, 235)
        Note over Pipe, Gemini: Pass 2: Analysis & Chart Prompt Injections
        Pipe->>Gemini: Submit messages + data payload + system prompt rules
        Gemini-->>Pipe: Yield streamed token chunks
        Pipe-->>Frontend: Forward streamed response chunks (SSE)
    end

    Frontend->>Frontend: Render Markdown analysis & append iframe pointing to /static/chart-unh.html
    Note over Frontend: User sees the inlined, synchronized double-ended slider chart instantly!
```

---

## 2. Technology Stack & Interactions

### Docker Containerization
*   **Orchestration**: Managed via `docker-compose.yml` to bring up the official Open WebUI container.
*   **Port Mapping**: `3000:8080` exposes the SvelteKit frontend server on the host port `3000`.
*   **PYTHONPATH Isolation**: `/app/backend/open_webui_analyst` mounts the custom modules (`alphavantage/`, `models.py`) safely without name conflicts, adding it to Python's system path so imports resolve cleanly.
*   **Offline Mode**: Setting `OFFLINE_MODE=True` disables default Hugging Face sentence-transformers model auto-updates on container startup, making boot times instantaneous.

### Open WebUI Pipe Function
*   **Pipe Class (`Pipe`)**: Implements Open WebUI's native ASGI `pipe` interface.
*   **Valves**: Exposes model configurations (API keys and default model) in the admin UI panel for easy management.
*   **Dynamic State Interceptor**: Scans every message. If no stock ticker is detected by the pre-flight prompt, it triggers the **Dormant State** and passes messages directly to Gemini. If a ticker is detected, it triggers the **Active State** to retrieve, cache, and inject metrics.

### Alpha Vantage Cache-First Engine
*   **SQLite Caching (`fetch_utils.py`)**: Stores responses locally in `alphavantage_cache.db` with a 24-hour Time-to-Live (TTL) invalidation policy to respect API rate limits.
*   **Offline Mapping Fallback**: If network fetches fail, it searches local pre-seeded JSON cache files. If daily price history is missing but monthly data is available, it maps monthly values into a simulated daily-close format, ensuring the UI chart renders correctly.

### Dynamic Checkboxes & Custom Double-Ended Range Slider
*   **Dynamic Checklist Controls**: Toggle metrics (Stock Price, P/E Ratio, EPS, Revenue, Free Cash Flow, Shares Outstanding) instantly.
*   **Modular Styles & Logic (`chartUtils.js`)**:
    *   `injectSliderStyles()`: Dynamically inserts the dual-range slider CSS track and handle styles into the document head at load time, keeping the HTML template code clean.
    *   `setupDualSlider(...)`: Overlays two standard range inputs, draws a dynamic `linear-gradient` highlight connection track between the thumbs, handles dragging events, and prevents start/end thumb crossover.
*   **Automatic Bounds Initialization**: Sorted date labels are constructed from the dataset on load, ensuring range boundaries (`min`/`max` values) are bound to the full timeline length immediately.
*   **Quick Timeline Snapping**: Buttons (`1Y`, `3Y`, `5Y`, `10Y`, `All`) programmatically move the handles and highlight the selected window.

---

## 3. Core Benefits

### Bring Your Own Model (BYOM)
*   The middleware utilizes standard OpenAI client specifications, allowing you to route requests to **any provider** (Google Gemini, OpenAI, Anthropic, or local offline LLMs running via Ollama/LM Studio).
*   Models and endpoints can be swapped dynamically on the fly by changing the Valves configuration in the admin dashboard.

### Local Privacy & Re-use
*   **Multi-Ticker SQLite Re-use**: Switching between tickers (or returning to a previously queried stock) reads directly from the cache, rendering the dashboard in `< 10ms` without making duplicate network requests.
*   **Automatic Storage Alignment**: Stale static HTML files are cleaned up from the static assets directory whenever their corresponding cache entry expires or gets removed, aligning local disk usage with database caching.
*   **Telemetry Bypass**: Setting `OFFLINE_MODE` blocks tracking connections and automatic model checks to Hugging Face, keeping operations completely private.

---

## 4. REST API Integration

Open WebUI exposes standard OpenAI-compatible endpoints on port 3000. You can query the custom model programmatically from any script or application:

1.  Navigate to **Settings > Account** and generate an **API Key**.
2.  Send a POST request requesting the model `data_pipe`:

```bash
curl -X POST http://localhost:3000/api/chat/completions \
  -H "Authorization: Bearer <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "data_pipe",
    "messages": [{"role": "user", "content": "Analyze UnitedHealth"}],
    "stream": true
  }'
```
