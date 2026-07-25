import sys
from pathlib import Path
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from visualization.visualization_tool import generate_visualization_html
import json

try:
    html = generate_visualization_html("AMZN", selected_metrics=["price", "revenue"])
    print("HTML Length:", len(html))
    print("Contains 'metric-revenue':", "metric-revenue" in html)
    print("Contains 'category-header':", "category-header" in html)
    print("Contains 'toggle-sh':", "toggle-sh" in html)
    print("Contains 'axis-selector':", "axis-selector" in html)
    
    # Save a copy to inspect
    with open("scratch/generated_debug.html", "w") as f:
        f.write(html)
    print("Saved debug HTML to scratch/generated_debug.html")
except Exception as e:
    print("Error:", str(e))
