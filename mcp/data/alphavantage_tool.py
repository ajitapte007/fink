# mcp/data/alphavantage_tool.py
import sys
from pathlib import Path

# Add mcp/ root folder to sys.path to enable local imports
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

import json
import traceback
from data.fetch_utils import get_all_data_for_ticker

def fetch_alphavantage_data(ticker: str, mock_data: bool = True) -> dict:
    """
    Fetches comprehensive historical financials (earnings, cashflow, balance sheets) for a ticker.
    Saves the full payload to the database cache and returns fetch metadata.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        return {
            "ticker": ticker,
            "success": False,
            "error": {
                "message": "Ticker symbol cannot be empty",
                "details": "Missing ticker parameter"
            }
        }
        
    try:
        raw_data = get_all_data_for_ticker(ticker, mock_data=mock_data)
        
        error_found = False
        error_details = ""
        for key, val in raw_data.items():
            if isinstance(val, dict):
                if "Error Message" in val:
                    error_found = True
                    error_details += f"API Error in {key}: {val['Error Message']}. "
                elif "Note" in val:
                    error_found = True
                    error_details += f"API Note in {key}: {val['Note']}. "
                    
        from data.models import VALID_METRIC_KEYS
        from data.process_utils import get_corporate_identity
        identity = get_corporate_identity(raw_data)
        
        corrupt_funcs = raw_data.get("_meta_corrupt_functions", [])
        success = (not error_found) and (len(corrupt_funcs) == 0)
        
        err_dict = None
        if not success:
            err_dict = {
                "message": "Data fetch failed or returned corrupt files",
                "details": f"Failed or corrupt functions: {corrupt_funcs}. API Errors: {error_details}"
            }
        
        return {
            "ticker": ticker,
            "success": success,
            "source": raw_data.get("_meta_source", "unknown"),
            "last_refreshed": raw_data.get("_meta_last_refreshed", "unknown"),
            "expires_at": raw_data.get("_meta_expires_at", "unknown"),
            "corporate_identity": identity.model_dump() if hasattr(identity, "model_dump") else identity.dict(),
            "valid_metric_keys": VALID_METRIC_KEYS,
            "error_details": error_details if error_details else None,
            "corrupt_functions": corrupt_funcs,
            "error": err_dict
        }
        
    except Exception as e:
        error_info = traceback.format_exc()
        return {
            "ticker": ticker,
            "success": False,
            "source": "error",
            "error": {
                "message": str(e),
                "details": error_info
            }
        }
