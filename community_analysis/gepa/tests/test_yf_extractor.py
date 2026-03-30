import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from yf_extractor import fetch_stock_data

def test_fetch_stock_data_success():
    with patch('yf_extractor.yf.Ticker') as MockTicker:
        mock_stock = MagicMock()
        MockTicker.return_value = mock_stock
        
        # Mock price history
        mock_hist = pd.DataFrame({'Close': [100.0] * 501})
        mock_hist.iloc[0, 0] = 50.0
        mock_hist.iloc[-1, 0] = 150.0
        
        mock_future = pd.DataFrame({'Close': [150.0, 200.0]})
        
        # Return different dataframes based on arguments
        def history_side_effect(**kwargs):
            if kwargs.get('start') == "2014-03-01":
                return mock_hist
            return mock_future
            
        mock_stock.history.side_effect = history_side_effect
        
        # Mock info
        mock_stock.info = {
            'trailingPE': 20.5,
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'revenueGrowth': 0.15,
            'operatingMargins': 0.25
        }
        
        result = fetch_stock_data("AAPL", "2014-03-01", "2024-03-01", "2026-03-01")
        
        assert result["ticker"] == "AAPL"
        assert result["ten_year_return"] == 200.0  # (150-50)/50 * 100
        assert result["future_return"] == pytest.approx(33.33, 0.01) # (200-150)/150 * 100
        assert result["pe"] == 20.5
        assert result["sector"] == "Technology"
        assert result["industry"] == "Consumer Electronics"
        assert result["revenue_growth"] == 15.0
        assert result["margins"] == 25.0

def test_fetch_stock_data_insufficient_history():
    with patch('yf_extractor.yf.Ticker') as MockTicker:
        mock_stock = MagicMock()
        MockTicker.return_value = mock_stock
        mock_stock.history.return_value = pd.DataFrame({'Close': [100.0] * 100}) # Less than 500
        
        with pytest.raises(ValueError, match="Not enough history"):
            fetch_stock_data("FAIL", "2014-03-01", "2024-03-01", "2026-03-01")
