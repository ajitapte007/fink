import urllib.request
import json
import sys

def test_live():
    url = "http://localhost:3000/api/chat/completions"
    headers = {
        "Authorization": "Bearer sk-fink-dev-test-key-12345",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "data_pipe",
        "messages": [
            {"role": "user", "content": "Analyze UnitedHealth"}
        ],
        "stream": True
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    print(f"Sending POST request to live API at {url}...")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req) as response:
            print("\n--- Live Container Stream Start ---")
            for line in response:
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data:"):
                    # Open WebUI returns SSE formatted data: {json}
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
                        # Skip parsing errors on control sequences
                        pass
            print("\n--- Live Container Stream End ---\n")
    except Exception as e:
        print(f"Error calling live container API: {e}")

if __name__ == "__main__":
    test_live()
