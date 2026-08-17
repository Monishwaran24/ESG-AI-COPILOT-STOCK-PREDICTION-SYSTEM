"""
Indian Stock Exchange API (indianapi.in) Integration
=======================================================
Primary data source for Indian stocks (NSE/BSE).
Replaces Finnhub/TwelveData/yfinance for all Indian stock data.

API Key: Reads from INDIANAPI_API_KEY in .env or environment variables.
Free tier base URL: https://stock.indianapi.in
Auth: x-api-key header

API Docs: https://indianapi.in/documentation/indian-stock-market

Endpoints:
  /stock?name=RELIANCE        — Full company data, price, financials, metrics
  /historical_data?symbol=... — Historical price/volume data
  /historical_stats?stats=...  — Quarterly financial statements
  /stock_target_price?stock_id= — Analyst targets
  /stock_forecasts?stock_id=... — Earnings forecasts
  /trending                   — Top gainers/losers
  /industry_search?query=...  — Industry search

Usage:
    from model.indian_api import (
        is_indianapi_available,
        get_indianapi_stock_data,
        get_indianapi_historical_data,
        get_indianapi_financials,
        get_indianapi_key_metrics,
        get_indianapi_quote,
        get_indianapi_analyst_targets,
        get_indianapi_stock_forecasts,
        get_indianapi_trending,
    )
    data = get_indianapi_stock_data('RELIANCE')
    metrics = get_indianapi_key_metrics('RELIANCE')
"""

import os
import time
import json
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Base URLs by plan
INDIANAPI_BASE_URLS = {
    'free': 'https://stock.indianapi.in',
    'developer': 'https://dev.indianapi.in',
    'analyst': 'https://analyst.indianapi.in',
    'pro': 'https://pro.indianapi.in',
}
DEFAULT_BASE_URL = INDIANAPI_BASE_URLS['free']

# Ticker map (special characters)
NSE_TICKER_MAP = {
    'M_M': 'M&M',
    'BAJAJ_AUTO': 'BAJAJ-AUTO',
}

# Indian stock ticker set (Nifty 50 + large caps)
INDIAN_TICKERS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'SBIN',
    'BHARTIARTL', 'KOTAKBANK', 'BAJFINANCE', 'LT', 'WIPRO', 'AXISBANK', 'TITAN', 'MARUTI',
    'ASIANPAINT', 'HCLTECH', 'SUNPHARMA', 'NTPC', 'ONGC', 'POWERGRID', 'M_M', 'NESTLEIND',
    'ULTRACEMCO', 'HDFCLIFE', 'SBILIFE', 'DRREDDY', 'BAJAJFINSV', 'TECHM', 'BRITANNIA', 'DIVISLAB',
    'CIPLA', 'HINDALCO', 'TATASTEEL', 'JSWSTEEL', 'COALINDIA', 'ADANIPORTS', 'GRASIM', 'BPCL',
    'HEROMOTOCO', 'SHREECEM', 'INDUSINDBK', 'EICHERMOT', 'TATAMOTORS', 'UPL', 'BAJAJ_AUTO', 'MARICO',
    'TATACONSUM', 'DABUR', 'PIDILITIND', 'COLPAL', 'HAVELLS', 'ABB',
    'TORNTPHARM', 'SIEMENS', 'GODREJCP', 'TRENT', 'DLF', 'SRTRANSFIN', 'VEDL', 'JSWENERGY', 'GAIL',
]
INDIAN_TICKERS_SET = set(INDIAN_TICKERS)

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
_stock_cache = {}
_STOCK_CACHE_TTL = 300  # 5 minutes

_hist_cache = {}
_HIST_CACHE_TTL = 3600  # 1 hour

_fin_cache = {}
_FIN_CACHE_TTL = 86400  # 24 hours

_metrics_cache = {}
_METRICS_CACHE_TTL = 3600  # 1 hour

_quote_cache = {}
_QUOTE_CACHE_TTL = 300  # 5 minutes

_target_cache = {}
_TARGET_CACHE_TTL = 7200  # 2 hours

_forecast_cache = {}
_FORECAST_CACHE_TTL = 86400  # 24 hours

_trending_cache = {}
_TRENDING_CACHE_TTL = 300  # 5 minutes


def _get_cached(key, cache, ttl):
    now = time.time()
    if key in cache:
        val, ts = cache[key]
        if (now - ts) < ttl:
            return val
    return None


def _set_cache(key, value, cache):
    cache[key] = (value, time.time())
    if len(cache) > 200:
        cache.clear()


# ---------------------------------------------------------------------------
# API Key & Availability
# ---------------------------------------------------------------------------

def get_indianapi_key():
    """Get IndianAPI key from environment."""
    return os.environ.get('INDIANAPI_API_KEY', '').strip()


def get_indianapi_base_url():
    """Get the base URL from env or default to free tier."""
    return os.environ.get('INDIANAPI_BASE_URL', DEFAULT_BASE_URL)


def is_indianapi_available():
    """Check if IndianAPI key is configured."""
    key = get_indianapi_key()
    if not key or len(key) < 5:
        return False
    if 'your_' in key.lower() or 'placeholder' in key.lower():
        return False
    return True


def is_indian_ticker(ticker):
    """Check if a ticker is an Indian stock."""
    return ticker.upper() in INDIAN_TICKERS_SET


def get_nse_symbol(ticker):
    """Get the NSE trading symbol from internal ticker (handles M_M -> M&M)."""
    return NSE_TICKER_MAP.get(ticker, ticker)


# ---------------------------------------------------------------------------
# REST API Request
# ---------------------------------------------------------------------------

def _indianapi_request(endpoint, params=None, method='GET'):
    """
    Make a REST call to the IndianAPI.

    Args:
        endpoint: API endpoint like 'stock', 'historical_data'
        params: dict of query parameters
        method: HTTP method ('GET' or 'POST')

    Returns:
        dict with API response, or dict with 'error' key on failure
    """
    try:
        import requests
    except ImportError:
        return {'error': 'requests library not available'}

    api_key = get_indianapi_key()
    if not api_key:
        return {'error': 'No IndianAPI key configured'}

    base_url = get_indianapi_base_url()
    if params is None:
        params = {}

    url = f'{base_url}/{endpoint}'
    headers = {'x-api-key': api_key}

    try:
        if method == 'GET':
            resp = requests.get(url, params=params, headers=headers, timeout=20)
        else:
            resp = requests.post(url, json=params, headers=headers, timeout=20)

        if resp.status_code == 401:
            return {'error': 'Invalid IndianAPI key - check your key at indianapi.in'}
        if resp.status_code == 403:
            return {'error': 'IndianAPI key not authorized for this plan - upgrade or check base URL'}
        if resp.status_code == 429:
            return {'error': 'rate_limit', 'message': 'IndianAPI rate limit exceeded'}
        if not resp.ok:
            return {'error': f'HTTP {resp.status_code}', 'message': resp.text[:300]}

        data = resp.json()
        return data

    except requests.exceptions.Timeout:
        return {'error': 'IndianAPI timeout'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Cannot connect to IndianAPI - check base URL'}
    except Exception as e:
        return {'error': f'IndianAPI error: {str(e)}'}


# ---------------------------------------------------------------------------
# Stock Data (main endpoint - everything in one call)
# ---------------------------------------------------------------------------

def get_indianapi_stock_data(ticker):
    """
    Fetch full stock data for a company from IndianAPI.

    Uses the /stock endpoint which returns:
      - companyProfile, currentPrice (BSE/NSE), percentChange
      - yearHigh, yearLow, financials, keyMetrics
      - analystView, recosBar, riskMeter, shareholding
      - stockCorporateActionData, recentNews, etc.

    Args:
        ticker: NSE ticker symbol (e.g., 'RELIANCE', 'TCS')

    Returns:
        dict with full stock data, or None on failure
    """
    cache_key = f"ia_stock_{ticker.upper()}"
    cached = _get_cached(cache_key, _stock_cache, _STOCK_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    nse_symbol = get_nse_symbol(ticker)
    data = _indianapi_request('stock', {'name': nse_symbol})

    if 'error' in data or not isinstance(data, dict):
        return None

    result = {
        'tickerId': data.get('tickerId', ticker.upper()),
        'companyName': data.get('companyName', ticker.upper()),
        'industry': data.get('industry', ''),
        'companyProfile': data.get('companyProfile', {}),
        'currentPrice': data.get('currentPrice', {}),
        'stockTechnicalData': data.get('stockTechnicalData', {}),
        'percentChange': data.get('percentChange', 0),
        'yearHigh': data.get('yearHigh', 0),
        'yearLow': data.get('yearLow', 0),
        'financials': data.get('financials', {}),
        'keyMetrics': data.get('keyMetrics', {}),
        'analystView': data.get('analystView', {}),
        'recosBar': data.get('recosBar', {}),
        'riskMeter': data.get('riskMeter', {}),
        'shareholding': data.get('shareholding', {}),
        'stockCorporateActionData': data.get('stockCorporateActionData', {}),
        'stockDetailsReusableData': data.get('stockDetailsReusableData', {}),
        'recentNews': data.get('recentNews', []),
        'source': 'indianapi',
    }

    _set_cache(cache_key, result, _stock_cache)
    return result


# ---------------------------------------------------------------------------
# Real-time Quote
# ---------------------------------------------------------------------------

def get_indianapi_quote(ticker):
    """
    Get real-time price quote for an Indian stock.

    Args:
        ticker: NSE ticker (e.g., 'RELIANCE')

    Returns:
        dict with price, change, high/low, or None
    """
    cache_key = f"ia_quote_{ticker.upper()}"
    cached = _get_cached(cache_key, _quote_cache, _QUOTE_CACHE_TTL)
    if cached is not None:
        return cached

    stock_data = get_indianapi_stock_data(ticker)
    if not stock_data:
        return None

    price_data = stock_data.get('currentPrice', {})
    percent_change = stock_data.get('percentChange', 0)

    # Price can be BSE/NSE dict or direct value
    bse_price = price_data.get('BSE', 0)
    nse_price = price_data.get('NSE', 0)
    price = nse_price or bse_price or 0

    result = {
        'price': float(price),
        'bse_price': float(bse_price),
        'nse_price': float(nse_price),
        'change': float(percent_change),
        'change_pct': float(percent_change),
        'high': float(stock_data.get('yearHigh', 0)),
        'low': float(stock_data.get('yearLow', 0)),
        'open': float(price),
        'close': float(price),
        'volume': 0,
        'year_high': float(stock_data.get('yearHigh', 0)),
        'year_low': float(stock_data.get('yearLow', 0)),
    }

    _set_cache(cache_key, result, _quote_cache)
    return result


# ---------------------------------------------------------------------------
# Key Metrics (PE, EPS, ROE, ROCE, etc.)
# ---------------------------------------------------------------------------
# The IndianAPI /stock endpoint returns keyMetrics organized into category
# sections. Each section (e.g. 'valuation', 'persharedata') is a list of
# {displayName, key, value} objects. We search these lists by internal key name.

# Mapping of known IndianAPI internal metric keys to our output field names.
# Format: (output_field, [(internal_key, fallback_priority), ...])
_KEY_METRIC_MAP = {
    # Valuation
    'pe_ratio': [
        'pPerEExcludingExtraordinaryItemsMostRecentFiscalYear',
        'pPerEBasicExcludingExtraordinaryItemsTTM',
        'pPerEIncludingExtraordinaryItemsTTM',
        'pPerENormalizedMostRecentFiscalYear',
        'pPerExcludingExtraordinaryItemsHighTrailing12Months',
        'pPerEExcludingExtraordinaryItemsMostRecentFiscalYearQuarter',
    ],
    'pb_ratio': [
        'priceToBookMostRecentFiscalYear',
        'priceToBookMostRecentQuarter',
    ],
    'ps_ratio': [
        'priceToSalesMostRecentFiscalYear',
        'priceToSalesTrailing12Month',
    ],
    'peg_ratio': ['pegRatio'],
    'pe_to_cash_flow': ['priceToCashFlowPerShareTrailing12Month'],
    'pe_to_fcf': [
        'priceToFreeCashFlowPerShareMostRecentFiscalYear',
        'priceToFreeCashFlowPerShareTrailing12Months',
    ],

    # Per-share
    'eps_ttm': [
        'ePSIncludingExtraOrdinaryItemsTrailing12Month',
        'ePSBasicExcludingExtraordinaryItemsItrailing12Month',
        'eEPSExcludingExtraordinaryIitemsTrailing12onth',
        'earningsPerShareNormalizedExcludingExtraordinaryItemsAvgDilutedSharesOutstandingTTM',
        'ePSExcludingExtraordinaryItemsMostRecentFiscalYear',
        'ePSBasicExcludingExtraordinaryItemsMostRecentFiscalYear',
    ],
    'eps_annual': [
        'ePSIncludingExtraordinaryItemsMostRecentFiscalYear',
        'ePSBasicExcludingExtraordinaryItemsMostRecentFiscalYear',
        'ePSNormalizedMostRecentFiscalYear',
    ],
    'book_value': [
        'bookValuePerShareMostRecentFiscalYear',  # note: API has space in key
        'bookValuePerShare MostRecentFiscalYear',
        'bookValuePerShareMostRecentQuarter',
        'bookValueTangibleperSharemostRecentQuarter',
    ],
    'dividend_per_share': [
        'dividendPerShare MostRecentFiscalYear',
        'dividendsPerShareTrailing12Month',
        'dividendperShare5YearAverage',
    ],
    'cash_per_share': [
        'cashPerShareMostRecentFiscalYear',
        'cashPerShareMostRecentQuarter',
    ],
    'cash_flow_per_share': [
        'cashflowPerShareMostRecentFiscalYear',
        'cashFlowPerShareTrailing12Month',
    ],

    # Profitability
    'roe': [
        'returnOnAverageEquityMostRecentFiscalYear',
        'returnOnAverageEquityMostRecentFiscalYear)',  # note trailing paren
        'returnOnAverageEquityTrailing12Month',
        'returnOnAverageEquity5YearAverage',
    ],
    'roce': [  # ROCE approximated by Return on Investment (ROI)
        'returnOnInvestmentMostRecentFiscalYear',
        'returnOnInvestment5YearAverage',
        'returnOnInvestmentTrailing12Month',
    ],
    'roa': [
        'returnOnAverageAssetsMostRecenFiscalYear',
        'returnOnAverageAssetsTrailing12Month',
        'returnOnAverageAssets5YearAverage',
    ],

    # Margins
    'gross_margin': [
        'grossMarginTrailing12Month',
        'grossMargin5YearAverage',
        'grossMargin1stHistoricalFiscalYear',
    ],
    'operating_margin': [
        'operatingMarginTrailing12Month',
        'operatingMargin5YearAverage',
        'operatingMargin1stHistoricalFiscalYear',
    ],
    'net_margin': [
        'netProfitMarginPercentTrailing12Month',
        'netProfitMargin5YearAverage',
        'netProfitMarginPercent1stHistoricalFiscalYear',
    ],
    'pretax_margin': [
        'pretaxMarginTrailing12Month',
        'pretaxMargin5YearAverage',
        'pretaxMargin1stHistoricalFiscalYear',
    ],

    # Leverage / Liquidity
    'debt_to_equity': [
        'totalDebtPerTotalEquityMostRecentFiscalYear',
        'totalDebtPerTotalEquityMostRecentQuarter',
        'ltDebtPerEquityMostRecentFiscalYear',
        'ltDebtPerEquityMostRecentFiscalYear)',
        'lTDebtPerEquityMostRecentQuarter',
    ],
    'current_ratio': [
        'currentRatioMostRecentFiscalYear',
        'currentRatioMostRecentQuarter',
    ],
    'quick_ratio': [
        'quickRatioMostRecentFiscalYear',
        'quickRatioMostRecentQuarter',
    ],
    'payout_ratio': [
        'payoutRatioTrailing12Month',
        'payoutRatioMostRecentFiscalYear',
    ],
    'net_interest_coverage': [
        'netInterestCoverageMostRecentFiscalYear',
        'netInterestCoverageTrailing12Month',
    ],

    # Dividend
    'dividend_yield': [
        'currentDividendYieldCommonStockPrimaryIssueLTM',
        'dividendYieldIndicatedAnnualDividendDividedByClosingprice',
        'dividendYield5YearAverage',
    ],

    # Growth
    'revenue_growth': [
        'revenueGrowthRate5Year',
        'revenueChangePercentTTMPOverTTM',
        'revenueChangePercentMostRecentQuarter1YearAgo',
        'growthRatePercentRevenue3Year',
    ],
    'profit_growth': [
        'ePSGrowthRate5Year',
        'ePSChangePercentTTMOverTTM',
        'growthRatePercentEPS3year',
    ],

    # Market data
    'market_cap': ['marketCap'],
    'beta': ['beta'],
    'avg_volume': [
        'avgTradingVolumeLast10Days',
        'avgTradingVolumeLast3months',
    ],
    'price_1d_change': ['price1DayPercentChange'],
    'price_5d_change': ['price5DayPercentChange'],
    'price_13w_change': ['price13WeekPricePercentChange'],
    'price_26w_change': ['price26WeekPricePercentChange'],
    'price_52w_change': ['price52WeekPricePercentChange'],
    'price_ytd_change': ['priceYTDPricePercentChange'],
    '52_week_low': ['52WeekLow'],
    '52_week_high': ['52WeekHigh'],
}


def _find_metric(key_metrics, internal_keys, default=0):
    """
    Search through categorized keyMetrics for a metric by its internal key name.

    The IndianAPI keyMetrics is a dict of category -> list of {displayName, key, value}.
    This helper iterates all categories to find the first matching key.

    Args:
        key_metrics: The categorized keyMetrics dict from the API
        internal_keys: List of possible internal key names to search for
        default: Value to return if no match found (default 0)

    Returns:
        The float value of the first matching metric, or default
    """
    if not isinstance(key_metrics, dict):
        return default

    for category_name, metric_list in key_metrics.items():
        if not isinstance(metric_list, list):
            continue
        for entry in metric_list:
            if isinstance(entry, dict):
                entry_key = entry.get('key', '')
                if entry_key in internal_keys:
                    val = entry.get('value')
                    try:
                        if val is not None:
                            return float(val)
                    except (ValueError, TypeError):
                        pass
    return default


def get_indianapi_key_metrics(ticker):
    """
    Extract key financial metrics from IndianAPI stock data.

    Args:
        ticker: NSE ticker

    Returns:
        dict with PE, EPS, ROE, ROCE, PB, Div Yield, etc., or None
    """
    cache_key = f"ia_metrics_{ticker.upper()}"
    cached = _get_cached(cache_key, _metrics_cache, _METRICS_CACHE_TTL)
    if cached is not None:
        return cached

    stock_data = get_indianapi_stock_data(ticker)
    if not stock_data:
        return None

    key_metrics = stock_data.get('keyMetrics', {})

    # Build result by searching categorized keyMetrics for each field
    result = {
        '_raw': key_metrics,  # Keep raw data for extended display
    }
    for field_name, internal_keys in _KEY_METRIC_MAP.items():
        result[field_name] = _find_metric(key_metrics, internal_keys)

    _set_cache(cache_key, result, _metrics_cache)
    return result


# ---------------------------------------------------------------------------
# Historical Data (OHLCV for charts)
# ---------------------------------------------------------------------------

def get_indianapi_historical_data(ticker, period='1yr', filter_type='price'):
    """
    Fetch historical OHLCV data from IndianAPI.

    Args:
        ticker: NSE ticker
        period: '1m', '6m', '1yr', '3yr', '5yr', '10yr', 'max' (default '1yr')
        filter_type: 'price', 'pe', 'sm', 'evebitda', 'ptb', 'mcs' (default 'price')

    Returns:
        pandas DataFrame with OHLCV data, or None on failure
    """
    cache_key = f"ia_hist_{ticker.upper()}_{period}_{filter_type}"
    cached = _get_cached(cache_key, _hist_cache, _HIST_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    nse_symbol = get_nse_symbol(ticker)
    data = _indianapi_request('historical_data', {
        'stock_name': nse_symbol,
        'period': period,
        'filter': filter_type,
    })

    if 'error' in data or not isinstance(data, dict):
        return None

    datasets = data.get('datasets', [])
    if not datasets:
        return None

    # Find Price and Volume datasets
    price_values = None
    volume_values = None
    for ds in datasets:
        metric = ds.get('metric', '').lower()
        if metric == 'price':
            price_values = ds.get('values', [])
        elif metric == 'volume':
            volume_values = ds.get('values', [])

    if not price_values:
        return None

    # Build DataFrame from price array: [[date, price], ...]
    records = []
    for i, entry in enumerate(price_values):
        if len(entry) >= 2:
            date_str = entry[0]
            price_val = float(entry[1]) if entry[1] is not None else 0
            vol_val = 0
            if volume_values and i < len(volume_values):
                vol_entry = volume_values[i]
                if len(vol_entry) >= 2:
                    try:
                        vol_val = float(vol_entry[1]) if vol_entry[1] is not None else 0
                    except (ValueError, TypeError):
                        vol_val = 0
            records.append({'Date': date_str, 'Close': price_val, 'Volume': vol_val})

    if not records:
        return None

    df = pd.DataFrame(records)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    df.dropna(subset=['Close'], inplace=True)

    # Generate OHLC from close price (approximate)
    df['Open'] = df['Close'].shift(1).fillna(df['Close'])
    df['High'] = df[['Open', 'Close']].max(axis=1) * 1.005
    df['Low'] = df[['Open', 'Close']].min(axis=1) * 0.995

    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if len(df) < 2:
        return None

    _set_cache(cache_key, df, _hist_cache)
    return df


# ---------------------------------------------------------------------------
# Financial Statements (Quarterly & Annual)
# ---------------------------------------------------------------------------

def get_indianapi_financials(ticker, stats_type='quarter_results'):
    """
    Fetch historical financial statements.

    Args:
        ticker: NSE ticker
        stats_type: 'quarter_results', 'yoy_results', 'balancesheet',
                   'cashflow', 'ratios', 'shareholding_pattern_quarterly',
                   'shareholding_pattern_yearly'

    Returns:
        dict with financial data, or None
    """
    cache_key = f"ia_fin_{ticker.upper()}_{stats_type}"
    cached = _get_cached(cache_key, _fin_cache, _FIN_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    nse_symbol = get_nse_symbol(ticker)
    data = _indianapi_request('historical_stats', {
        'stock_name': nse_symbol,
        'stats': stats_type,
    })

    if 'error' in data or not isinstance(data, dict):
        return None

    _set_cache(cache_key, data, _fin_cache)
    return data


# ---------------------------------------------------------------------------
# Analyst Targets
# ---------------------------------------------------------------------------

def get_indianapi_analyst_targets(ticker):
    """
    Fetch analyst ratings, price targets, and risk assessment.

    The IndianAPI /stock endpoint returns:
      - analystView: list of {ratingName, ratingValue, numberOfAnalystsLatest, ...}
      - recosBar: dict with stockAnalyst list, meanValue, noOfRecommendations
      - riskMeter: dict with categoryName, stdDev

    Args:
        ticker: NSE ticker

    Returns:
        dict with recommendation counts, recosBar, riskMeter, or None
    """
    cache_key = f"ia_target_{ticker.upper()}"
    cached = _get_cached(cache_key, _target_cache, _TARGET_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    stock_data = get_indianapi_stock_data(ticker)
    if not stock_data:
        return None

    # analystView is a list of rating objects
    analyst_view = stock_data.get('analystView', [])
    if not isinstance(analyst_view, list):
        analyst_view = []

    # Extract analyst counts from the list
    buy_count = 0
    hold_count = 0
    sell_count = 0
    for entry in analyst_view:
        if not isinstance(entry, dict):
            continue
        name = entry.get('ratingName', '').lower()
        count_val = entry.get('numberOfAnalystsLatest', 0)
        try:
            count = int(float(count_val))
        except (ValueError, TypeError):
            count = 0
        if 'strong buy' in name or name == 'buy':
            buy_count += count
        elif name == 'hold':
            hold_count += count
        elif 'strong sell' in name or name == 'sell':
            sell_count += count

    # recosBar has the aggregated data
    recos_bar = stock_data.get('recosBar', {})
    if not isinstance(recos_bar, dict):
        recos_bar = {}

    # riskMeter
    risk_meter = stock_data.get('riskMeter', {})
    if not isinstance(risk_meter, dict):
        risk_meter = {}

    result = {
        'recommendation': {
            'buy': buy_count,
            'hold': hold_count,
            'sell': sell_count,
            'total': recos_bar.get('noOfRecommendations', buy_count + hold_count + sell_count),
            'mean_rating': recos_bar.get('meanValue', 0),
            'ticker_rating': recos_bar.get('tickerRatingValue', 0),
        },
        'recosBar': recos_bar,
        'riskMeter': risk_meter,
    }

    _set_cache(cache_key, result, _target_cache)
    return result


# ---------------------------------------------------------------------------
# Stock Forecasts (Earnings Estimates)
# ---------------------------------------------------------------------------

def get_indianapi_stock_forecasts(ticker, measure_code='EPS', period_type='Annual',
                                   data_type='Estimates', age='Current'):
    """
    Fetch stock forecasts (earnings estimates).

    Args:
        ticker: NSE ticker
        measure_code: 'EPS', 'SAL', 'NET', 'ROE', etc.
        period_type: 'Annual' or 'Interim'
        data_type: 'Estimates' or 'Actuals'
        age: 'Current', 'OneWeekAgo', 'ThirtyDaysAgo', etc.

    Returns:
        dict with forecast data, or None
    """
    cache_key = f"ia_fcast_{ticker.upper()}_{measure_code}_{period_type}_{data_type}_{age}"
    cached = _get_cached(cache_key, _forecast_cache, _FORECAST_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    nse_symbol = get_nse_symbol(ticker)
    data = _indianapi_request('stock_forecasts', {
        'stock_id': nse_symbol.lower(),
        'measure_code': measure_code,
        'period_type': period_type,
        'data_type': data_type,
        'age': age,
    })

    if 'error' in data or not isinstance(data, dict):
        return None

    _set_cache(cache_key, data, _forecast_cache)
    return data


# ---------------------------------------------------------------------------
# Trending Stocks
# ---------------------------------------------------------------------------

def get_indianapi_trending():
    """
    Fetch trending stocks (top gainers/losers).

    Returns:
        dict with top_gainers and top_losers lists, or None
    """
    cached = _get_cached('ia_trending', _trending_cache, _TRENDING_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_indianapi_available():
        return None

    data = _indianapi_request('trending')

    if 'error' in data or not isinstance(data, dict):
        return None

    result = {
        'top_gainers': data.get('trending_stocks', {}).get('top_gainers', []),
        'top_losers': data.get('trending_stocks', {}).get('top_losers', []),
    }

    _set_cache('ia_trending', result, _trending_cache)
    return result


# ---------------------------------------------------------------------------
# Convenience / Unified Functions
# ---------------------------------------------------------------------------

def get_indianapi_stock_price(ticker):
    """
    Get current stock price for display in navbar/ticker.

    Args:
        ticker: NSE ticker

    Returns:
        dict with price, change, change_pct, or None
    """
    quote = get_indianapi_quote(ticker)
    if not quote:
        return None
    return {
        'price': quote.get('price', 0),
        'change': quote.get('change', 0),
        'change_pct': quote.get('change_pct', 0),
        'currency_symbol': '\u20b9',
    }


def get_indianapi_stock_data_with_financials(ticker):
    """
    Get comprehensive stock data including financials and metrics in one call.

    Returns a combined dict suitable for the /api/fundamentals endpoint.
    """
    stock_data = get_indianapi_stock_data(ticker)
    if not stock_data:
        return None

    metrics = get_indianapi_key_metrics(ticker)
    quote = get_indianapi_quote(ticker)

    profile = stock_data.get('companyProfile', {})
    financials = stock_data.get('financials', {})

    result = {
        'ticker': ticker,
        'company': stock_data.get('companyName', ticker),
        'industry': stock_data.get('industry', ''),
        'indianapi_configured': True,
        'profile': {
            'name': stock_data.get('companyName', ticker),
            'ticker': ticker,
            'industry': stock_data.get('industry', ''),
            'market_cap': metrics.get('market_cap', 0) if metrics else 0,
        },
        'current_price': quote.get('price', 0) if quote else 0,
        'bse_price': quote.get('bse_price', 0) if quote else 0,
        'nse_price': quote.get('nse_price', 0) if quote else 0,
        'percent_change': quote.get('change_pct', 0) if quote else 0,
        'year_high': quote.get('year_high', 0) if quote else 0,
        'year_low': quote.get('year_low', 0) if quote else 0,
        'metrics': metrics or {},
        'financials': financials,
        'recent_news': stock_data.get('recentNews', [])[:5],
        'risk_meter': stock_data.get('riskMeter', {}),
        'shareholding': stock_data.get('shareholding', {}),
        'source': 'indianapi',
    }

    return result
