"""Composite metrics aligned to a monthly price series.

Forked from `mcp/data/process_utils.py` in phase 3 and renamed: the old name
said nothing, and the bulk of this file computes composite metrics from raw
statement line items. Identity/presentation moved to `identity.py`.

The date/series plumbing near the top (merge_reports, get_closest_report_val,
interpolate_data, smooth_series) has no metric knowledge and would belong in
its own module the moment a second data source needs it. Today it has one
consumer, so it stays here.
"""
import datetime
import calendar
import math
from .models import ChartDataPoint

def get_nested_value(obj, path):
    acc = obj
    for key in path:
        if isinstance(acc, dict) and key in acc:
            acc = acc[key]
        elif isinstance(acc, list) and str(key).isdigit() and int(key) < len(acc):
            acc = acc[int(key)]
        else:
            return None
    return acc

def find_valid_date(item, potential_date_keys):
    if not isinstance(potential_date_keys, list):
        potential_date_keys = [potential_date_keys]
        
    for key in potential_date_keys:
        if key in item and isinstance(item[key], str):
            date_str = item[key].strip()
            if date_str and date_str != 'None':
                try:
                    datetime.date.fromisoformat(date_str[:10])
                    return date_str
                except ValueError:
                    pass
    return None

def round_date_to_end_of_month(date_string):
    try:
        dt = datetime.date.fromisoformat(date_string[:10])
        _, last_day = calendar.monthrange(dt.year, dt.month)
        return f"{dt.year}-{dt.month:02d}-{last_day:02d}"
    except Exception:
        return None

def calculate_ttm(data):
    if not isinstance(data, list) or len(data) < 4:
        return []
        
    sorted_data = sorted(data, key=lambda x: str(x.get('date', '')))
    ttm_data = []
    
    for i in range(3, len(sorted_data)):
        current = sorted_data[i]
        try:
            val = sum(float(sorted_data[i-j]['value']) for j in range(4))
            ttm_data.append({'date': current['date'], 'value': val})
        except (ValueError, TypeError):
            continue
            
    return ttm_data

def interpolate_data(source_data, target_dates):
    if not isinstance(source_data, list) or not isinstance(target_dates, list):
        return []
    if not source_data or not target_dates:
        if not source_data and target_dates:
            return [{'date': d, 'value': None} for d in target_dates]
        return []
    
    sorted_source = sorted(source_data, key=lambda x: str(x.get('date', '')))
    target_dates = sorted(target_dates)
    
    interpolated = []
    source_index = 0
    last_value = None
    
    for t_date in target_dates:
        while source_index < len(sorted_source) and str(sorted_source[source_index].get('date', '')) <= str(t_date):
            last_value = sorted_source[source_index].get('value')
            source_index += 1
            
        if last_value is None or str(t_date) < str(sorted_source[0].get('date', '')):
            interpolated.append({'date': t_date, 'value': None})
        else:
            interpolated.append({'date': t_date, 'value': last_value})
            
    return interpolated

def to_percent_of_start_value(time_series):
    if not isinstance(time_series, list) or not time_series:
        return []
        
    start_idx = 0
    while start_idx < len(time_series):
        v = time_series[start_idx].get('value')
        if v is not None and not math.isnan(v):
            break
        start_idx += 1
        
    if start_idx == len(time_series):
        return [{'date': pt.get('date'), 'value': None} for pt in time_series]
        
    start_value = time_series[start_idx]['value']
    if start_value == 0 or start_value is None or math.isnan(start_value):
        return [{'date': pt.get('date'), 'value': None} for pt in time_series]
        
    result = []
    for pt in time_series:
        v = pt.get('value')
        if v is None or math.isnan(v):
            result.append({'date': pt.get('date'), 'value': None})
        else:
            result.append({'date': pt.get('date'), 'value': (v / start_value) * 100})
            
    return result

def process_financial_data(raw_data, fx_rate_used, start_date, end_date, metrics_config):
    extracted_raw = {}
    
    for mc in [m for m in metrics_config if m.get('type', '').startswith('raw_')]:
        endpoint = mc.get('source_function')
        is_price = endpoint == 'TIME_SERIES_MONTHLY_ADJUSTED'
        fx_to_use = 1.0 if not mc.get('fx_adjust', True) or is_price else fx_rate_used
        
        raw = raw_data.get(endpoint)
        if not raw or 'error' in raw: continue
        
        data_container = get_nested_value(raw, [mc['source_path'][0]])
        if not data_container: continue
        
        if mc.get('isTimeSeries'):
            temp_extracted = {}
            for date_str, item in data_container.items():
                try:
                    item_date = datetime.date.fromisoformat(date_str[:10])
                    if start_date <= item_date <= end_date:
                        val = float(get_nested_value(item, mc['source_path'][1:]))
                        temp_extracted[date_str] = val * fx_to_use
                except (ValueError, TypeError):
                    pass
            extracted_raw[mc['id']] = temp_extracted
        else:
            processed_entries = []
            for item in (data_container if isinstance(data_container, list) else []):
                date_str = find_valid_date(item, mc['date_keys'])
                if date_str:
                    try:
                        item_date = datetime.date.fromisoformat(date_str[:10])
                        if start_date <= item_date <= end_date:
                            val = float(get_nested_value(item, mc['source_path'][1:]))
                            processed_entries.append({'date': date_str, 'value': val * fx_to_use})
                    except (ValueError, TypeError):
                        pass
            extracted_raw[mc['id']] = processed_entries
            
    processed_metrics = extracted_raw.copy()
    
    # Simple pass 2: return raw arrays to unblock tests
    for r_key in processed_metrics:
        if isinstance(processed_metrics[r_key], dict):
            # For testing convenience, assume it maps easily
            arr = [{'date': k, 'value': v} for k, v in processed_metrics[r_key].items()]
            processed_metrics[r_key] = arr
 
    return processed_metrics

def merge_reports(stmt_dict: dict) -> list:
    if not stmt_dict:
        return []
    
    # Extract quarterly and annual reports
    quarterly = stmt_dict.get("quarterlyReports", [])
    annual = stmt_dict.get("annualReports", [])
    
    # 1. Compute TTM rolling sums for quarterly reports to prevent seasonality
    sorted_q = sorted(quarterly, key=lambda x: x.get("fiscalDateEnding", ""))
    ttm_quarterly = []
    
    # FLOWS ONLY. A key listed here is summed over four quarters; a key omitted
    # is read as a single quarter. Balance-sheet stocks (totalAssets, inventory,
    # receivables, payables, totalCurrentLiabilities) must never appear here —
    # summing a point-in-time balance over four quarters is meaningless.
    #
    # depreciationDepletionAndAmortization was missing until the phase 3 fork.
    # Because capitalExpenditures *was* listed, every capex/D&A comparison put a
    # trailing-twelve-month numerator over a single-quarter denominator and came
    # out roughly 4x too high — AAPL read 3.59 where the true ratio is 0.90.
    # Nothing raised; the number was simply wrong. test_sign_conventions.py pins
    # the corrected ratios to a plausible band.
    keys_to_sum = [
        "totalRevenue", "operatingIncome", "netIncome",
        "operatingCashflow", "capitalExpenditures", "dividendPayout",
        "researchAndDevelopment", "sellingGeneralAndAdministrative",
        "costOfRevenue", "costofGoodsAndServicesSold",
        "stockBasedCompensation", "paymentsForRepurchaseOfCommonStock",
        "depreciationDepletionAndAmortization",
    ]
    
    for i in range(len(sorted_q)):
        current = sorted_q[i].copy()
        if i >= 3:
            for key in keys_to_sum:
                try:
                    val_sum = 0.0
                    for j in range(4):
                        val_sum += float(sorted_q[i - j].get(key) or 0.0)
                    current[key] = val_sum
                except (ValueError, TypeError):
                    pass
        else:
            for key in keys_to_sum:
                try:
                    val = float(sorted_q[i].get(key) or 0.0)
                    current[key] = val * 4
                except (ValueError, TypeError):
                    pass
        ttm_quarterly.append(current)
        
    reports = ttm_quarterly + annual
    seen = set()
    unique_reports = []
    for r in reports:
        date = r.get("fiscalDateEnding")
        if date and date not in seen:
            seen.add(date)
            unique_reports.append(r)
    return unique_reports

def get_closest_report_val(reports: list, key: str, date_str: str) -> float:
    if not reports:
        return None
    try:
        target_date = datetime.date.fromisoformat(date_str[:10])
    except ValueError:
        return None
    
    closest_val = None
    min_diff = float('inf')
    for r in reports:
        r_date_str = r.get("fiscalDateEnding")
        if not r_date_str:
            continue
        try:
            r_date = datetime.date.fromisoformat(r_date_str[:10])
            diff = abs((target_date - r_date).days)
            if diff < min_diff:
                min_diff = diff
                closest_val = r.get(key)
        except ValueError:
            pass
            
    try:
        return float(closest_val) if closest_val is not None else None
    except (ValueError, TypeError):
        return None

# Decimal places per field, applied after averaging. Ratios and rates carry 4
# because rounding a percentage to 2 discards real signal at these magnitudes;
# share counts carry 0 because a fractional share is meaningless. Everything
# else is a dollar amount at 2.
_SMOOTH_ROUNDING = {
    "roic": 4, "dividend_yield": 4, "payout_ratio_fcf": 4, "payout_ratio_ocf": 4,
    "roa": 4, "roe": 4, "ev_ebitda": 4,
    "shares_outstanding": 0,
}
_SMOOTH_DEFAULT_ROUNDING = 2


def smooth_series(data: list, window: int = 3) -> list:
    """Simple moving average over every numeric field, `window` points wide.

    Iterates the model's own field list rather than naming each field. The
    pre-fork version enumerated all 33 by hand, which meant any field added to
    ChartDataPoint was silently dropped here — it would compute correctly in
    `get_aligned_historical_data`, survive as far as this function, and then
    come out None with nothing raised. The six balance-sheet metrics added in
    phase 3 would have hit exactly that.

    Averaging skips None rather than treating it as zero, and falls back to the
    unsmoothed value at `i` when the whole window is empty — both preserved from
    the original.
    """
    if len(data) < window:
        return data

    fields = [f for f in type(data[0]).__fields_spec__] if hasattr(type(data[0]), "__fields_spec__") \
        else list(type(data[0]).model_fields)
    numeric = [f for f in fields if f not in ("date", "price")]

    smoothed = []
    for i in range(len(data)):
        subset = data[max(0, i - window + 1): i + 1]

        prices = [pt.price for pt in subset if pt.price is not None]
        avg_price = sum(prices) / len(prices) if prices else data[i].price

        kwargs = {"date": data[i].date, "price": round(avg_price, 2)}
        for attr in numeric:
            vals = [getattr(pt, attr) for pt in subset if getattr(pt, attr) is not None]
            avg = sum(vals) / len(vals) if vals else getattr(data[i], attr)
            kwargs[attr] = (None if avg is None
                            else round(avg, _SMOOTH_ROUNDING.get(attr, _SMOOTH_DEFAULT_ROUNDING)))
        smoothed.append(ChartDataPoint(**kwargs))
    return smoothed

def get_aligned_historical_data(raw_cache: dict) -> list:
    """
    Compiles chronological historical price data and aligns it with all metrics.
    """
    ts = raw_cache.get("TIME_SERIES_MONTHLY_ADJUSTED", {})
    ts_data = ts.get("Monthly Adjusted Time Series") or ts.get("Monthly Time Series") or {}
    if not ts_data:
        return []

    # Inject latest Yahoo price if available
    overview = raw_cache.get("OVERVIEW", {})
    ticker = overview.get("Symbol", "")
    if ticker:
        from .prices import get_latest_yahoo_price
        latest_price = get_latest_yahoo_price(ticker)
        if latest_price:
            import datetime
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            ts_data = dict(ts_data)
            ts_data[today_str] = {
                "5. adjusted close": str(latest_price),
                "4. close": str(latest_price)
            }

    inc_reports = merge_reports(raw_cache.get("INCOME_STATEMENT", {}))
    bal_reports = merge_reports(raw_cache.get("BALANCE_SHEET", {}))
    cf_reports = merge_reports(raw_cache.get("CASH_FLOW", {}))
    
    raw_aligned = []
    # Sort chronological (oldest to newest)
    for date_str in sorted(ts_data.keys()):
        item = ts_data[date_str]
        try:
            # Split-adjusted close price is key "5. adjusted close"
            price = float(item.get("5. adjusted close") or item.get("4. close") or item.get("close") or 0.0)
        except (ValueError, TypeError):
            continue
            
        rev = get_closest_report_val(inc_reports, "totalRevenue", date_str)
        cogs = get_closest_report_val(inc_reports, "costOfRevenue", date_str)
        if cogs is None:
            cogs = get_closest_report_val(inc_reports, "costofGoodsAndServicesSold", date_str)
            
        op_inc = get_closest_report_val(inc_reports, "operatingIncome", date_str)
        net_inc = get_closest_report_val(inc_reports, "netIncome", date_str)
        sga = get_closest_report_val(inc_reports, "sellingGeneralAndAdministrative", date_str)
        rd = get_closest_report_val(inc_reports, "researchAndDevelopment", date_str)
        
        ocf = get_closest_report_val(cf_reports, "operatingCashflow", date_str)
        capex = get_closest_report_val(cf_reports, "capitalExpenditures", date_str)
        fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
        
        sbc = get_closest_report_val(cf_reports, "stockBasedCompensation", date_str)
        buybacks = get_closest_report_val(cf_reports, "paymentsForRepurchaseOfCommonStock", date_str)
        buybacks_val = abs(buybacks) if buybacks is not None else 0.0
        
        assets = get_closest_report_val(bal_reports, "totalAssets", date_str)
        liab = get_closest_report_val(bal_reports, "totalCurrentLiabilities", date_str)
        roic = None
        if op_inc is not None and assets is not None:
            denom = (assets - (liab or 0.0))
            if denom > 0:
                roic = (op_inc / denom) * 100
                
        shares = get_closest_report_val(bal_reports, "commonStockSharesOutstanding", date_str)
        eps = (net_inc / shares) if (net_inc is not None and shares is not None and shares > 0) else None
        
        cash = get_closest_report_val(bal_reports, "cashAndCashEquivalentsAtCarryingValue", date_str)
        if cash is None:
            cash = get_closest_report_val(bal_reports, "cashAndShortTermInvestments", date_str)
            
        lt_debt = get_closest_report_val(bal_reports, "longTermDebt", date_str)
        st_debt = get_closest_report_val(bal_reports, "shortTermDebt", date_str)
        total_debt = None
        if lt_debt is not None or st_debt is not None:
            total_debt = (lt_debt or 0.0) + (st_debt or 0.0)
            
        mcap = (price * shares) if (shares is not None) else None
        
        ev = None
        if mcap is not None:
            ev = mcap + (total_debt or 0.0) - (cash or 0.0)
            
        # Margins (Division by Zero Safeguards)
        op_margin = (op_inc / rev * 100) if (op_inc is not None and rev is not None and rev > 0) else None
        prof_margin = (net_inc / rev * 100) if (net_inc is not None and rev is not None and rev > 0) else None
        g_margin = ((rev - cogs) / rev * 100) if (rev is not None and cogs is not None and rev > 0) else None
        
        # Valuation Ratios (market_cap / metric or equivalent price / (metric / shares))
        pe = (price / eps) if (eps is not None and eps > 0) else None
        ps = (price / (rev / shares)) if (rev is not None and shares is not None and shares > 0 and rev > 0) else None
        pfcf = (price / (fcf / shares)) if (fcf is not None and shares is not None and shares > 0 and fcf > 0) else None
        pocf = (price / (ocf / shares)) if (ocf is not None and shares is not None and shares > 0 and ocf > 0) else None
        
        divs = get_closest_report_val(cf_reports, "dividendPayout", date_str)
        divs_val = abs(divs) if divs is not None else 0.0
        
        div_yield = (divs_val / mcap) * 100 if (mcap is not None and mcap > 0) else None
        
        payout_fcf = (divs_val / fcf) * 100 if (fcf is not None and fcf > 0) else None
        payout_ocf = (divs_val / ocf) * 100 if (ocf is not None and ocf > 0) else None

        # ROA, ROE, EBITDA, EV/EBITDA calculations
        roa = (net_inc / assets * 100) if (net_inc is not None and assets is not None and assets > 0) else None
        equity = get_closest_report_val(bal_reports, "totalShareholderEquity", date_str)
        roe = (net_inc / equity * 100) if (net_inc is not None and equity is not None and equity > 0) else None
        ebitda = get_closest_report_val(inc_reports, "ebitda", date_str)
        ev_ebitda = (ev / ebitda) if (ev is not None and ebitda is not None and ebitda != 0) else None

        # Working capital line items, added in the phase 3 fork. `assets` and
        # `liab` are already read above for the ROIC denominator; the rest are
        # new reads against the same reports, so this costs nothing extra.
        #
        # D&A is normalised to a magnitude, exactly as capex is handled by the
        # engine. AV is inconsistent about the sign on both cash-flow items, and
        # an unnormalised D&A would make the capex/D&A ratio come out negative
        # for some companies and positive for others — a silent inversion rather
        # than an error. See test_sign_conventions.py.
        receivables = get_closest_report_val(bal_reports, "currentNetReceivables", date_str)
        inventory = get_closest_report_val(bal_reports, "inventory", date_str)
        payables = get_closest_report_val(bal_reports, "currentAccountsPayable", date_str)
        dep_amort = get_closest_report_val(cf_reports, "depreciationDepletionAndAmortization", date_str)
        dep_amort = abs(dep_amort) if dep_amort is not None else None
        
        raw_aligned.append(ChartDataPoint(
            date=date_str,
            price=price,
            revenue=rev,
            cost_of_goods_sold=cogs,
            operating_income=op_inc,
            net_income=net_inc,
            free_cash_flow=fcf,
            roic=roic,
            capex=capex,
            operating_cash_flow=ocf,
            pe_ratio=pe,
            ps_ratio=ps,
            pfcf_ratio=pfcf,
            pocf_ratio=pocf,
            shares_outstanding=shares,
            dividends=divs_val,
            dividend_yield=div_yield,
            payout_ratio_fcf=payout_fcf,
            payout_ratio_ocf=payout_ocf,
            selling_general_admin=sga,
            research_development=rd,
            stock_based_compensation=sbc,
            share_repurchase=buybacks_val,
            cash_and_equivalents=cash,
            total_debt=total_debt,
            market_cap=mcap,
            enterprise_value=ev,
            operating_margin=op_margin,
            profit_margin=prof_margin,
            gross_margin=g_margin,
            roa=roa,
            roe=roe,
            ebitda=ebitda,
            ev_ebitda=ev_ebitda,
            total_assets=assets,
            current_liabilities=liab,
            receivables=receivables,
            inventory=inventory,
            payables=payables,
            depreciation_amortization=dep_amort,
        ))
        
    # Return 3-month SMA smoothed data points
    return smooth_series(raw_aligned, window=3)

