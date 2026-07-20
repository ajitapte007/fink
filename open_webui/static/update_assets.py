#!/usr/bin/env python3
import sys
import urllib.request
from pathlib import Path

DEFAULT_CHARTJS_VERSION = "4.4.1"

def update_assets(version: str = DEFAULT_CHARTJS_VERSION):
    dest_dir = Path(__file__).parent.resolve()
    dest_file = dest_dir / "chart.js"
    url = f"https://cdn.jsdelivr.net/npm/chart.js@{version}/dist/chart.umd.js"
    
    print(f"Downloading Chart.js version {version} from {url}...")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Set a user-agent to avoid CDN rate-limiting or blocking
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            with open(dest_file, "wb") as f:
                f.write(response.read())
        print(f"Successfully updated Chart.js! Saved to {dest_file} ({dest_file.stat().st_size / 1024:.1f} KB)")
    except Exception as e:
        print(f"Error downloading Chart.js: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CHARTJS_VERSION
    update_assets(ver)
