# mcp/tests/test_cache_flow.py
# sys.path is handled by conftest.py.
import time
import sqlite3

from data.fetch_utils import get_av_data, init_db, get_db_path

def test_sqlite_cache_and_metadata():
    """
    Verifies that calling get_av_data properly records and retrieves:
    - expires_at and source columns
    - populates SQLite read-through cache
    - loads locally in offline mode (mock_data=True)
    """
    init_db()
    db_path = get_db_path()
    
    # Clean previous records for UNH to ensure clean state
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM av_cache WHERE symbol = 'UNH'")
    conn.commit()
    conn.close()
    
    # 1. Fetch data with mock_data enabled (offline-first)
    res = get_av_data("UNH", "OVERVIEW", mock_data=True)
    
    assert "data" in res
    assert res["source"] == "mock"
    assert res["expires_at"] > res["timestamp"]
    assert isinstance(res["data"], dict)
    assert res["data"].get("Symbol") == "UNH"
    
    # 2. Check that database cache table has the metadata entries
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, expires_at, source FROM av_cache WHERE symbol = 'UNH' AND function = 'OVERVIEW'"
    )
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    timestamp, expires_at, source = row
    assert source == "mock"
    assert expires_at > timestamp
    
    # 3. Read again (should hit active SQLite cache directly)
    res_second = get_av_data("UNH", "OVERVIEW", mock_data=True)
    assert res_second["source"] == "mock"
    assert res_second["timestamp"] == timestamp
    
    print("\ntest_sqlite_cache_and_metadata PASSED successfully!")

def test_cache_corruptness_and_sync_refetch():
    from data.fetch_utils import set_db_cache, get_db_cache, is_ticker_cache_corrupt, get_all_data_for_ticker
    import sqlite3
    
    init_db()
    db_path = get_db_path()
    
    # 1. Clear UNH cache
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM av_cache WHERE symbol = 'UNH'")
    conn.commit()
    conn.close()
    
    # 2. Set one of the functions as corrupt
    set_db_cache("UNH", "OVERVIEW", {"dummy": "data"}, time.time(), time.time() + 86400, "mock", is_corrupt=1)
    assert is_ticker_cache_corrupt("UNH") is True
    
    # 3. Call get_all_data_for_ticker which should trigger global cache refresh and sync refetch
    # (since mock_data=True, it will repopulate all 5 clean functions from UNH.json)
    res = get_all_data_for_ticker("UNH", mock_data=True)
    assert not res["_meta_corrupt_functions"]
    
    # 4. Assert all cache entries are now healthy (is_corrupt = 0)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT function, is_corrupt FROM av_cache WHERE symbol = 'UNH'")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) == 5
    for func, is_corrupt in rows:
        assert is_corrupt == 0
        
    # 5. Simulate network failure on corrupt/expired cache and check fallback preservation
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM av_cache WHERE symbol = 'UNH'")
    conn.commit()
    conn.close()
    
    set_db_cache("UNH", "OVERVIEW", {"Error Message": "Fail"}, time.time(), time.time() + 86400, "api", is_corrupt=1)

    # Force the network call to fail explicitly rather than relying on the absence of
    # ALPHAVANTAGE_API_KEY. This test previously passed only because no key was set in
    # the environment; once one is present the fetch succeeds, overwrites the corrupt
    # record, and the assertion breaks for reasons unrelated to the cache logic.
    import data.fetch_utils as fetch_utils

    def _boom(function, symbol):
        raise ConnectionError("simulated network failure")

    original_fetch = fetch_utils.fetch_data
    fetch_utils.fetch_data = _boom
    try:
        # Should fall back to the cached corrupt record and preserve is_corrupt=1
        res_failed = get_all_data_for_ticker("UNH", mock_data=False)
    finally:
        fetch_utils.fetch_data = original_fetch

    assert "OVERVIEW" in res_failed["_meta_corrupt_functions"]

if __name__ == "__main__":
    test_sqlite_cache_and_metadata()
    test_cache_corruptness_and_sync_refetch()
