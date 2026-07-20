import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pytest
import datetime
import math
from alphavantage.process_utils import (
    round_date_to_end_of_month,
    get_nested_value,
    calculate_ttm,
    interpolate_data,
    process_financial_data,
    to_percent_of_start_value
)

def test_round_date_to_end_of_month():
    assert round_date_to_end_of_month('2023-05-15') == '2023-05-31'
    assert round_date_to_end_of_month('2023-02-28') == '2023-02-28'
    assert round_date_to_end_of_month('not a real date') is None

def test_get_nested_value():
    test_obj = {'a': {'b': {'c': 123}, 'd': [{'e': 456}]}}
    assert get_nested_value(test_obj, ['a', 'b', 'c']) == 123
    assert get_nested_value(test_obj, ['a', 'd', '0', 'e']) == 456
    assert get_nested_value(test_obj, ['a', 'x', 'y']) is None

def test_calculate_ttm():
    quarterly = [
        {'date': '2023-03-31', 'value': 1.0},
        {'date': '2023-06-30', 'value': 1.1},
        {'date': '2023-09-30', 'value': 1.2},
        {'date': '2023-12-31', 'value': 1.3},
        {'date': '2024-03-31', 'value': 1.4}
    ]
    ttm = calculate_ttm(quarterly)
    assert len(ttm) == 2
    assert math.isclose(ttm[0]['value'], 4.6)
    assert math.isclose(ttm[1]['value'], 5.0)
    assert ttm[1]['date'] == '2024-03-31'
    assert calculate_ttm(quarterly[:3]) == []

def test_interpolate_data():
    annual = [{'date': '2022-12-31', 'value': 100}, {'date': '2023-12-31', 'value': 200}]
    targets = ['2022-11-30', '2022-12-31', '2023-01-31', '2023-12-31']
    interpolated = interpolate_data(annual, targets)
    assert interpolated[0]['value'] is None
    assert interpolated[1]['value'] == 100
    assert interpolated[2]['value'] == 100
    assert interpolated[3]['value'] == 200

def test_process_financial_data():
    metrics_config = [
        {
            'id': 'price',
            'type': 'raw_time_series',
            'source_function': 'TIME_SERIES_MONTHLY_ADJUSTED',
            'source_path': ['Monthly Adjusted Time Series', '5. adjusted close'],
            'isTimeSeries': True,
            'is_plottable': True,
            'fx_adjust': False
        },
        {
            'id': 'annualRevenue',
            'type': 'raw_fundamental',
            'source_function': 'INCOME_STATEMENT',
            'source_path': ['annualReports', 'totalRevenue'],
            'date_keys': 'fiscalDateEnding',
            'isTimeSeries': False,
            'is_plottable': True,
            'fx_adjust': True
        }
    ]
    raw_data = {
        'TIME_SERIES_MONTHLY_ADJUSTED': {
            'Monthly Adjusted Time Series': {
                '2023-01-31': {'5. adjusted close': '100'},
                '2023-02-28': {'5. adjusted close': '110'}
            }
        },
        'INCOME_STATEMENT': {
            'annualReports': [
                {'fiscalDateEnding': '2023-01-31', 'totalRevenue': '200', 'reportedCurrency': 'EUR'},
                {'fiscalDateEnding': '2023-02-28', 'totalRevenue': '220', 'reportedCurrency': 'EUR'}
            ]
        }
    }
    processed = process_financial_data(raw_data, 1.2, datetime.date(2023, 1, 31), datetime.date(2023, 3, 31), metrics_config)
    assert processed['annualRevenue'][0]['value'] == pytest.approx(240.0)
    assert processed['annualRevenue'][1]['value'] == pytest.approx(264.0)

def test_to_percent_of_start_value():
    series = [{'date': 'x', 'value': 10}, {'date': 'y', 'value': 20}]
    output = to_percent_of_start_value(series)
    assert output[0]['value'] == 100
    assert output[1]['value'] == 200

def test_smooth_series_and_alignment():
    from alphavantage.process_utils import get_aligned_historical_data, smooth_series
    from models import ChartDataPoint
    
    # Test SMA smoothing
    data = [
        ChartDataPoint(date="2023-01-31", price=100.0, revenue=10.0),
        ChartDataPoint(date="2023-02-28", price=110.0, revenue=20.0),
        ChartDataPoint(date="2023-03-31", price=120.0, revenue=30.0),
    ]
    smoothed = smooth_series(data, window=3)
    assert len(smoothed) == 3
    # 2023-03-31 should be the average of [100, 110, 120] = 110
    assert smoothed[2].price == 110.0
    # and revenue should be average of [10, 20, 30] = 20
    assert smoothed[2].revenue == 20.0

    # Test alignment with mocked raw cache
    raw_cache = {
        "TIME_SERIES_MONTHLY_ADJUSTED": {
            "Monthly Adjusted Time Series": {
                "2023-01-31": {"5. adjusted close": "100.0"},
                "2023-02-28": {"5. adjusted close": "110.0"},
                "2023-03-31": {"5. adjusted close": "120.0"}
            }
        },
        "INCOME_STATEMENT": {
            "quarterlyReports": [
                {"fiscalDateEnding": "2023-03-31", "totalRevenue": "1000", "netIncome": "100"},
                {"fiscalDateEnding": "2022-12-31", "totalRevenue": "900", "netIncome": "90"},
                {"fiscalDateEnding": "2022-09-30", "totalRevenue": "800", "netIncome": "80"},
                {"fiscalDateEnding": "2022-06-30", "totalRevenue": "700", "netIncome": "70"}
            ]
        },
        "BALANCE_SHEET": {
            "quarterlyReports": [
                {"fiscalDateEnding": "2023-03-31", "commonStockSharesOutstanding": "50"}
            ]
        },
        "CASH_FLOW": {
            "quarterlyReports": [
                {"fiscalDateEnding": "2023-03-31", "operatingCashflow": "200", "capitalExpenditures": "50", "dividendPayout": "20"}
            ]
        }
    }
    
    aligned = get_aligned_historical_data(raw_cache)
    assert len(aligned) == 3
    # Check that commonStockSharesOutstanding and TTM calculations are mapped
    # 2023-03-31 has commonStockSharesOutstanding = 50.0
    # Net income TTM = 100 + 90 + 80 + 70 = 340.0
    # EPS = 340.0 / 50.0 = 6.8
    # Operating Cash Flow TTM = 200 * 4 = 800.0 (since < 4 quarters available in CF reports)
    # capex = 50 * 4 = 200.0
    # Free Cash Flow = 600.0
    # pe_ratio = price / EPS = 110.0 / 6.8 = 16.18 (smoothed average price is 110.0)
    assert aligned[2].eps is not None
    assert aligned[2].pe_ratio is not None
    assert aligned[2].free_cash_flow is not None


def test_format_market_cap():
    from alphavantage.process_utils import format_market_cap
    assert format_market_cap(1.5e12) == "$1.50T"
    assert format_market_cap(2.5e9) == "$2.50B"
    assert format_market_cap(3.5e6) == "$3.50M"
    assert format_market_cap(150000) == "$150,000"


def test_get_corporate_identity():
    from alphavantage.process_utils import get_corporate_identity
    
    mock_cache = {
        "OVERVIEW": {
            "Symbol": "AAPL",
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
            "MarketCapitalization": "2850000000000"
        },
        "TIME_SERIES_MONTHLY_ADJUSTED": {
            "Monthly Adjusted Time Series": {
                "2023-01-31": {"5. adjusted close": "150.00"},
                "2023-02-28": {"5. adjusted close": "160.00"}
            }
        }
    }
    
    corp_id = get_corporate_identity(mock_cache)
    assert corp_id.ticker == "AAPL"
    assert corp_id.sector == "Technology"
    assert corp_id.industry == "Consumer Electronics"
    assert corp_id.market_cap == "$2.85T"
    assert corp_id.last_closing_price == "$160.00"


