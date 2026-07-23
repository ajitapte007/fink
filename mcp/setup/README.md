# Fink MCP Modular Setup Framework

This directory houses the orchestration and setup tooling for configuring the **Fink Stock Analyst Agent** workspace environment. 

---

## 🚀 Quick Start: Installation

To install and configure the application on your host, you only need to run the master orchestrator script from the repository root:

```bash
./mcp/setup/setup.sh
```

This single command will sequentially run the key collection manager, host virtualenv config, container registrations, database schema generation, and E2E verification test suite.

---

## Architecture Overview

We separate the setup flow into modular scripts to keep development iterations fast and host configurations decoupled from container databases:

1. **`setup.sh` (Master orchestrator)**: The main entry point. Automatically runs the environment configuration, host installations, and container updates sequentially.
2. **`setup_env.sh` (Interactive key manager)**: Collects your OpenAI and Alpha Vantage API keys interactively and saves them securely to the root `.env` file.
3. **`setup_host.sh` (Host python venv and testing dependencies)**: **(One-time per host)** Sets up the Python virtual environment, updates pip, installs testing dependencies, and downloads Playwright browser binaries for the headless E2E verification test suite.
4. **`setup_open_webui_container.sh` (Container & SQLite provisioner)**: Copies visualizer scripts and helper libraries directly into the running Open WebUI container, compiles code parameters to database OpenAPI schemas, binds custom tools directly to the assistant model, and triggers container reloads.
5. **`register_native_tool.py` (Database provisioner core)**: A generic command-line interface helper executing inside the container context to programmatically manage model presettings, system prompts, and tool ID binds in the SQLite database.

---

## Fast Re-Registration

During development, if you only modify your Svelte native tool Python file (`mcp/visualization/visualization_tool.py`), you can register the update in 2 seconds without rebuilding host dependencies by calling:

```bash
./mcp/setup/setup_open_webui_container.sh
```
