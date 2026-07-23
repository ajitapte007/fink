"""
title: Fink Financial Chart Tool (Native)
author: Antigravity Pair Programmer
author_url: https://github.com/google/antigravity
version: 1.0
"""

import httpx
from pydantic import BaseModel
from typing import Optional, List

class Tools:
    def __init__(self):
        pass

    async def visualization_embed_native(
        self,
        ticker: str,
        selected_metrics: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        __event_emitter__=None
    ) -> str:
        """
        Generates and mounts an interactive Chart.js financial analytics chart for a given stock ticker.
        
        :param ticker: Stock ticker symbol (e.g. 'UNH').
        :param selected_metrics: List of metrics (e.g. ['price', 'pe_ratio']).
        :param start_year: Start year bound for the timeline (e.g. 2018).
        :param end_year: End year bound for the timeline (e.g. 2026).
        """
        url = "http://host.docker.internal:8001/visualization_internal"
        try:
            import socket
            socket.gethostbyname("host.docker.internal")
        except socket.gaierror:
            url = "http://localhost:8001/visualization_internal"
            
        payload = {
            "ticker": ticker,
            "selected_metrics": selected_metrics or ["price"],
            "start_year": start_year,
            "end_year": end_year
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=20.0)
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
