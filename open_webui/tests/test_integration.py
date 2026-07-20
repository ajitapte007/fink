import os
import sys
import time
import json
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Setup PYTHONPATH for testing
test_dir = Path(__file__).parent.resolve()
root_dir = test_dir.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Configure temporary SQLite Cache DB for tests
TEST_DB_PATH = str(test_dir / "test_cache.db")
os.environ["ALPHAVANTAGE_CACHE_DB"] = TEST_DB_PATH

# Import modules after env config
from alphavantage import fetch_utils
from alphavantage import process_utils
from data_pipe import Pipe

@pytest.fixture(autouse=True)
def clean_db():
    """Fixture to ensure database is clean before and after each test."""
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    fetch_utils.init_db()
    yield
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

def test_sqlite_read_through_cache():
    """Verify writing, reading, and caching in the SQLite DB."""
    symbol = "TESTSYM"
    func = "OVERVIEW"
    mock_data = {"Symbol": symbol, "Name": "Test Company", "Sector": "Technology"}
    
    # Verify initially cache is empty
    assert fetch_utils.get_db_cache(symbol, func) is None
    
    # Set cache and check hit
    fetch_utils.set_db_cache(symbol, func, mock_data)
    cached = fetch_utils.get_db_cache(symbol, func)
    assert cached is not None
    assert cached["Symbol"] == symbol
    assert cached["Name"] == "Test Company"

def test_sqlite_ttl_expiration():
    """Verify that records older than 24 hours expire and trigger a refresh."""
    symbol = "TESTSYM"
    func = "OVERVIEW"
    stale_data = {"Symbol": symbol, "Status": "Stale"}
    fresh_data = {"Symbol": symbol, "Status": "Fresh"}
    
    # Insert stale record manually with timestamp > 24 hours ago
    db_path = fetch_utils.get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO av_cache (symbol, function, data, timestamp) VALUES (?, ?, ?, ?)",
        (symbol, func, json.dumps(stale_data), time.time() - 90000) # 25 hours ago
    )
    conn.commit()
    conn.close()
    
    # 24h TTL cache lookup should fail/expire
    assert fetch_utils.get_db_cache(symbol, func, ttl_seconds=86400) is None
    
    # Running get_av_data should trigger network fetch since cache is expired
    with patch("alphavantage.fetch_utils.fetch_data", return_value=fresh_data) as mock_fetch:
        res = fetch_utils.get_av_data(symbol, func, ttl_seconds=86400)
        assert mock_fetch.call_count == 1
        assert res["Status"] == "Fresh"

def test_offline_local_json_fallback():
    """Verify that failing network requests fallback to the pre-seeded JSON cache files."""
    symbol = "AMZN" # Pre-seeded in local_av_cache/
    func = "OVERVIEW"
    
    # Simulate network error
    with patch("alphavantage.fetch_utils.fetch_data", side_effect=Exception("Network Offline")):
        # Should fall back to the pre-seeded AMZN.json file
        data = fetch_utils.get_av_data(symbol, func)
        assert data is not None
        assert data["Symbol"] == "AMZN"
        assert "Amazon.com, Inc." in data["Description"]

def test_monthly_to_daily_mapping_fallback():
    """Verify mapping monthly adjusted data to simulate daily series when daily series is missing."""
    symbol = "UNH"
    
    # Request daily data. UNH.json only contains monthly adjusted data.
    # Check that it falls back, translates keys, and maps close price.
    with patch("alphavantage.fetch_utils.fetch_data", side_effect=Exception("API Limit / Offline")):
        data = fetch_utils.get_av_data(symbol, "TIME_SERIES_DAILY")
        assert data is not None
        assert "Time Series (Daily)" in data
        assert symbol in data["Meta Data"]["2. Symbol"]
        
        daily_series = data["Time Series (Daily)"]
        assert len(daily_series) > 0
        
        # Verify fields are mapped to daily format
        sample_date = list(daily_series.keys())[0]
        assert "4. close" in daily_series[sample_date]

def test_user_preferences_extraction():
    """Verify pre-flight Gemini extraction mappings (active vs dormant intent and preferences JSON)."""
    pipe = Pipe()
    pipe.valves.GEMINI_API_KEY = "dummy_key"
    
    # Mock pre-flight LLM call returning a preferences JSON
    mock_choices = [MagicMock()]
    mock_choices[0].message.content = '{"ticker": "AAPL", "is_financial_query": true, "metrics": ["price", "pe_ratio"], "start_date": "2021-07-20", "end_date": "2026-07-20"}'
    mock_response = MagicMock()
    mock_response.choices = mock_choices
    
    with patch("openai.resources.chat.completions.Completions.create", return_value=mock_response) as mock_create:
        prefs = pipe.extract_user_preferences([{"role": "user", "content": "Explain Apple's margins over 5 years"}], "dummy_key")
        assert mock_create.call_count == 1
        assert prefs["ticker"] == "AAPL"
        assert prefs["is_financial_query"] is True
        assert prefs["start_date"] == "2021-07-20"
        assert prefs["end_date"] == "2026-07-20"
        assert "price" in prefs["metrics"]
        
    # Mock pre-flight LLM call returning a dormant intent (null ticker)
    mock_choices[0].message.content = '{"ticker": null, "is_financial_query": false, "metrics": ["price", "pe_ratio"], "start_date": null, "end_date": null}'
    with patch("openai.resources.chat.completions.Completions.create", return_value=mock_response) as mock_create:
        prefs = pipe.extract_user_preferences([{"role": "user", "content": "How is the weather?"}], "dummy_key")
        assert prefs["ticker"] is None
        assert prefs["is_financial_query"] is False
        assert prefs["start_date"] is None
        assert prefs["end_date"] is None

def test_payload_and_prompt_injection():
    """Verify that metadata context and system prompts are injected correctly in the active state."""
    pipe = Pipe()
    pipe.valves.GEMINI_API_KEY = "dummy_key"
    pipe.valves.ALPHAVANTAGE_API_KEY = "dummy_av_key"
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about AAPL"}
    ]
    
    # Mock preference extraction to return AAPL active state
    with patch.object(pipe, "extract_user_preferences", return_value={"ticker": "AAPL", "is_financial_query": True, "metrics": ["price", "pe_ratio"], "start_date": None, "end_date": None}):
        # Mock fetch_utils calls to avoid network hit
        mock_raw = {
            "OVERVIEW": {"Symbol": "AAPL", "AssetType": "Common Stock"},
            "TIME_SERIES_MONTHLY_ADJUSTED": {},
            "INCOME_STATEMENT": {},
            "BALANCE_SHEET": {},
            "CASH_FLOW": {}
        }
        with patch("alphavantage.fetch_utils.get_all_data_for_ticker", return_value=mock_raw):
            # Process aligned data should return a basic list of ChartDataPoints
            from models import ChartDataPoint
            mock_point = ChartDataPoint(date="2026-07-01", price=150.0)
            with patch("alphavantage.process_utils.get_aligned_historical_data", return_value=[mock_point]):
                # Mock the final LLM stream call
                mock_delta = MagicMock()
                mock_delta.content = "Final Analysis Output"
                mock_chunk = MagicMock()
                mock_chunk.choices = [MagicMock()]
                mock_chunk.choices[0].delta = mock_delta
                
                with patch("openai.resources.chat.completions.Completions.create", return_value=[mock_chunk]) as mock_completions:
                    body = {
                        "messages": messages,
                        "model": "model_id"
                    }
                    generator = pipe.pipe(body)
                    response_text = "".join(list(generator))
                    
                    # assert "Final Analysis Output" in response_text
                    assert '/static/chart-aapl.html' in response_text
                    
                    # Verify user message has the payload injected
                    user_msg = messages[-1]["content"]
                    assert "[DATA OVERRIDE LAYER]" in user_msg
                    assert '"ticker": "AAPL"' in user_msg
                    
                    # Verify system instruction was injected
                    sys_msg = messages[0]["content"]
                    assert "You are a professional financial due diligence analyst." in sys_msg
                    assert "Do NOT output any HTML blocks" in sys_msg

def test_missing_ticker_clarification():
    """Verify that a financial query with a missing ticker yields a clarification request."""
    pipe = Pipe()
    pipe.valves.GEMINI_API_KEY = "dummy_key"
    pipe.valves.ALPHAVANTAGE_API_KEY = "dummy_av_key"
    
    messages = [
        {"role": "user", "content": "plot price and pe ratio"}
    ]
    
    # Mock preference extraction to return missing ticker but is_financial_query=True
    with patch.object(pipe, "extract_user_preferences", return_value={"ticker": None, "is_financial_query": True, "metrics": ["price", "pe_ratio"], "start_date": None, "end_date": None}):
        body = {
            "messages": messages,
            "model": "model_id"
        }
        generator = pipe.pipe(body)
        response_text = "".join(list(generator))
        assert "specify which stock ticker symbol" in response_text

def test_faked_general_conversation():
    """Verify that a general conversation query returns the faked placeholder response."""
    pipe = Pipe()
    pipe.valves.GEMINI_API_KEY = "dummy_key"
    pipe.valves.ALPHAVANTAGE_API_KEY = "dummy_av_key"
    
    messages = [
        {"role": "user", "content": "how is the weather?"}
    ]
    
    # Mock preference extraction to return dormant state
    with patch.object(pipe, "extract_user_preferences", return_value={"ticker": None, "is_financial_query": False, "metrics": ["price", "pe_ratio"], "start_date": None, "end_date": None}):
        body = {
            "messages": messages,
            "model": "model_id"
        }
        generator = pipe.pipe(body)
        response_text = "".join(list(generator))
        assert "Gemini text analysis disabled for testing" in response_text
