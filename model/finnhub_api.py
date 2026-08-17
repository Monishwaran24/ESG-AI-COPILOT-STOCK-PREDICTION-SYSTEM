"""
Finnhub Stock Data API Integration
====================================
Primary data source for real-time stock quotes, historical OHLCV (candlestick)
data, company profiles, and fundamentals. Replaces Twelve Data as the primary
stock data provider.

Finnhub API Key: Reads from FINNHUB_API_KEY in .env or environment variables.
Free tier: 60 requests/minute, enough for most use cases with caching.

API Docs: https://finnhub.io/docs/api
- Stock Candles:   GET /stock/candle
- Quote:           GET /quote
- Company Profile: GET /stock/profile2
- Financials:      GET /stock/metric
- Company News:    GET /company-news (used in news_sentiment.py)

Usage:
    from model.finnhub_api import (
        is_finnhub_available,
        get_finnhub_historical_data,
        get_finnhub_quote,
        get_finnhub_company_profile,
        get_finnhub_metrics
    )
    df = get_finnhub_historical_data('AAPL', days=365)
    quote = get_finnhub_quote('AAPL')
"""

import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Cache for historical data to avoid hitting rate limits
_hist_cache = {}
_HIST_CACHE_TTL = 3600  # 1 hour

# Cache for quotes
_quote_cache = {}
_QUOTE_CACHE_TTL = 300  # 5 minutes

# Cache for company profiles
_profile_cache = {}
_PROFILE_CACHE_TTL = 86400  # 24 hours

# NSE ticker map (Indian stock symbols on Finnhub use NSE: prefix)
NSE_TICKER_MAP = {
    'M_M': 'M&M',
    'BAJAJ_AUTO': 'BAJAJ-AUTO',
}

# Indian stock ticker set
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


def get_finnhub_api_key():
    """Get Finnhub API key from environment."""
    return os.environ.get('FINNHUB_API_KEY', '').strip()


def is_finnhub_available():
    """Check if Finnhub API key is configured and valid-looking for stock data."""
    key = get_finnhub_api_key()
    if not key or len(key) < 5:
        return False
    if 'your_' in key.lower() or key == 'YOUR_API_KEY_HERE':
        return False
    return True


def is_indian_ticker(ticker):
    """Check if a ticker is an Indian stock."""
    return ticker.upper() in INDIAN_TICKERS_SET


def get_nse_symbol(ticker):
    """Get the NSE trading symbol from internal ticker (handles M_M -> M&M, etc.)."""
    return NSE_TICKER_MAP.get(ticker, ticker)


def _get_finnhub_symbol(ticker):
    """
    Convert a ticker to Finnhub format.
    For US stocks: use as-is.
    For Indian stocks: prefix with NSE: (e.g., NSE:RELIANCE)
    """
    t = ticker.upper()
    if is_indian_ticker(t):
        nse_symbol = get_nse_symbol(t)
        return f"NSE:{nse_symbol}"
    return t


def _get_cached(key, cache, ttl):
    """Get a cached value if fresh."""
    now = time.time()
    if key in cache:
        val, ts = cache[key]
        if (now - ts) < ttl:
            return val
    return None


def _set_cache(key, value, cache):
    """Set a cached value."""
    cache[key] = (value, time.time())
    if len(cache) > 200:
        cache.clear()


def _finnhub_rest_request(endpoint, params=None):
    """
    Make a direct REST call to Finnhub API.

    Args:
        endpoint: API endpoint like 'quote', 'stock/candle', 'stock/profile2'
        params: dict of query parameters (without token)

    Returns:
        dict with API response, or dict with 'error' key on failure
    """
    try:
        import requests
    except ImportError:
        return {'error': 'requests library not available'}

    api_key = get_finnhub_api_key()
    if not api_key:
        return {'error': 'No Finnhub API key configured'}

    if params is None:
        params = {}

    params['token'] = api_key
    url = f'https://finnhub.io/api/v1/{endpoint}'

    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code == 429:
            return {'error': 'rate_limit', 'message': 'Finnhub rate limit exceeded (60 req/min)'}
        if resp.status_code == 403:
            return {'error': 'forbidden', 'message': 'Finnhub API key invalid or unauthorized'}
        if not resp.ok:
            return {'error': f'HTTP {resp.status_code}', 'message': resp.text[:200]}

        data = resp.json()

        # Check for Finnhub error responses
        if isinstance(data, dict):
            if data.get('error'):
                return {'error': data['error']}

        return data

    except requests.exceptions.Timeout:
        return {'error': 'Finnhub API timeout'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Cannot connect to Finnhub API'}
    except Exception as e:
        return {'error': f'Finnhub API error: {str(e)}'}


def get_finnhub_historical_data(ticker, days=365, resolution='D'):
    """
    Fetch historical OHLCV (candlestick) data from Finnhub API.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'RELIANCE')
        days: Number of days of historical data to fetch
        resolution: '1', '5', '15', '30', '60', 'D', 'W', 'M' (default: 'D' for daily)

    Returns:
        pandas DataFrame with columns: Open, High, Low, Close, Volume, Date (index)
        Returns None on failure
    """
    cache_key = f"fh_hist_{ticker.upper()}_{days}_{resolution}"
    cached = _get_cached(cache_key, _hist_cache, _HIST_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)

    # Calculate timestamps
    to_ts = int(time.time())
    from_ts = int(to_ts - (days + 30) * 86400)  # Add buffer days

    params = {
        'symbol': symbol,
        'resolution': resolution,
        'from': from_ts,
        'to': to_ts,
    }

    data = _finnhub_rest_request('stock/candle', params)

    if 'error' in data:
        return None

    # Finnhub returns candle data as arrays: {'c': [close], 'h': [high], 'l': [low], 'o': [open], 'v': [volume], 't': [timestamp], 's': 'ok'}
    if not isinstance(data, dict) or data.get('s') != 'ok':
        return None

    closes = data.get('c', [])
    highs = data.get('h', [])
    lows = data.get('l', [])
    opens = data.get('o', [])
    volumes = data.get('v', [])
    timestamps = data.get('t', [])

    if not closes or len(closes) < 2:
        return None

    # Build DataFrame
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes,
    }, index=pd.to_datetime(timestamps, unit='s'))

    df.index.name = 'Date'
    df.sort_index(inplace=True)

    # Convert to numeric
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df.dropna(subset=['Close'], inplace=True)

    if len(df) < 2:
        return None

    _set_cache(cache_key, df, _hist_cache)
    return df


def get_finnhub_quote(ticker):
    """
    Get real-time stock quote from Finnhub API.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        dict with quote data, or None on failure
    """
    cache_key = f"fh_quote_{ticker.upper()}"
    cached = _get_cached(cache_key, _quote_cache, _QUOTE_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('quote', {'symbol': symbol})

    if 'error' in data:
        return None

    # Finnhub quote response: {c: current, d: change, dp: percent_change, h: high, l: low, o: open, pc: previous_close, t: timestamp}
    if not isinstance(data, dict) or 'c' not in data:
        return None

    current = data.get('c', 0)
    prev_close = data.get('pc', 0)
    change = data.get('d', current - prev_close)
    change_pct = data.get('dp', ((current - prev_close) / prev_close * 100) if prev_close else 0)

    result = {
        'price': float(current),
        'open': float(data.get('o', 0)),
        'high': float(data.get('h', 0)),
        'low': float(data.get('l', 0)),
        'close': float(prev_close),
        'volume': int(data.get('v', 0)),
        'change': round(float(change), 2),
        'change_pct': round(float(change_pct), 2),
    }

    _set_cache(cache_key, result, _quote_cache)
    return result


def get_finnhub_company_profile(ticker):
    """
    Fetch company profile information from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with company info, or None on failure
    """
    cache_key = f"fh_profile_{ticker.upper()}"
    cached = _get_cached(cache_key, _profile_cache, _PROFILE_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/profile2', {'symbol': symbol})

    if 'error' in data:
        return None

    if not isinstance(data, dict) or not data.get('ticker'):
        return None

    result = {
        'name': data.get('name', ticker.upper()),
        'ticker': data.get('ticker', ticker.upper()),
        'exchange': data.get('exchange', ''),
        'industry': data.get('finnhubIndustry', ''),
        'market_cap': data.get('marketCapitalization', 0),
        'share_outstanding': data.get('shareOutstanding', 0),
        'ipo_date': data.get('ipo', ''),
        'country': data.get('country', 'US'),
        'currency': data.get('currency', 'USD'),
        'weburl': data.get('weburl', ''),
        'logo': data.get('logo', ''),
        'phone': data.get('phone', ''),
    }

    _set_cache(cache_key, result, _profile_cache)
    return result


def get_finnhub_metrics(ticker):
    """
    Fetch company financial metrics from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with financial metrics, or None on failure
    """
    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/metric', {'symbol': symbol, 'metric': 'all'})

    if 'error' in data:
        return None

    if not isinstance(data, dict) or 'metric' not in data:
        return None

    metrics = data.get('metric', {})
    return {
        'beta': metrics.get('beta', 0),
        'pe_ratio': metrics.get('peBasicExclExtraTTM', 0),
        'eps_ttm': metrics.get('epsBasicExclExtraTTM', 0),
        'dividend_yield': metrics.get('dividendYieldIndicatedAnnual', 0),
        'dividend_per_share': metrics.get('dividendPerShareAnnual', 0),
        '52_week_high': metrics.get('52WeekHigh', 0),
        '52_week_low': metrics.get('52WeekLow', 0),
        '52_week_change': metrics.get('52WeekChange', 0),
        'market_cap': metrics.get('marketCapitalization', 0),
        'volume_avg': metrics.get('volumeAvg30D', 0),
        'shares_outstanding': metrics.get('sharesOutstanding', 0),
        'roa': metrics.get('returnOnAssetsTTM', 0),
        'roe': metrics.get('returnOnEquityTTM', 0),
        'revenue_ttm': metrics.get('revenueTTM', 0),
        'gross_margin': metrics.get('grossMarginTTM', 0),
    }


# Cache for earnings data
_earnings_cache = {}
_EARNINGS_CACHE_TTL = 3600  # 1 hour

# Cache for recommendations
_rec_cache = {}
_REC_CACHE_TTL = 7200  # 2 hours

# Cache for price targets
_pt_cache = {}
_PT_CACHE_TTL = 3600  # 1 hour

# Cache for financials
_fin_cache = {}
_FIN_CACHE_TTL = 86400  # 24 hours (financials change slowly)

# Cache for earnings calendar
_earnings_cal_cache = {}
_EARNINGS_CAL_CACHE_TTL = 3600  # 1 hour

# Cache for extended metrics
_metric_ext_cache = {}
_METRIC_EXT_CACHE_TTL = 3600  # 1 hour

# Cache for sentiment
_sentiment_cache = {}
_SENTIMENT_CACHE_TTL = 1800  # 30 minutes


def get_finnhub_earnings(ticker):
    """
    Fetch historical earnings data from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        list of earnings records with actual EPS, estimated EPS, surprise, or None
    """
    cache_key = f"fh_earn_{ticker.upper()}"
    cached = _get_cached(cache_key, _earnings_cache, _EARNINGS_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/earnings', {'symbol': symbol, 'limit': 4})

    if 'error' in data or not isinstance(data, list):
        return None

    earnings = []
    for e in data[:4]:
        earnings.append({
            'period': e.get('period', ''),
            'report_date': e.get('reportDate', ''),
            'eps_actual': e.get('epsActual', 0),
            'eps_estimate': e.get('epsEstimate', 0),
            'revenue_actual': e.get('revenueActual', 0),
            'revenue_estimate': e.get('revenueEstimate', 0),
            'surprise_pct': e.get('surprise', 0),
        })

    _set_cache(cache_key, earnings, _earnings_cache)
    return earnings


def get_finnhub_earnings_calendar(ticker):
    """
    Fetch upcoming earnings calendar from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with upcoming earnings info, or None
    """
    cache_key = f"fh_ecal_{ticker.upper()}"
    cached = _get_cached(cache_key, _earnings_cal_cache, _EARNINGS_CAL_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    from datetime import date, timedelta
    today = date.today()
    params = {
        'symbol': ticker,
        'from': today.isoformat(),
        'to': (today + timedelta(days=90)).isoformat(),
    }
    data = _finnhub_rest_request('calendar/earnings', params)

    if 'error' in data or not isinstance(data, dict):
        return None

    earnings_cal = data.get('earningsCalendar', [])
    if not earnings_cal:
        return None

    # Get the first upcoming earnings report
    ec = earnings_cal[0]
    result = {
        'report_date': ec.get('date', ''),
        'eps_estimate': ec.get('epsEstimate', 0),
        'revenue_estimate': ec.get('revenueEstimate', 0),
        'hour': ec.get('hour', ''),
    }

    _set_cache(cache_key, result, _earnings_cal_cache)
    return result


def get_finnhub_recommendations(ticker):
    """
    Fetch analyst recommendation trends from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with latest consensus (buy/hold/sell counts), or None
    """
    cache_key = f"fh_rec_{ticker.upper()}"
    cached = _get_cached(cache_key, _rec_cache, _REC_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/recommendation', {'symbol': symbol})

    if 'error' in data or not isinstance(data, list) or not data:
        return None

    latest = data[0]
    result = {
        'period': latest.get('period', ''),
        'strong_buy': latest.get('strongBuy', 0),
        'buy': latest.get('buy', 0),
        'hold': latest.get('hold', 0),
        'sell': latest.get('sell', 0),
        'strong_sell': latest.get('strongSell', 0),
        'total': sum([
            latest.get('strongBuy', 0), latest.get('buy', 0),
            latest.get('hold', 0), latest.get('sell', 0),
            latest.get('strongSell', 0)
        ]),
    }

    _set_cache(cache_key, result, _rec_cache)
    return result


def get_finnhub_price_target(ticker):
    """
    Fetch analyst price target consensus from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with price target data, or None
    """
    cache_key = f"fh_pt_{ticker.upper()}"
    cached = _get_cached(cache_key, _pt_cache, _PT_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/price-target', {'symbol': symbol})

    if 'error' in data or not isinstance(data, dict):
        return None

    result = {
        'target_high': data.get('targetHigh', 0),
        'target_low': data.get('targetLow', 0),
        'target_mean': data.get('targetMean', 0),
        'target_median': data.get('targetMedian', 0),
        'last_updated': data.get('lastUpdated', ''),
        'num_analysts': data.get('numberOfAnalysts', 0),
    }

    _set_cache(cache_key, result, _pt_cache)
    return result


def get_finnhub_metric_extended(ticker):
    """
    Fetch extended financial metrics from Finnhub API.
    Extends get_finnhub_metrics() with additional ratios and growth metrics.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with extended financial metrics, or None
    """
    cache_key = f"fh_mext_{ticker.upper()}"
    cached = _get_cached(cache_key, _metric_ext_cache, _METRIC_EXT_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('stock/metric', {'symbol': symbol, 'metric': 'all'})

    if 'error' in data or not isinstance(data, dict) or 'metric' not in data:
        return None

    m = data.get('metric', {})
    result = {
        # Valuation
        'pe_ratio': m.get('peBasicExclExtraTTM', 0),
        'ps_ratio': m.get('psTTM', 0),
        'pb_ratio': m.get('pbQuarterly', 0),
        'ev_ebitda': m.get('enterpriseValueToEbitdaTTM', 0),
        'book_value': m.get('bookValuePerShareQuarterly', 0),
        
        # Profitability
        'gross_margin': m.get('grossMarginTTM', 0),
        'operating_margin': m.get('operatingMarginTTM', 0),
        'net_margin': m.get('profitMarginTTM', 0),
        'roa': m.get('returnOnAssetsTTM', 0),
        'roe': m.get('returnOnEquityTTM', 0),
        'roi': m.get('returnOnInvestmentTTM', 0),
        
        # Growth
        'revenue_growth': m.get('revenueGrowthQuarterlyYoy', 0),
        'eps_growth': m.get('epsGrowthQuarterlyYoy', 0),
        'earnings_growth': m.get('earningsGrowthQuarterlyYoy', 0),
        
        # Liquidity / Solvency
        'current_ratio': m.get('currentRatioQuarterly', 0),
        'quick_ratio': m.get('quickRatioQuarterly', 0),
        'debt_equity': m.get('totalDebtToEquityQuarterly', 0),
        'interest_coverage': m.get('interestCoverageTTM', 0),
        
        # Cash Flow
        'free_cash_flow': m.get('freeCashFlowTTM', 0),
        'operating_cash_flow': m.get('operatingCashFlowTTM', 0),
        'capex': m.get('capitalExpenditureTTM', 0),
        
        # Per share
        'eps_ttm': m.get('epsBasicExclExtraTTM', 0),
        'eps_growth_ttm': m.get('epsGrowthTTMYoy', 0),
        'dividend_yield': m.get('dividendYieldIndicatedAnnual', 0),
        'dividend_per_share': m.get('dividendPerShareAnnual', 0),
        
        # Trading
        'beta': m.get('beta', 0),
        'volume_avg': m.get('volumeAvg30D', 0),
        'shares_outstanding': m.get('sharesOutstanding', 0),
        'market_cap': m.get('marketCapitalization', 0),
        '52_week_high': m.get('52WeekHigh', 0),
        '52_week_low': m.get('52WeekLow', 0),
    }

    _set_cache(cache_key, result, _metric_ext_cache)
    return result


def get_finnhub_sentiment(ticker):
    """
    Fetch news sentiment statistics from Finnhub API.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with sentiment stats (buzz, score, etc.), or None
    """
    cache_key = f"fh_sent_{ticker.upper()}"
    cached = _get_cached(cache_key, _sentiment_cache, _SENTIMENT_CACHE_TTL)
    if cached is not None:
        return cached

    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('news-sentiment', {'symbol': symbol})

    if 'error' in data or not isinstance(data, dict):
        return None

    result = {
        'buzz': data.get('buzz', {}).get('buzz', 0),
        'score': data.get('companyNewsScore', 0),
        'sector_score': data.get('sectorAverageBullishPercent', 0),
        'articles_last_week': data.get('articlesInLastWeek', []),
        'sentiment': data.get('sentiment', {}),
    }

    _set_cache(cache_key, result, _sentiment_cache)
    return result


def get_finnhub_stock_data(ticker, period='6mo'):
    """
    Get historical stock data from Finnhub as primary source.
    This is the main function called by predict.py.

    Args:
        ticker: Stock ticker symbol
        period: Period string ('1mo', '3mo', '6mo', '1y', '2y')

    Returns:
        pandas DataFrame with OHLCV data, or None on failure
    """
    days_map = {
        '1mo': 30, '3mo': 90, '6mo': 180,
        '1y': 365, '2y': 730, '3y': 1095, '5y': 1825,
    }
    days = days_map.get(period, 180)

    df = get_finnhub_historical_data(ticker, days=days)
    return df


# Convenience function for predict.py to check availability
def is_finnhub_stock_available():
    """Check if Finnhub is available for stock data (separate from news)."""
    return is_finnhub_available()


# ============================================================
# Pattern Detection & Chart Analysis (Finnhub /scan endpoints)
# These may require a premium Finnhub subscription.
# If unavailable, the functions return None gracefully.
# ============================================================

def get_finnhub_patterns(ticker, resolution='D'):
    """
    Detect candlestick chart patterns using Finnhub's pattern recognition API.
    Note: This endpoint may require a premium Finnhub subscription.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        resolution: '1', '5', '15', '30', '60', 'D', 'W', 'M' (default: 'D' daily)

    Returns:
        dict with pattern data, or None if unavailable/error
    """
    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('scan/pattern', {'symbol': symbol, 'resolution': resolution})

    if 'error' in data or not isinstance(data, dict):
        return None

    # The response structure typically includes 'patterns' key
    patterns = data.get('patterns', data)
    return {
        'ticker': ticker,
        'resolution': resolution,
        'patterns': patterns,
        'source': 'finnhub'
    }


def get_finnhub_support_resistance(ticker, resolution='D'):
    """
    Get support and resistance levels from Finnhub.
    Note: This endpoint may require a premium Finnhub subscription.

    Args:
        ticker: Stock ticker symbol
        resolution: '1', '5', '15', '30', '60', 'D', 'W', 'M' (default: 'D' daily)

    Returns:
        dict with support/resistance levels, or None if unavailable/error
    """
    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('scan/support-resistance', {'symbol': symbol, 'resolution': resolution})

    if 'error' in data or not isinstance(data, dict):
        return None

    return {
        'ticker': ticker,
        'resolution': resolution,
        'levels': data,
        'source': 'finnhub'
    }


def get_finnhub_technical_summary(ticker, resolution='D'):
    """
    Get aggregate technical analysis summary (Buy/Sell/Neutral) from Finnhub.
    Note: This endpoint may require a premium Finnhub subscription.

    Args:
        ticker: Stock ticker symbol
        resolution: '1', '5', '15', '30', '60', 'D', 'W', 'M' (default: 'D' daily)

    Returns:
        dict with technical analysis summary, or None if unavailable/error
    """
    if not is_finnhub_available():
        return None

    symbol = _get_finnhub_symbol(ticker)
    data = _finnhub_rest_request('scan/technical-indicator', {'symbol': symbol, 'resolution': resolution})

    if 'error' in data or not isinstance(data, dict):
        return None

    return {
        'ticker': ticker,
        'resolution': resolution,
        'summary': data,
        'source': 'finnhub'
    }
