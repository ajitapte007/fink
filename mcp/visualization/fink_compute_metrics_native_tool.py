"""
title: Fink Compute Metrics Tool (Native)
author: Antigravity Pair Programmer
author_url: https://github.com/google/antigravity
version: 1.0
"""

import httpx
from typing import Optional, List

class Tools:
    def __init__(self):
        pass

    async def compute_metrics_native(
        self,
        ticker: str,
        metrics: Optional[List[str]] = None,
        per_share_metrics: Optional[List[str]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> str:
        """
        Returns structured historical financial metrics as a JSON string for a given stock ticker.
        Auto-fetches data on first use. Use this to get precise numbers for analysis and reasoning.
        
        :param ticker: Stock ticker symbol (e.g. 'AAPL').
        :param metrics: List of metrics to extract. If omitted, returns all. Valid metrics: {{VALID_METRIC_NAMES}}
        :param per_share_metrics: List of aggregate metrics to scale by shares outstanding (e.g. ['revenue', 'free_cash_flow']).
        :param start_year: Start year filter, inclusive (e.g. 2018).
        :param end_year: End year filter, inclusive (e.g. 2024).
        """
        # Resolve MCP server host: Docker compose service name > host.docker.internal > localhost
        url = None
        import socket
        for host in ["fink-mcp-server", "host.docker.internal", "localhost"]:
            try:
                socket.gethostbyname(host)
                url = f"http://{host}:8001/compute_metrics"
                break
            except socket.gaierror:
                continue
        if url is None:
            url = "http://localhost:8001/compute_metrics"

        payload = {
            "ticker": ticker,
            "metrics": metrics,
            "per_share_metrics": per_share_metrics,
            "start_year": start_year,
            "end_year": end_year
        }
        # Remove None values to let the server use defaults
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=120.0)
                if response.status_code != 200:
                    return f"Error calling compute_metrics server: {response.text}"

                mcp_res = response.json()
                # MCPO wraps the result in {"result": ...}
                result = mcp_res if isinstance(mcp_res, str) else mcp_res.get("result", mcp_res)
                if isinstance(result, str):
                    return result
                import json
                return json.dumps(result, indent=2)

        except Exception as e:
            return f"Failed to compute metrics: {str(e)}"
