"""
Revenue segment data fetcher using LLM with web search grounding.

Extracts product and geographic revenue segment data from SEC 10-K filings
by prompting an LLM with search capabilities, rather than scraping EDGAR HTML.
"""
import json
from typing import List, Dict, Any

from data.llm_client import get_llm_client


def _build_segment_prompt(ticker: str, company_name: str) -> tuple:
    """Build system and user prompts for revenue segment extraction."""
    system_prompt = (
        "You are an expert financial data analyst specializing in SEC 10-K annual report filings. "
        "Your task is to extract historical revenue segment data from public company filings. "
        "You MUST search for the actual SEC 10-K filings to ground your answers in real data. "
        "Do NOT hallucinate or estimate — only report numbers that appear in actual filings."
    )

    user_prompt = f"""Search for {ticker} ({company_name}) SEC 10-K annual report filings and extract revenue segment data for every available fiscal year, going back up to 20 years.

For each fiscal year, extract:
1. **Product/service segments**: Revenue broken down by product line, business unit, or service category as reported in the filing's segment disclosures (e.g., "iPhone", "Services", "Intelligent Cloud", etc.)
2. **Geographic segments**: Revenue broken down by geographic region as reported (e.g., "Americas", "Europe", "Greater China", etc.)

Output ONLY a valid JSON array, with one object per fiscal year, sorted by fiscal_year_end ascending. Each object must have exactly these keys:

- "fiscal_year_end": string in "YYYY-MM-DD" format (the exact fiscal year-end date from the filing)
- "product_segments": object mapping segment name (string) to annual revenue in raw USD (integer, NOT in millions or billions — multiply as needed)
- "geographic_segments": object mapping region name (string) to annual revenue in raw USD (integer)

Rules:
- Report ALL revenue figures in raw USD (e.g., $201,183,000,000 not $201.2B)
- Use the exact segment names as they appear in each year's filing (names may change across years)
- If a company does not disclose product or geographic segments in a given year, use an empty object {{}}
- Include data for every year you can find, up to 20 years back
- Do NOT include any text outside the JSON array — output ONLY the JSON"""

    return system_prompt, user_prompt


def _validate_segment_entry(entry: dict) -> bool:
    """Validate that a single segment entry has the expected structure."""
    if not isinstance(entry, dict):
        return False
    if "fiscal_year_end" not in entry:
        return False
    if not isinstance(entry.get("product_segments", {}), dict):
        return False
    if not isinstance(entry.get("geographic_segments", {}), dict):
        return False
    # Validate date format (YYYY-MM-DD)
    try:
        parts = entry["fiscal_year_end"].split("-")
        if len(parts) != 3 or len(parts[0]) != 4:
            return False
    except (AttributeError, IndexError):
        return False
    return True


def _validate_and_clean_response(data: Any) -> List[dict]:
    """Validate and clean the LLM response into a list of segment entries."""
    # Handle case where response is wrapped in an object with a "data" or "segments" key
    if isinstance(data, dict):
        for key in ("data", "segments", "results", "fiscal_years"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            # Single entry wrapped in an object
            if "fiscal_year_end" in data:
                data = [data]
            else:
                return []

    if not isinstance(data, list):
        return []

    valid_entries = []
    for entry in data:
        if _validate_segment_entry(entry):
            # Ensure segment dicts have numeric values
            cleaned = {
                "fiscal_year_end": entry["fiscal_year_end"],
                "product_segments": {},
                "geographic_segments": {}
            }
            for seg_name, seg_val in entry.get("product_segments", {}).items():
                try:
                    cleaned["product_segments"][str(seg_name)] = int(float(seg_val))
                except (ValueError, TypeError):
                    continue
            for seg_name, seg_val in entry.get("geographic_segments", {}).items():
                try:
                    cleaned["geographic_segments"][str(seg_name)] = int(float(seg_val))
                except (ValueError, TypeError):
                    continue
            valid_entries.append(cleaned)

    # Sort by fiscal_year_end ascending
    valid_entries.sort(key=lambda x: x["fiscal_year_end"])
    return valid_entries


def fetch_revenue_segments(ticker: str, company_name: str) -> List[dict]:
    """Fetch revenue segment data for a company using LLM with web search grounding.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL').
        company_name: Full company name (e.g., 'Apple Inc.').

    Returns:
        List of dicts, each with keys: fiscal_year_end, product_segments, geographic_segments.
        Sorted by fiscal_year_end ascending.
    """
    client = get_llm_client()
    system_prompt, user_prompt = _build_segment_prompt(ticker, company_name)

    try:
        raw_response = client.query_json_with_search(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0
        )
    except json.JSONDecodeError as e:
        print(f"[segment_fetcher] JSON parse error for {ticker}: {e}")
        return []
    except Exception as e:
        print(f"[segment_fetcher] LLM query error for {ticker}: {e}")
        return []

    return _validate_and_clean_response(raw_response)
