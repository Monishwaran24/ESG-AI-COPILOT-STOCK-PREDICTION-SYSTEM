"""
Twelve Data API Wrapper (Fallback Data Source)
=================================================
This module now serves as a FALLBACK data source only.
Primary data source: Finnhub API (see finnhub_api.py)

Twelve Data: direct REST calls, no SDK needed.
yfinance: used as additional fallback.

Setup:
  1. Sign up for free API key at https://twelvedata.com (800 req/day)
  2. Set TWELVEDATA_API_KEY in your .env file
  3. Free tier supports limited NSE stocks (INFY works, RELIANCE needs paid plan)
  4. For unsupported stocks, automatically falls back to yfinance

Usage:
    from model.kite_api import get_indian_stock_data, get_indian_live_price
    df = get_indian_stock_data('RELIANCE', period='1y')
    price = get_indian_live_price('RELIANCE')
"""

import os
import time
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# NSE Ticker mappings (special characters like M&M -> M_M)
# ---------------------------------------------------------------------------
NSE_TICKER_MAP = {
    'M_M': 'M&M',
    'BAJAJ_AUTO': 'BAJAJ-AUTO',
}

# Cache for historical data to avoid hitting rate limits
_hist_cache = {}
_HIST_CACHE_TTL = 3600  # 1 hour

# Cache for live prices
_price_cache = {}
_PRICE_CACHE_TTL = 300  # 5 minutes (800 req/day free tier protection)


def get_twelvedata_key():
    """Get Twelve Data API key from environment."""
    return os.environ.get('TWELVEDATA_API_KEY', '').strip()


def is_twelvedata_available():
    """Check if Twelve Data API key is configured and valid."""
    key = get_twelvedata_key()
    if not key or len(key) < 10:
        return False
    if 'your_' in key.lower() or key == 'YOUR_API_KEY_HERE':
        return False
    return True


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


def _twelvedata_rest_request(endpoint, params):
    """
    Make a direct REST call to Twelve Data API.
    No SDK required — uses requests directly.

    Args:
        endpoint: API endpoint like 'time_series', 'quote'
        params: dict of query parameters

    Returns:
        dict with API response, or dict with 'error' key on failure
    """
    try:
        import requests
    except ImportError:
        return {'error': 'requests library not available'}

    api_key = get_twelvedata_key()
    if not api_key:
        return {'error': 'No API key configured'}

    params['apikey'] = api_key
    url = f'https://api.twelvedata.com/{endpoint}'

    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()

        # Check for API-level errors
        code = data.get('code')
        if code == 401:
            return {'error': 'Invalid Twelve Data API key'}
        if code == 429:
            return {'error': 'Twelve Data rate limit exceeded'}

        # Check for symbol-level restrictions (free tier limitation)
        msg = data.get('message', '').lower()
        if 'grow' in msg or 'venture' in msg or 'upgrade' in msg:
            return {'error': 'restricted', 'message': data.get('message', '')}

        # Check for symbol errors
        status = data.get('status', 'ok')
        if status == 'error':
            return {'error': data.get('message', 'Unknown error')}

        return data

    except requests.exceptions.Timeout:
        return {'error': 'Twelve Data API timeout'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Cannot connect to Twelve Data API'}
    except Exception as e:
        return {'error': f'Twelve Data API error: {str(e)}'}


def get_historical_data_twelvedata(ticker, days=365, interval='1day'):
    """
    Fetch historical OHLCV data from Twelve Data via direct REST API.

    Args:
        ticker: NSE symbol (e.g., 'RELIANCE')
        days: Number of days of historical data
        interval: '1day' (daily), '1hour', etc.

    Returns:
        pandas DataFrame with columns: Open, High, Low, Close, Volume
        Returns None on failure
    """
    cache_key = f"td_hist_{ticker}_{days}_{interval}"
    cached = _get_cached(cache_key, _hist_cache, _HIST_CACHE_TTL)
    if cached is not None:
        return cached

    nse_symbol = NSE_TICKER_MAP.get(ticker, ticker)
    outputsize = min(days + 30, 5000)

    # Try multiple symbol formats
    symbol_formats = [
        {'symbol': nse_symbol, 'exchange': 'NSE'},
        {'symbol': f'{nse_symbol}.BSE'},
        {'symbol': nse_symbol},  # Let Twelve Data auto-detect
    ]

    for fmt in symbol_formats:
        params = {
            'symbol': fmt['symbol'],
            'interval': interval,
            'outputsize': outputsize,
        }
        if 'exchange' in fmt:
            params['exchange'] = fmt['exchange']

        data = _twelvedata_rest_request('time_series', params)

        if 'error' in data:
            if data['error'] == 'restricted':
                # Free tier doesn't support this symbol — skip
                continue
            # Other errors — skip this format
            continue

        if 'values' not in data or not data['values']:
            continue

        # Convert to DataFrame
        records = data['values']
        records.reverse()  # API returns newest first
        df = pd.DataFrame(records)

        # Rename and convert columns
        col_map = {'datetime': 'Date', 'open': 'Open', 'high': 'High',
                   'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)

        # Convert to numeric
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df.sort_index(inplace=True)
        df.dropna(subset=['Close'], inplace=True)

        if len(df) > 20:
            _set_cache(cache_key, df, _hist_cache)
            return df

    return None


def get_live_quote_twelvedata(ticker):
    """
    Get current quote for a NSE ticker from Twelve Data via direct REST API.

    Args:
        ticker: NSE symbol (e.g., 'RELIANCE')

    Returns:
        dict with price info, or None on failure
    """
    cache_key = f"td_quote_{ticker}"
    cached = _get_cached(cache_key, _price_cache, _PRICE_CACHE_TTL)
    if cached is not None:
        return cached

    nse_symbol = NSE_TICKER_MAP.get(ticker, ticker)

    # Try multiple formats
    symbol_formats = [
        {'symbol': nse_symbol, 'exchange': 'NSE'},
        {'symbol': nse_symbol},
    ]

    for fmt in symbol_formats:
        params = {'symbol': fmt['symbol']}
        if 'exchange' in fmt:
            params['exchange'] = fmt['exchange']

        data = _twelvedata_rest_request('quote', params)

        if 'error' in data:
            if data['error'] == 'restricted':
                continue
            continue

        result = {
            'price': float(data.get('close', 0)),
            'open': float(data.get('open', 0)),
            'high': float(data.get('high', 0)),
            'low': float(data.get('low', 0)),
            'close': float(data.get('previous_close', 0)),
            'volume': int(float(data.get('volume', 0))),
            'change': float(data.get('change', 0)),
            'change_pct': float(data.get('percent_change', 0)),
        }

        _set_cache(cache_key, result, _price_cache)
        return result

    return None


def get_indian_stock_data_yfinance(ticker, period='6mo'):
    """
    Fallback: Fetch Indian stock data via yfinance (.NS suffix).
    This is the workhorse for most Indian stocks on the free tier.

    Args:
        ticker: NSE symbol (e.g., 'RELIANCE')
        period: yfinance period string

    Returns:
        pandas DataFrame with OHLCV data, or None
    """
    try:
        import yfinance as yf
        nse_symbol = NSE_TICKER_MAP.get(ticker, ticker)
        yf_ticker = f"{nse_symbol}.NS"
        stock = yf.Ticker(yf_ticker)
        data = stock.history(period=period)
        if data.empty:
            # Try BSE as last resort
            yf_ticker = f"{nse_symbol}.BO"
            stock = yf.Ticker(yf_ticker)
            data = stock.history(period=period)
        if not data.empty:
            return data
        return None
    except Exception as e:
        print(f"[kite_api] yfinance fallback error for {ticker}: {e}")
        return None


def get_indian_stock_data(ticker, period='6mo', prefer_twelvedata=True):
    """
    Get Indian stock historical data.
    Primary: Twelve Data API (limited free tier support)
    Fallback: yfinance with .NS suffix (works for all NSE stocks)

    Args:
        ticker: NSE symbol (e.g., 'RELIANCE')
        period: period string (e.g., '6mo', '1y', '2y')
        prefer_twelvedata: if True, try Twelve Data first

    Returns:
        pandas DataFrame with OHLCV data, or None
    """
    days_map = {
        '1mo': 30, '3mo': 90, '6mo': 180,
        '1y': 365, '2y': 730, '3y': 1095, '5y': 1825,
    }
    days = days_map.get(period, 180)

    # Try Twelve Data first (works for INFY, limited others on free tier)
    if prefer_twelvedata and is_twelvedata_available():
        df = get_historical_data_twelvedata(ticker, days=days)
        if df is not None and len(df) > 20:
            return df

    # Fallback to yfinance (works for ALL NSE stocks)
    df = get_indian_stock_data_yfinance(ticker, period=period)
    if df is not None and len(df) > 20:
        return df

    # Try Twelve Data as last resort if we skipped it
    if not prefer_twelvedata and is_twelvedata_available():
        df = get_historical_data_twelvedata(ticker, days=days)
        if df is not None and len(df) > 20:
            return df

    return None


def get_indian_live_price(ticker, prefer_twelvedata=True):
    """
    Get current live price for an Indian stock.
    Primary: Twelve Data API (limited)
    Fallback: yfinance with .NS suffix

    Args:
        ticker: NSE symbol (e.g., 'RELIANCE')
        prefer_twelvedata: if True, try Twelve Data first

    Returns:
        dict with price info, or None
    """
    if prefer_twelvedata and is_twelvedata_available():
        quote = get_live_quote_twelvedata(ticker)
        if quote is not None:
            return quote

    try:
        import yfinance as yf
        nse_symbol = NSE_TICKER_MAP.get(ticker, ticker)
        yf_ticker = f"{nse_symbol}.NS"
        stock = yf.Ticker(yf_ticker)
        data = stock.history(period='5d')
        if not data.empty:
            latest = data.iloc[-1]
            prev = data.iloc[-2] if len(data) > 1 else latest
            change = float(latest['Close'] - prev['Close'])
            change_pct = (change / float(prev['Close'])) * 100 if float(prev['Close']) > 0 else 0
            return {
                'price': float(latest['Close']),
                'open': float(latest['Open']),
                'high': float(latest['High']),
                'low': float(latest['Low']),
                'close': float(prev['Close']),
                'volume': int(latest['Volume']),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
            }
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Indian stock ticker list (Nifty 50 + additional large-cap stocks)
# ---------------------------------------------------------------------------
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


def is_indian_ticker(ticker):
    """Check if a ticker is an Indian stock."""
    return ticker.upper() in INDIAN_TICKERS_SET


def get_nse_symbol(ticker):
    """Get the NSE trading symbol from internal ticker (handles M_M -> M&M, etc.)."""
    return NSE_TICKER_MAP.get(ticker, ticker)


def get_cached_price(ticker):
    """Get cached live price for an Indian stock."""
    cache_key = f"td_price_{ticker.upper()}"
    cached = _get_cached(cache_key, _price_cache, _PRICE_CACHE_TTL)
    return cached


def set_cached_price(ticker, data):
    """Cache live price for an Indian stock."""
    cache_key = f"td_price_{ticker.upper()}"
    _set_cache(cache_key, data, _price_cache)
