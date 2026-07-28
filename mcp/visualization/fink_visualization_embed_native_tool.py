"""
title: Fink Financial Chart Tool (Native)
author: Antigravity Pair Programmer
author_url: https://github.com/google/antigravity
version: 2.0
"""

import httpx
from pydantic import BaseModel
from typing import Optional, List

class Tools:
    def __init__(self):
        pass

    async def visualize_native(
        self,
        ticker: str,
        selected_metrics: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        normalize: Optional[bool] = False,
        growth_rate_yoy: Optional[bool] = False,
        __event_emitter__=None
    ) -> str:
        """
        Generates and mounts an interactive Chart.js financial analytics chart for a given stock ticker.
        Auto-fetches data on first use — no need to prime the cache.
        
        :param ticker: Stock ticker symbol (e.g. 'UNH').
        :param selected_metrics: List of metrics to plot. Valid metrics: {{VALID_METRIC_NAMES}}
        :param start_year: Start year bound for the timeline (e.g. 2018).
        :param end_year: End year bound for the timeline (e.g. 2026).
        :param normalize: Set to True to normalize chart data to show percentage growth from starting baseline. Set to False for absolute values. Default is False. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        :param growth_rate_yoy: Set to True to calculate and display the Year-over-Year (YoY) percentage rate of growth change for all metrics. Set to False for absolute values. Default is False. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        """
        # Try Docker compose service name first, then host.docker.internal, then localhost
        url = None
        import socket
        for host in ["fink-mcp-server", "host.docker.internal", "localhost"]:
            try:
                socket.gethostbyname(host)
                url = f"http://{host}:8001/visualize_html"
                break
            except socket.gaierror:
                continue
        if url is None:
            url = "http://localhost:8001/visualize_html"
            
        payload = {
            "ticker": ticker,
            # Omit when unset so the server applies DEFAULT_CHART_METRICS from the registry,
            # rather than duplicating a default here that can drift out of sync.
            "selected_metrics": selected_metrics,
            "start_year": start_year,
            "end_year": end_year,
            "normalize": normalize,
            "growth_rate_yoy": growth_rate_yoy
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=120.0)
                if response.status_code != 200:
                    return f"Error calling visualization server: {response.text}"
                
                mcp_res = response.json()
                raw_html_block = mcp_res if isinstance(mcp_res, str) else mcp_res.get("result", "")
                if not raw_html_block:
                    return "No content returned from visualization server."
                
                # Extract HTML block from markdown wrapper
                html_content = raw_html_block
                if "```html" in raw_html_block:
                    import re
                    match = re.search(r'```html\s*(.*?)\s*```', raw_html_block, re.DOTALL)
                    if match:
                        html_content = match.group(1)
                
                # Emit Svelte Rich UI Embed event to mount the iframe inside the chat bubble
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "embeds",
                        "data": {
                            "embeds": [html_content]
                        }
                    })
                    return f"📈 **Interactive chart generated for {ticker.upper()} below:**"
                else:
                    return "Interactive preview is not supported in this chat environment."
                    
        except Exception as e:
            return f"Failed to generate chart: {str(e)}"
