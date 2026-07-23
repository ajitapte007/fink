# mcp/tests/test_stdio_jsonrpc.py
import subprocess
import json
import time

def run_jsonrpc_test():
    # Start the server as a stdio subprocess
    cmd = ["venv/bin/python", "mcp/server.py"]
    print(f"Launching MCP server stdio subprocess: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for the startup logs on stderr
    time.sleep(1)
    
    # 1. Send initialize request
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }
    
    print("\n---> Sending 'initialize' request...")
    proc.stdin.write(json.dumps(init_req) + "\n")
    proc.stdin.flush()
    
    # Read response line
    stdout_line = proc.stdout.readline()
    print(f"<--- Server Stdout: {stdout_line.strip()}")
    
    # 2. Send tools/call request for alphavantage
    call_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "alphavantage",
            "arguments": {
                "ticker": "UNH"
            }
        }
    }
    
    print("\n---> Sending 'tools/call' for 'alphavantage'...")
    proc.stdin.write(json.dumps(call_req) + "\n")
    proc.stdin.flush()
    
    # Read response
    stdout_line = proc.stdout.readline()
    print(f"<--- Server Stdout: {stdout_line.strip()}")
    
    # Terminate and read remaining stderr logs
    proc.terminate()
    stdout_rem, stderr_rem = proc.communicate()
    
    print("\n=== Remaining Server Stderr (Tracebacks) ===")
    print(stderr_rem)
    print("============================================")

if __name__ == "__main__":
    run_jsonrpc_test()
