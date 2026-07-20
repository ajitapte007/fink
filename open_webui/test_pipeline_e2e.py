import os
import sys
import json
import urllib.request
import time
from pathlib import Path

# Setup PYTHONPATH for local imports
current_dir = Path(__file__).parent.resolve()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Read API keys from .env
root_dir = current_dir.parent
env_path = root_dir / ".env"
if env_path.exists():
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

def verify_html_integrity(html_content: str, source_description: str):
    """Performs static checks on the generated HTML content to verify script integrity and prevent blank screens."""
    print(f"\n[INTEGRITY] Verifying HTML integrity for {source_description}...")
    
    # 1. Check for unreplaced formatting placeholders
    placeholders = ["{chart_utils_code}", "{processed_metrics}", "{metrics_config}"]
    for ph in placeholders:
        if ph in html_content:
            print(f"FAIL: Found un-replaced formatting placeholder '{ph}' in {source_description}!")
            sys.exit(1)
            
    # 2. Check that chartUtils.js was inlined successfully
    if "setupDualSlider" not in html_content:
        print(f"FAIL: chartUtils.js inlining failed! setupDualSlider not found in {source_description}.")
        sys.exit(1)
        
    # 3. Check that processedMetrics contains actual data keys
    if "const processedMetrics = {}" in html_content or "const processedMetrics = ;" in html_content:
        print(f"FAIL: processedMetrics data block is empty in {source_description}!")
        sys.exit(1)
        
    # 4. Check for Chart.js framework tags
    if "new Chart" not in html_content:
        print(f"FAIL: Chart.js initialization code ('new Chart') not found in {source_description}!")
        sys.exit(1)
        
    print(f"SUCCESS: HTML integrity check passed for {source_description}!")

def run_local_simulation(query: str):
    """Runs the pipeline logic in-memory using local Python import. Returns accumulated response text."""
    print(f"\n=== RUNNING IN-MEMORY PYTHON SIMULATION for '{query}' ===")
    from data_pipe import Pipe
    pipe = Pipe()
    
    pipe.valves.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    pipe.valves.ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")
    
    body = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ],
        "model": "gemini-2.5-flash"
    }
    
    # Ensure clean slate before running simulation for UNH
    if "UnitedHealth" in query or "unh" in query.lower():
        local_chart_file = current_dir / "static" / "chart-unh.html"
        if local_chart_file.exists():
            local_chart_file.unlink()
            
    response_chunks = []
    try:
        generator = pipe.pipe(body)
        print("--- Stream Start ---")
        for chunk in generator:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            response_chunks.append(chunk)
        print("\n--- Stream End ---")
        
        response_text = "".join(response_chunks)
        
        # Verify local file generation and integrity for active state
        if "UnitedHealth" in query or "unh" in query.lower():
            if local_chart_file.exists():
                with open(local_chart_file, "r") as f:
                    content = f.read()
                verify_html_integrity(content, f"local static file ({local_chart_file})")
            else:
                print("FAIL: local simulation did not generate chart-unh.html!")
                sys.exit(1)
                
        return response_text
            
    except Exception as e:
        print(f"Error during in-memory simulation: {e}")
        sys.exit(1)

def run_live_api_test(query: str):
    """Sends a real HTTP POST request to the running Docker container API. Returns accumulated response text."""
    print(f"\n=== RUNNING LIVE CONTAINER API VERIFICATION for '{query}' ===")
    
    url = "http://localhost:3000/api/chat/completions"
    headers = {
        "Authorization": "Bearer sk-fink-dev-test-key-12345",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "data_pipe",
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": True
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    response_chunks = []
    try:
        with urllib.request.urlopen(req) as response:
            print("--- Stream Start ---")
            for line in response:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data:"):
                    content_json_str = line_str[5:].strip()
                    if content_json_str == "[DONE]":
                        break
                    try:
                        content_json = json.loads(content_json_str)
                        choices = content_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                sys.stdout.write(content)
                                sys.stdout.flush()
                                response_chunks.append(content)
                    except Exception:
                        pass
            print("\n--- Stream End ---")
            
            response_text = "".join(response_chunks)
            
            # Fetch and verify the live generated static chart over HTTP
            if "UnitedHealth" in query or "unh" in query.lower():
                live_chart_url = "http://localhost:3000/static/chart-unh.html"
                print(f"\nVerifying live compiled chart serving at {live_chart_url}...")
                # Wait briefly for file system sync
                time.sleep(1)
                try:
                    with urllib.request.urlopen(live_chart_url) as resp:
                        if resp.status == 200:
                            content = resp.read().decode("utf-8")
                            verify_html_integrity(content, f"live container served file ({live_chart_url})")
                        else:
                            print(f"FAIL: Fetching live chart returned status {resp.status}!")
                            sys.exit(1)
                except Exception as e:
                    print(f"FAIL: Failed to fetch live chart over HTTP: {e}")
                    sys.exit(1)
                    
            return response_text
                
    except Exception as e:
        print(f"Error during live container API call: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check command line argument for mode selection
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    
    # Verify static asset accessibility first
    if mode in ("live", "both"):
        static_url = "http://localhost:3000/static/chartUtils.js"
        print(f"Verifying static asset serving at {static_url}...")
        try:
            static_req = urllib.request.Request(static_url, method="HEAD")
            with urllib.request.urlopen(static_req) as resp:
                if resp.status == 200:
                    print("SUCCESS: chartUtils.js is serving correctly at /static/chartUtils.js!")
                else:
                    print(f"WARNING: Static asset check returned status {resp.status}")
        except Exception as e:
            print(f"ERROR: chartUtils.js static endpoint check failed: {e}")
            print("Tip: Make sure the docker container is running (docker-compose up -d).")
            sys.exit(1)

    # 1. Test query for Active State (with ticker UNH)
    active_query = "show unh price and pe ratio over the last 10 years"
    
    # 2. Test query for Ticker Clarification Request (financial query, missing ticker)
    clarify_query = "plot stock price and pe ratio"
    
    # 3. Test query for Dormant State (general conversation query)
    dormant_query = "how is the weather?"
    
    if mode in ("local", "both"):
        # Local Sim validations
        r1 = run_local_simulation(active_query)
        assert "/static/chart-unh.html" in r1, f"FAIL: Active state did not yield iframe. Response: {r1}"
        
        r2 = run_local_simulation(clarify_query)
        assert "specify which stock ticker symbol" in r2, f"FAIL: Clarification prompt not triggered. Response: {r2}"
        
        r3 = run_local_simulation(dormant_query)
        assert "Gemini text analysis disabled for testing" in r3, f"FAIL: Dormant faked state failed. Response: {r3}"
        print("\nSUCCESS: All local simulation E2E checks passed!")
        
    if mode in ("live", "both"):
        # Live Container API validations
        r1 = run_live_api_test(active_query)
        assert "/static/chart-unh.html" in r1, f"FAIL: Live active state did not yield iframe. Response: {r1}"
        
        r2 = run_live_api_test(clarify_query)
        assert "specify which stock ticker symbol" in r2, f"FAIL: Live clarification prompt not triggered. Response: {r2}"
        
        r3 = run_live_api_test(dormant_query)
        assert "Gemini text analysis disabled for testing" in r3, f"FAIL: Live dormant faked state failed. Response: {r3}"
        print("\nSUCCESS: All live container API E2E checks passed!")
        
    print("\nALL E2E VERIFICATION CHECKS SUCCESSFULLY COMPLETED!")
