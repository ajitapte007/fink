# MCP Financial Analytics API & Tool Reference

This document describes the API schemas, tool schemas, and supported workflows for the MCP server.

---

## Tool API Reference

### 1. `alphavantage` Tool
Exposes cleaned financial history data for US-listed tickers.

- **Parameters:**
  - `ticker` (string, required): US ticker symbol (e.g. `"AAPL"`).

- **Returns:** JSON object containing:
  - `ticker` (string): The ticker symbol.
  - `source` (string): Origin of the data (`"mock"`, `"cache"`, or `"alphavantage"`).
  - `metrics`: Dictionary of statement lists (earnings, cashflow, balance sheets).
  - `error` (object, optional): If the fetch fails, contains detailed error logs.

- **Data Fetch Precedence:**
  1. Check mock datasets (if ticker matches mock assets or API limits reached).
  2. Local SQLite DB cache (TTL checking).
  3. Live Alpha Vantage API.

### 2. `visualization` Tool
Generates an interactive HTML-based time series widget leveraging Chart.js.

- **Parameters:**
  - `ticker` (string, required): Ticker symbol.
  - `data` (object, required): JSON object returned by the `alphavantage` tool.
  - `selected_metrics` (array of strings, optional): Metrics to check by default. Defaults to `["price", "ps_ratio"]`.
  - `start_year` (integer, optional): Initial start year bound.
  - `end_year` (integer, optional): Initial end year bound.

- **Returns:** Markdown block wrapped with `html` rendering script:
  - Renders a multi-graph line chart.
  - X-axis: Time (years).
  - Dual Y-axes (left: Stock Price; right: selected financial ratios/metrics).
  - Interactive widgets: checkboxes for choosing metrics (Price, P/S Ratio, Revenue, EBITDA, Cash Flow, etc.), and a double-thumb slider to control start/end date range.

---

## Workflows

### 1. Direct UI Interaction Workflow
1. User prompts: *"Compare AAPL stock price with its PS ratio."*
2. LLM calls `alphavantage(ticker="AAPL")` and receives JSON data.
3. LLM calls `visualization(ticker="AAPL", data={...})` and receives the HTML string.
4. The client renders the widget inside a sandboxed `<iframe>`.
5. The user directly toggles checkbox metrics on the screen or slides the range slider.
6. The HTML script dynamically recalculates scale bounds and updates the Chart.js canvas immediately in-browser.

### 2. Chat-Driven Modification Workflow
1. User sees the initial chart and types in chat: *"Now filter it from 2018 to 2022 and show Revenue instead of PS ratio."*
2. LLM parses the request and invokes:
   `visualization(ticker="AAPL", data=..., selected_metrics=["price", "revenue"], start_year=2018, end_year=2022)`
3. The server generates a new HTML block with initial parameter states preset.
4. The client swaps/renders the new widget block.
