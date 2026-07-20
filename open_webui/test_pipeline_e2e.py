import os
import sys
import json
import urllib.request
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

def run_local_simulation(query: str):
    """Runs the pipeline logic in-memory using local Python import."""
    print("\n=== RUNNING IN-MEMORY PYTHON SIMULATION ===")
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
    
    print(f"Executing pipeline in-memory for query: '{query}'...")
    try:
        generator = pipe.pipe(body)
        print("--- Stream Start ---")
        for chunk in generator:
            sys.stdout.write(chunk)
            sys.stdout.flush()
        print("\n--- Stream End ---")
    except Exception as e:
        print(f"Error during in-memory simulation: {e}")

def run_live_api_test(query: str):
    """Sends a real HTTP POST request to the running Docker container API."""
    print("\n=== RUNNING LIVE CONTAINER API VERIFICATION ===")
    
    # Verify static asset accessibility
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
        return

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
    print(f"Sending POST request to live container API at {url}...")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
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
                    except Exception:
                        pass
            print("\n--- Stream End ---")
    except Exception as e:
        print(f"Error during live container API call: {e}")
        print("Tip: Make sure the docker container is running (docker-compose up -d) and the API key has been seeded.")

if __name__ == "__main__":
    query = "Analyze UnitedHealth"
    
    # Check command line argument for mode selection
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    
    if mode in ("local", "both"):
        run_local_simulation(query)
    if mode in ("live", "both"):
        run_live_api_test(query)
