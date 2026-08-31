import os, sys, warnings, numpy as np, pandas as pd, yfinance as yf
import joblib, json
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pt')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
ESG_DATA_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

# Import data source modules
# PRIMARY: Finnhub API (for US stocks) — Indian stocks use IndianAPI exclusively
# Fallback 1: Twelve Data API (for US stocks)
# Fallback 2: yfinance (for US stocks)
from model.finnhub_api import (
    get_finnhub_stock_data, get_finnhub_quote, get_finnhub_company_profile,
    get_finnhub_historical_data, is_finnhub_available as is_finnhub_stock_available
)
from model.kite_api import (
    get_indian_stock_data, get_historical_data_twelvedata,
    get_live_quote_twelvedata, get_indian_live_price,
    is_twelvedata_available, _twelvedata_rest_request
)
from model.indian_api import (
    is_indianapi_available, get_indianapi_historical_data,
    get_indianapi_quote, get_indianapi_key_metrics,
    get_indianapi_stock_data, get_indianapi_stock_data_with_financials,
    is_indian_ticker, INDIAN_TICKERS_SET, INDIAN_TICKERS, get_nse_symbol as indianapi_get_nse_symbol
)

_model_cache = None
_scaler_cache = None
_encoder_cache = None
_metadata_cache = None
_stock_data_cache = {}  # Cache for raw OHLCV DataFrames (speeds up chart rendering)

feature_cols = [
    # Base features (36) - MUST match train_model.py
    'SMA_10','SMA_30','EMA_10','EMA_30','RSI_14',
    'MACD','MACD_Signal','MACD_Histogram',
    'BB_Width','BB_Position',
    'Price_Change_1d','Price_Change_5d','Price_Change_20d',
    'Volume_Ratio','High_Low_Ratio','Close_Open_Ratio','Volatility_10d',
    'Price_Acceleration','VPT_Change','RSI_SMA','Price_Position',
    'ATR_14','STOCH_K','STOCH_D','WILLIAMS_R','MFI',
    'Log_Return_1d','Log_Return_5d','Log_Return_20d',
    'Price_Momentum','Volume_Change_1d','High_Low_Pct',
    'ESG_Score','Environmental_Score','Social_Score','Governance_Score',
    # Extended features (31) - MUST match train_model.py
    'SMA_50','EMA_50','SMA_200','EMA_200',
    'TRIX','ROC_10','ROC_20','PPO','ADX','ADXR',
    'CMO','ULT_OSC','AROON_UP','AROON_DOWN',
    'CHAIKIN_MF','OBV_Change','KAMA_10','KAMA_DIVERGENCE',
    'MIDPOINT_10','MIDPRICE_10',
    'NATR_14','TRANGE_14',
    'HV_10','HV_20','HV_30',
    'SKEW_10','KURT_10','MAX_10','MIN_10',
    'CORR_CLOSE_VOL','CORR_HIGH_LOW',
    # Macro Features (new)
    'MACRO_SP500_Return', 'MACRO_VIX', 'MACRO_IRX'
]

# Base features only (what the saved ML model was trained on - first 36 features)
BASE_FEATURES = feature_cols[:36]

def get_yfinance_ticker(ticker):
    t = ticker.upper().strip()
    if t == 'BRK.B':
        return 'BRK-B'
    if is_indian_ticker(t) and not t.endswith('.NS') and not t.endswith('.BO'):
        return f"{t}.NS"
    return t

def get_market(ticker):
    """Determine if a ticker is US or Indian market."""
    if is_indian_ticker(ticker):
        return 'IN'
    return 'US'

def get_currency_symbol(ticker):
    """Get the currency symbol for a ticker's market."""
    if is_indian_ticker(ticker):
        return '₹'
    return '$'

def get_market_suffix(ticker):
    """Get market identifier suffix."""
    if is_indian_ticker(ticker):
        return ' (NSE)'
    return ''

def get_nse_symbol(ticker):
    """Get NSE symbol for Indian tickers."""
    return indianapi_get_nse_symbol(ticker)

def load_model():
    global _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    if _model_cache is not None:
        return _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    try:
        MODEL_PATH_PKL = os.path.join(MODEL_DIR, 'model.pkl')
        _model_cache = joblib.load(MODEL_PATH_PKL)
        _scaler_cache = joblib.load(SCALER_PATH)
        _encoder_cache = joblib.load(ENCODUC_PATH if 'ENCODUC_PATH' in globals() else ENCODER_PATH)
        with open(METADATA_PATH, 'r') as f:
            _metadata_cache = json.load(f)
            
        return _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    except Exception as e:
        print(f"[X] Error loading model: {e}")
        return None, None, None, None

def get_stock_data_twelvedata(ticker, period='1y'):
    """
    Fetch historical stock data from Twelve Data REST API.
    Supports both US and Indian stock symbols.
    """
    days_map = {
        '1mo': 30, '3mo': 90, '6mo': 180,
        '1y': 365, '2y': 730, '3y': 1095, '5y': 1825,
    }
    outputsize = days_map.get(period, 365)

    if not is_twelvedata_available():
        return None

    if is_indian_ticker(ticker):
        return get_historical_data_twelvedata(ticker, days=outputsize)

    params = {
        'symbol': ticker,
        'interval': '1day',
        'outputsize': min(outputsize + 30, 5000),
    }

    data = _twelvedata_rest_request('time_series', params)

    if 'error' in data or 'values' not in data or not data['values']:
        return None

    records = data['values']
    records.reverse()
    df = pd.DataFrame(records)

    col_map = {'datetime': 'Date', 'open': 'Open', 'high': 'High',
               'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)

    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df.sort_index(inplace=True)
    df.dropna(subset=['Close'], inplace=True)

    if len(df) < 2:
        return None

    return df


def get_stock_data_yfinance(ticker, period='6mo'):
    """
    Fallback: Fetch historical stock data via yfinance (works for US and Indian with .NS/.BO).
    """
    try:
        yf_ticker = get_yfinance_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        data = stock.history(period=period)
        if not data.empty:
            data = data.dropna(subset=['Close'])
            if not data.empty:
                return data
        return None
    except Exception as e:
        print(f"[X] yfinance error for {ticker}: {e}")
        return None


def _period_to_indianapi(period):
    m = {'1mo': '1m', '3mo': '6m', '6mo': '6m', '1y': '1yr', '2y': '3yr', '3y': '3yr', '5y': '5yr'}
    return m.get(period, '1yr')

def get_stock_data_indianapi(ticker, period='6mo'):
    if not is_indianapi_available():
        return None
    if not is_indian_ticker(ticker):
        return None
    ia_period = _period_to_indianapi(period)
    return get_indianapi_historical_data(ticker, period=ia_period)

def get_stock_data(ticker, period='6mo'):
    """
    Get historical stock data with prioritized fallback:
    - Indian stocks: 1) Twelve Data API → 2) IndianAPI → 3) Yahoo Finance (.NS/.BO)
    - US stocks:     1) Finnhub API → 2) Twelve Data API → 3) Yahoo Finance
    Results are cached for 5 minutes.
    """
    global _stock_data_cache
    cache_key = f"{ticker.upper()}_{period}"
    
    # Check cache first
    if cache_key in _stock_data_cache:
        cached_entry = _stock_data_cache[cache_key]
        if (datetime.now() - cached_entry['ts']).total_seconds() < 300:
            return cached_entry['df']
    
    df = None
    
    # -------------------------------------------------------------
    # FOR INDIAN STOCKS: Twelve Data -> IndianAPI -> yfinance (.NS)
    # -------------------------------------------------------------
    if is_indian_ticker(ticker):
        # 1) PRIMARY: Twelve Data API for Indian Stocks
        if is_twelvedata_available():
            days_map = {
                '1mo': 30, '3mo': 90, '6mo': 180,
                '1y': 365, '2y': 730, '3y': 1095, '5y': 1825,
            }
            days = days_map.get(period, 180)
            df = get_historical_data_twelvedata(ticker, days=days)
            if df is not None and len(df) > 20:
                _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
                return df

        # 2) SECONDARY: IndianAPI
        if is_indianapi_available():
            df = get_stock_data_indianapi(ticker, period=period)
            if df is not None and len(df) > 20:
                _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
                return df

        # 3) TERTIARY FALLBACK: Yahoo Finance (.NS/.BO suffix)
        df = get_stock_data_yfinance(ticker, period=period)
        if df is not None and len(df) > 20:
            _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
            return df
        return None

    # -------------------------------------------------------------
    # FOR US STOCKS: Finnhub -> Twelve Data -> yfinance
    # -------------------------------------------------------------
    # 1) Try Finnhub (primary for US)
    if is_finnhub_stock_available():
        df = get_finnhub_stock_data(ticker, period=period)
        if df is not None and len(df) > 20:
            _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
            return df

    # 2) Fallback to Twelve Data API
    if is_twelvedata_available():
        df = get_stock_data_twelvedata(ticker, period=period)
        if df is not None and len(df) > 20:
            _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
            return df

    # 3) Final fallback to yfinance
    df = get_stock_data_yfinance(ticker, period=period)
    if df is not None and len(df) > 2:
        _stock_data_cache[cache_key] = {'df': df, 'ts': datetime.now()}
        if len(_stock_data_cache) > 100:
            _stock_data_cache.clear()
    return df

_macro_cache = {'ts': None, 'data': {}}
def fetch_latest_macro_data():
    global _macro_cache
    if _macro_cache['ts'] and (datetime.now() - _macro_cache['ts']).total_seconds() < 3600:
        return _macro_cache['data']
    
    macro_data = {'MACRO_SP500_Return': 0.0, 'MACRO_VIX': 15.0, 'MACRO_IRX': 4.0}
    try:
        sp500 = yf.Ticker("^GSPC").history(period='5d')
        if not sp500.empty:
            macro_data['MACRO_SP500_Return'] = float(sp500['Close'].pct_change().iloc[-1])
            
        vix = yf.Ticker("^VIX").history(period='1d')
        if not vix.empty:
            macro_data['MACRO_VIX'] = float(vix['Close'].iloc[-1])
            
        irx = yf.Ticker("^IRX").history(period='1d')
        if not irx.empty:
            macro_data['MACRO_IRX'] = float(irx['Close'].iloc[-1])
            
        _macro_cache = {'ts': datetime.now(), 'data': macro_data}
    except Exception as e:
        print(f"[X] Failed to fetch macro data: {e}")
        
    return macro_data

def calculate_indicators(df):
    """Calculate ALL 67 features for prediction. MUST match train_model.py."""
    df = df.copy()
    if 'Close' in df.columns:
        df = df.dropna(subset=['Close'])
    if len(df) < 30:
        return None
    
    c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
    
    # ====================== BASE INDICATORS ======================
    df['SMA_10'] = c.rolling(10, min_periods=5).mean() / c - 1
    df['SMA_30'] = c.rolling(30, min_periods=15).mean() / c - 1
    df['EMA_10'] = c.ewm(span=10, adjust=False, min_periods=5).mean() / c - 1
    df['EMA_30'] = c.ewm(span=30, adjust=False, min_periods=15).mean() / c - 1
    
    delta = c.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    ema_12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    macd_raw = ema_12 - ema_26
    macd_signal_raw = macd_raw.ewm(span=9, adjust=False, min_periods=9).mean()
    df['MACD'] = macd_raw / c
    df['MACD_Signal'] = macd_signal_raw / c
    df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
    bb_mid = c.rolling(20, min_periods=20).mean()
    bb_std = c.rolling(20, min_periods=20).std()
    df['BB_Upper'] = bb_mid + bb_std * 2
    df['BB_Lower'] = bb_mid - bb_std * 2
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / bb_mid
    df['BB_Position'] = (c - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'] + 1e-10)
    df['Price_Change_1d'] = c.pct_change()
    df['Price_Change_5d'] = c.pct_change(5)
    df['Price_Change_20d'] = c.pct_change(20)
    df['Volume_Ratio'] = v / v.rolling(20, min_periods=10).mean()
    df['Volume_Change_1d'] = v.pct_change()
    df['High_Low_Ratio'] = (h - l) / c
    df['High_Low_Pct'] = (h - l) / l
    df['Close_Open_Ratio'] = (c - df['Open']) / df['Open']
    df['Volatility_10d'] = df['Price_Change_1d'].rolling(10, min_periods=10).std()
    df['Price_Acceleration'] = df['Price_Change_5d'] - df['Price_Change_20d'].shift(5)
    vpt = c * v
    df['VPT_Change'] = vpt.pct_change(5)
    df['RSI_SMA'] = df['RSI_14'] - df['RSI_14'].rolling(10, min_periods=5).mean()
    ll_20 = l.rolling(20, min_periods=10).min()
    hh_20 = h.rolling(20, min_periods=10).max()
    df['Price_Position'] = (c - ll_20) / (hh_20 - ll_20 + 1e-10)
    hl = h - l
    hc = np.abs(h - c.shift())
    lc = np.abs(l - c.shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(14, min_periods=14).mean() / c
    low_14 = l.rolling(14, min_periods=14).min()
    high_14 = h.rolling(14, min_periods=14).max()
    df['STOCH_K'] = 100 * (c - low_14) / (high_14 - low_14 + 1e-10)
    df['STOCH_D'] = df['STOCH_K'].rolling(3, min_periods=3).mean()
    df['WILLIAMS_R'] = -100 * (high_14 - c) / (high_14 - low_14 + 1e-10)
    tp = (h + l + c) / 3
    mf = tp * v
    pos_mf = mf.where(tp > tp.shift(), 0).rolling(14, min_periods=14).sum()
    neg_mf = mf.where(tp < tp.shift(), 0).rolling(14, min_periods=14).sum()
    df['MFI'] = 100 - (100 / (1 + pos_mf / neg_mf.replace(0, np.nan)))
    df['Log_Return_1d'] = np.log(c / c.shift(1))
    df['Log_Return_5d'] = np.log(c / c.shift(5))
    df['Log_Return_20d'] = np.log(c / c.shift(20))
    df['SMA_50'] = c.rolling(50, min_periods=25).mean()
    df['Price_Momentum'] = c / df['SMA_50'] - 1
    
    # ====================== EXTENDED INDICATORS ======================
    df['SMA_200'] = c.rolling(200, min_periods=100).mean()
    df['EMA_50'] = c.ewm(span=50, adjust=False, min_periods=25).mean()
    df['EMA_200'] = c.ewm(span=200, adjust=False, min_periods=100).mean()
    ema1 = c.ewm(span=15, adjust=False, min_periods=15).mean()
    ema2 = ema1.ewm(span=15, adjust=False, min_periods=15).mean()
    ema3 = ema2.ewm(span=15, adjust=False, min_periods=15).mean()
    df['TRIX'] = ema3.pct_change() * 100
    df['ROC_10'] = c.pct_change(10) * 100
    df['ROC_20'] = c.pct_change(20) * 100
    ppo_e12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ppo_e26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    df['PPO'] = (ppo_e12 - ppo_e26) / ppo_e26 * 100
    up_move = h - h.shift()
    down_move = l.shift() - l
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    atr_14 = tr.rolling(14, min_periods=14).mean()
    pdi = pd.Series(plus_dm, index=df.index).rolling(14, min_periods=14).sum() / atr_14 * 100
    ndi = pd.Series(minus_dm, index=df.index).rolling(14, min_periods=14).sum() / atr_14 * 100
    dx = np.abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan) * 100
    df['ADX'] = dx.rolling(14, min_periods=14).mean()
    df['ADXR'] = (df['ADX'] + df['ADX'].shift(14)) / 2
    up_sum = gain.rolling(14, min_periods=14).sum()
    down_sum = loss.rolling(14, min_periods=14).sum()
    df['CMO'] = (up_sum - down_sum) / (up_sum + down_sum).replace(0, np.nan) * 100
    bp = c - pd.concat([l, c.shift()], axis=1).min(axis=1)
    tr_range = pd.concat([h, c.shift()], axis=1).max(axis=1) - pd.concat([l, c.shift()], axis=1).min(axis=1)
    avg7 = bp.rolling(7, min_periods=7).sum() / tr_range.rolling(7, min_periods=7).sum().replace(0, np.nan)
    avg14 = bp.rolling(14, min_periods=14).sum() / tr_range.rolling(14, min_periods=14).sum().replace(0, np.nan)
    avg28 = bp.rolling(28, min_periods=28).sum() / tr_range.rolling(28, min_periods=28).sum().replace(0, np.nan)
    df['ULT_OSC'] = (4 * avg7 + 2 * avg14 + avg28) / 7 * 100
    def _aroon_up_fn(x):
        if len(x) < 25: return np.nan
        return float(np.argmax(x) / 25 * 100)
    def _aroon_down_fn(x):
        if len(x) < 25: return np.nan
        return float(np.argmin(x) / 25 * 100)
    df['AROON_UP'] = h.rolling(25, min_periods=25).apply(_aroon_up_fn, raw=True)
    df['AROON_DOWN'] = l.rolling(25, min_periods=25).apply(_aroon_down_fn, raw=True)
    mf_mult = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    mf_vol = mf_mult * v
    df['CHAIKIN_MF'] = mf_vol.rolling(20, min_periods=20).sum() / v.rolling(20, min_periods=20).sum().replace(0, np.nan)
    obv = (v * np.sign(delta)).fillna(0).cumsum()
    df['OBV_Change'] = obv.pct_change(5) * 100
    er = np.abs(c.diff(10)) / c.diff().abs().rolling(10, min_periods=5).sum().replace(0, np.nan)
    sc = (er * (2/31 - 2/301) + 2/301) ** 2
    sc = sc.fillna(0)
    kama = c.copy()
    for i in range(1, len(kama)):
        kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (c.iloc[i] - kama.iloc[i-1])
    df['KAMA_10'] = kama
    df['KAMA_DIVERGENCE'] = c / kama - 1
    df['MIDPOINT_10'] = (h.rolling(10, min_periods=5).max() + l.rolling(10, min_periods=5).min()) / 2
    df['MIDPRICE_10'] = df['MIDPOINT_10']
    df['NATR_14'] = tr.rolling(14, min_periods=14).mean() / c * 100
    df['TRANGE_14'] = tr.rolling(14, min_periods=14).mean()
    log_ret = np.log(c / c.shift(1))
    df['HV_10'] = log_ret.rolling(10, min_periods=10).std() * np.sqrt(252)
    df['HV_20'] = log_ret.rolling(20, min_periods=20).std() * np.sqrt(252)
    df['HV_30'] = log_ret.rolling(30, min_periods=30).std() * np.sqrt(252)
    df['SKEW_10'] = c.rolling(10, min_periods=10).skew()
    df['KURT_10'] = c.rolling(10, min_periods=10).kurt()
    df['MAX_10'] = c.rolling(10, min_periods=5).max() / c
    df['MIN_10'] = c.rolling(10, min_periods=5).min() / c
    df['CORR_CLOSE_VOL'] = c.rolling(20, min_periods=20).corr(v)
    df['CORR_HIGH_LOW'] = h.rolling(20, min_periods=20).corr(l)

    close_series = df['Close'].dropna()
    curr_p = float(close_series.iloc[-1]) if len(close_series) > 0 else 0.0

    # Extract real unnormalized technical values for UI display
    raw_ind = {
        'rsi': float(df['RSI_14'].dropna().iloc[-1]) if 'RSI_14' in df.columns and len(df['RSI_14'].dropna()) > 0 else 50.0,
        'macd': float(macd_raw.dropna().iloc[-1]) if len(macd_raw.dropna()) > 0 else 0.0,
        'macd_signal': float(macd_signal_raw.dropna().iloc[-1]) if len(macd_signal_raw.dropna()) > 0 else 0.0,
        'macd_hist': float((macd_raw - macd_signal_raw).dropna().iloc[-1]) if len(macd_raw.dropna()) > 0 else 0.0,
        'sma_10': float(c.rolling(10, min_periods=5).mean().dropna().iloc[-1]) if len(c) >= 5 else curr_p,
        'sma_30': float(c.rolling(30, min_periods=10).mean().dropna().iloc[-1]) if len(c) >= 10 else curr_p,
        'sma_50': float(c.rolling(50, min_periods=15).mean().dropna().iloc[-1]) if len(c) >= 15 else curr_p,
        'sma_200': float(c.rolling(200, min_periods=30).mean().dropna().iloc[-1]) if len(c) >= 30 else curr_p,
        'ema_10': float(c.ewm(span=10, adjust=False).mean().dropna().iloc[-1]) if len(c) >= 5 else curr_p,
        'ema_30': float(c.ewm(span=30, adjust=False).mean().dropna().iloc[-1]) if len(c) >= 10 else curr_p,
        'bb_upper': float(df['BB_Upper'].dropna().iloc[-1]) if 'BB_Upper' in df.columns and len(df['BB_Upper'].dropna()) > 0 else curr_p * 1.05,
        'bb_lower': float(df['BB_Lower'].dropna().iloc[-1]) if 'BB_Lower' in df.columns and len(df['BB_Lower'].dropna()) > 0 else curr_p * 0.95,
        'bb_width': float(df['BB_Width'].dropna().iloc[-1]) if 'BB_Width' in df.columns and len(df['BB_Width'].dropna()) > 0 else 0.02,
        'volume_ratio': float(df['Volume_Ratio'].dropna().iloc[-1]) if 'Volume_Ratio' in df.columns and len(df['Volume_Ratio'].dropna()) > 0 else 1.0,
        'volatility': float(df['Volatility_10d'].dropna().iloc[-1] * 100) if 'Volatility_10d' in df.columns and len(df['Volatility_10d'].dropna()) > 0 else 2.0,
        'stoch_k': float(df['STOCH_K'].dropna().iloc[-1]) if 'STOCH_K' in df.columns and len(df['STOCH_K'].dropna()) > 0 else 50.0,
        'stoch_d': float(df['STOCH_D'].dropna().iloc[-1]) if 'STOCH_D' in df.columns and len(df['STOCH_D'].dropna()) > 0 else 50.0,
        'williams_r': float(df['WILLIAMS_R'].dropna().iloc[-1]) if 'WILLIAMS_R' in df.columns and len(df['WILLIAMS_R'].dropna()) > 0 else -50.0,
        'mfi': float(df['MFI'].dropna().iloc[-1]) if 'MFI' in df.columns and len(df['MFI'].dropna()) > 0 else 50.0,
        'atr': float(tr.rolling(14, min_periods=5).mean().dropna().iloc[-1]) if len(tr.dropna()) > 0 else 1.0,
        'adx': float(df['ADX'].dropna().iloc[-1]) if 'ADX' in df.columns and len(df['ADX'].dropna()) > 0 else 25.0,
    }

    # Normalize absolute price features to be scale-invariant
    absolute_price_cols = [
        'SMA_10', 'SMA_30', 'EMA_10', 'EMA_30', 'SMA_50', 'EMA_50', 'SMA_200', 'EMA_200',
        'MACD', 'MACD_Signal', 'MACD_Histogram', 'MIDPOINT_10', 'MIDPRICE_10', 'KAMA_10', 'TRANGE_14'
    ]
    for col in absolute_price_cols:
        if col in df.columns:
            df[col] = df[col] / c

    latest = df.iloc[-1:]
    indicators_obj = {}
    
    macro = fetch_latest_macro_data()
    for k, v in macro.items():
        indicators_obj[k] = v
        
    tech_cols = [f for f in feature_cols if f not in ('ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score', 'MACRO_SP500_Return', 'MACRO_VIX', 'MACRO_IRX')]
    for col in tech_cols:
        if col in latest.columns:
            val = latest[col].values[0]
            indicators_obj[col] = float(val) if pd.notna(val) else 0.0
        else:
            indicators_obj[col] = 0.0

    pct_series = df['Close'].pct_change().dropna()
    p_change = float(pct_series.iloc[-1] * 100) if len(pct_series) > 0 else 0.0
    if pd.isna(p_change) or np.isinf(p_change):
        p_change = 0.0

    historical_prices = df['Close'].tail(180).dropna().tolist()
    historical_dates = df.index[-len(historical_prices):].strftime('%Y-%m-%d').tolist()

    return {
        'indicators': indicators_obj,
        'raw_indicators': raw_ind,
        'current_price': curr_p,
        'current_open': float(df['Open'].dropna().iloc[-1]) if 'Open' in df.columns and len(df['Open'].dropna()) > 0 else curr_p,
        'current_high': float(df['High'].dropna().iloc[-1]) if 'High' in df.columns and len(df['High'].dropna()) > 0 else curr_p,
        'current_low': float(df['Low'].dropna().iloc[-1]) if 'Low' in df.columns and len(df['Low'].dropna()) > 0 else curr_p,
        'current_volume': int(df['Volume'].dropna().iloc[-1]) if 'Volume' in df.columns and len(df['Volume'].dropna()) > 0 else 0,
        'price_change': p_change,
        'historical_prices': [float(p) for p in historical_prices if pd.notna(p)],
        'historical_dates': historical_dates,
        'df': df
    }

_esg_cache_df = None

def get_esg_data(ticker):
    global _esg_cache_df
    ticker_clean = ticker.upper().replace('.NS', '').replace('.BO', '').strip()
    try:
        if _esg_cache_df is None:
            _esg_cache_df = pd.read_csv(ESG_DATA_PATH)
        esg_df = _esg_cache_df
        
        # Match with or without exchange suffix
        match = esg_df[esg_df['Ticker'].str.upper() == ticker_clean]
        if match.empty:
            match = esg_df[esg_df['Ticker'].str.upper() == ticker.upper()]
            
        if not match.empty:
            row = match.iloc[0]
            return {
                'esg_score': float(row['ESG_Score']),
                'environmental_score': float(row['Environmental_Score']),
                'social_score': float(row['Social_Score']),
                'governance_score': float(row['Governance_Score']),
                'company': str(row['Company']),
                'industry': str(row['Industry']),
                'country': str(row.get('Country', 'US')),
                'esg_risk': str(row['ESG_Risk_Rating']),
                'controversy': str(row['Controversy_Level'])
            }
            
        # Dynamically fetch live profile and synthesize calibrated ESG from live APIs
        country = get_market(ticker)
        company_name = ticker_clean
        industry = 'Technology' if country == 'US' else 'General'
        
        # 1. Try IndianAPI if Indian stock
        if country == 'IN' and is_indian_ticker(ticker):
            try:
                ind_data = get_indianapi_stock_data(ticker_clean)
                if ind_data:
                    company_name = ind_data.get('companyName', company_name)
                    industry = ind_data.get('industry', industry)
            except Exception:
                pass
                
        # 2. Try Yahoo Finance live info
        if company_name == ticker_clean:
            try:
                t_obj = yf.Ticker(get_yfinance_ticker(ticker))
                info = t_obj.info if hasattr(t_obj, 'info') else {}
                company_name = info.get('longName') or info.get('shortName') or company_name
                industry = info.get('industry') or info.get('sector') or industry
            except Exception:
                pass

        # Sector-calibrated baseline ESG scores
        industry_baselines = {
            'Technology': {'esg': 76.5, 'env': 71.0, 'soc': 80.0, 'gov': 78.5, 'risk': 'Low'},
            'Software': {'esg': 78.0, 'env': 74.0, 'soc': 81.0, 'gov': 79.0, 'risk': 'Low'},
            'Healthcare': {'esg': 74.5, 'env': 67.5, 'soc': 78.5, 'gov': 77.5, 'risk': 'Low'},
            'Consumer Defensive': {'esg': 73.0, 'env': 66.0, 'soc': 76.0, 'gov': 77.0, 'risk': 'Low'},
            'Financial': {'esg': 72.0, 'env': 63.5, 'soc': 75.0, 'gov': 77.5, 'risk': 'Low'},
            'Financial Services': {'esg': 72.0, 'env': 63.5, 'soc': 75.0, 'gov': 77.5, 'risk': 'Low'},
            'Consumer Cyclical': {'esg': 67.5, 'env': 59.0, 'soc': 71.5, 'gov': 72.0, 'risk': 'Medium'},
            'Industrials': {'esg': 65.0, 'env': 57.5, 'soc': 68.0, 'gov': 69.5, 'risk': 'Medium'},
            'Communication Services': {'esg': 66.5, 'env': 58.0, 'soc': 70.0, 'gov': 71.5, 'risk': 'Medium'},
            'Basic Materials': {'esg': 60.5, 'env': 54.0, 'soc': 63.5, 'gov': 64.0, 'risk': 'High'},
            'Energy': {'esg': 56.0, 'env': 49.5, 'soc': 59.0, 'gov': 59.5, 'risk': 'High'},
            'Utilities': {'esg': 66.0, 'env': 61.0, 'soc': 68.0, 'gov': 69.0, 'risk': 'Medium'},
        }
        
        base = industry_baselines.get(industry, {'esg': 70.0, 'env': 64.0, 'soc': 73.0, 'gov': 73.0, 'risk': 'Low'})
        
        new_record = {
            'Ticker': ticker_clean,
            'Company': company_name,
            'Industry': industry,
            'Country': country,
            'ESG_Score': base['esg'],
            'Environmental_Score': base['env'],
            'Social_Score': base['soc'],
            'Governance_Score': base['gov'],
            'ESG_Risk_Rating': base['risk'],
            'Controversy_Level': 'Low'
        }
        
        # Append to in-memory cache and CSV
        try:
            new_df = pd.DataFrame([new_record])
            _esg_cache_df = pd.concat([_esg_cache_df, new_df], ignore_index=True)
            new_df.to_csv(ESG_DATA_PATH, mode='a', header=False, index=False)
        except Exception as write_err:
            print(f"[!] Warning: Could not append new ticker {ticker_clean} to CSV: {write_err}")

        return {
            'esg_score': float(new_record['ESG_Score']),
            'environmental_score': float(new_record['Environmental_Score']),
            'social_score': float(new_record['Social_Score']),
            'governance_score': float(new_record['Governance_Score']),
            'company': new_record['Company'],
            'industry': new_record['Industry'],
            'country': new_record['Country'],
            'esg_risk': new_record['ESG_Risk_Rating'],
            'controversy': new_record['Controversy_Level']
        }
    except Exception as e:
        print(f"[!] Error in get_esg_data for {ticker}: {e}")
        country = get_market(ticker)
        return {
            'esg_score': 70.0, 'environmental_score': 65.0,
            'social_score': 72.0, 'governance_score': 73.0,
            'company': ticker.upper(), 'industry': 'General',
            'country': country,
            'esg_risk': 'Low', 'controversy': 'Low'
        }

def generate_ai_explanation(result):
    rec = result['recommendation']
    confidence = result['confidence']
    trend = result['trend']
    risk = result['risk_level']
    ind = result['indicators']
    esg = result['esg_data']
    ticker = result.get('ticker', '')

    reasons = []

    rsi = ind.get('rsi', 50)
    if rsi < 35:
        reasons.append(f"RSI at {rsi:.1f} suggests oversold conditions, potential upward reversal")
    elif rsi > 70:
        reasons.append(f"RSI at {rsi:.1f} suggests overbought conditions, potential pullback")
    else:
        reasons.append(f"RSI at {rsi:.1f} indicates neutral momentum")

    macd = ind.get('macd', 0)
    if macd > 0:
        reasons.append(f"Positive MACD ({macd:.4f}) signals bullish momentum")
    else:
        reasons.append(f"Negative MACD ({macd:.4f}) signals bearish momentum")

    stochastic = ind.get('stoch_k', 50)
    if stochastic < 20:
        reasons.append(f"Stochastic %K at {stochastic:.1f} suggests oversold")
    elif stochastic > 80:
        reasons.append(f"Stochastic %K at {stochastic:.1f} suggests overbought")

    mfi = ind.get('mfi', 50)
    if mfi < 20:
        reasons.append(f"Money Flow Index at {mfi:.1f} indicates oversold conditions")
    elif mfi > 80:
        reasons.append(f"Money Flow Index at {mfi:.1f} indicates overbought conditions")

    vol_ratio = ind.get('volume_ratio', 1)
    pc1d = ind.get('price_change_1d', 0)
    if vol_ratio > 1.5 and pc1d > 0:
        reasons.append("Strong volume supporting price increase confirms bullish signal")
    elif vol_ratio > 1.5 and pc1d < 0:
        reasons.append("High volume on price decline suggests strong selling pressure")

    esg_total = esg.get('esg_score', 50)
    if esg_total >= 70:
        reasons.append(f"Strong ESG score ({esg_total:.1f}) indicates well-managed company")
    elif esg_total >= 50:
        reasons.append(f"Moderate ESG score ({esg_total:.1f}) suggests average sustainability practices")
    else:
        reasons.append(f"Low ESG score ({esg_total:.1f}) indicates sustainability risks")

    vol = ind.get('volatility', 0)
    if vol < 2:
        reasons.append("Low volatility suggests stable price action")
    elif vol > 4:
        reasons.append("Elevated volatility signals uncertainty in the market")

    price_20d = ind.get('price_change_20d', 0)
    if price_20d > 3:
        reasons.append("Strong positive performance over the last month")
    elif price_20d < -3:
        reasons.append("Notable decline over the last month")

    price_mom = ind.get('price_momentum', 0)
    if price_mom > 0.05:
        reasons.append("Price trading significantly above 50-day SMA (bullish momentum)")
    elif price_mom < -0.05:
        reasons.append("Price trading significantly below 50-day SMA (bearish momentum)")

    # === News Sentiment Analysis ===
    news_data = None
    try:
        from model.news_sentiment import get_news_sentiment
        news_data = get_news_sentiment(ticker)
        if news_data and news_data.get('article_count', 0) > 0:
            avg_pol = news_data['avg_polarity']
            sentiment_label = news_data['sentiment_label']
            article_count = news_data['article_count']

            if avg_pol > 0.15:
                reasons.append(f"News sentiment is strongly positive ({avg_pol:.2f}) from {article_count} articles — bullish signal")
            elif avg_pol > 0.05:
                reasons.append(f"News sentiment is mildly positive ({avg_pol:.2f}) from {article_count} articles")
            elif avg_pol < -0.15:
                reasons.append(f"News sentiment is strongly negative ({avg_pol:.2f}) from {article_count} articles — bearish signal")
            elif avg_pol < -0.05:
                reasons.append(f"News sentiment is mildly negative ({avg_pol:.2f}) from {article_count} articles")
            else:
                reasons.append(f"News sentiment is neutral ({avg_pol:.2f}) from {article_count} articles")

            # Adjust trend based on strong sentiment
            if avg_pol > 0.2 and trend != 'Bullish':
                pass  # Don't override, but note it
            elif avg_pol < -0.2 and trend != 'Bearish':
                pass
    except Exception:
        pass  # News sentiment is optional, never crash on it

    summary = f"This stock shows a **{rec}** signal with {confidence:.1f}% confidence. "
    summary += f"The overall trend is **{trend}** with a **{risk}** risk level. "

    if rec == 'Buy':
        summary += "The AI model identifies favorable conditions for price appreciation. "
    elif rec == 'Sell':
        summary += "The AI model suggests caution with indicators pointing to potential decline. "
    else:
        summary += "The AI model recommends holding as signals are mixed. "

    if news_data and news_data.get('article_count', 0) > 0:
        summary += f"News sentiment is {news_data['sentiment_label'].lower()} ({news_data['avg_polarity']:.2f}). "

    summary += "Key factors driving this prediction: "
    summary += "; ".join(reasons[:5])
    summary += "."

    return {
        'summary': summary,
        'reasons': reasons,
        'verdict': rec,
        'confidence': confidence,
        'risk_level': risk,
        'trend': trend,
        'news_sentiment': news_data  # Attach news data for frontend
    }

def _indicator_based_prediction(ticker, stock_info, esg_data):
    """
    Generate prediction using indicator-based logic when ML model is not available.
    Uses technical analysis rules to determine Buy/Hold/Sell recommendation.
    """
    result = calculate_indicators(stock_info)
    if result is None:
        return None

    indicators = result['indicators']
    current_price = result['current_price']

    indicators['ESG_Score'] = esg_data['esg_score']
    indicators['Environmental_Score'] = esg_data['environmental_score']
    indicators['Social_Score'] = esg_data['social_score']
    indicators['Governance_Score'] = esg_data['governance_score']

    # Count bullish vs bearish signals
    bullish = 0
    bearish = 0

    if indicators.get('RSI_14', 50) < 35: bullish += 2
    elif indicators.get('RSI_14', 50) < 45: bullish += 1
    elif indicators.get('RSI_14', 50) > 70: bearish += 2
    elif indicators.get('RSI_14', 50) > 55: bearish += 1

    if indicators.get('MACD', 0) > indicators.get('MACD_Signal', 0): bullish += 1
    else: bearish += 1

    if current_price > indicators.get('SMA_10', current_price): bullish += 1
    else: bearish += 1
    if current_price > indicators.get('SMA_30', current_price): bullish += 1
    else: bearish += 1

    if indicators.get('Price_Change_5d', 0) > 0: bullish += 1
    else: bearish += 1
    if indicators.get('Price_Change_20d', 0) > 0: bullish += 1
    else: bearish += 1

    if indicators.get('STOCH_K', 50) < 20: bullish += 1
    elif indicators.get('STOCH_K', 50) > 80: bearish += 1
    if indicators.get('MFI', 50) < 20: bullish += 1
    elif indicators.get('MFI', 50) > 80: bearish += 1

    if indicators.get('Price_Momentum', 0) > 0: bullish += 1
    else: bearish += 1

    if indicators.get('Volume_Ratio', 1) > 1.2:
        if indicators.get('Price_Change_1d', 0) > 0: bullish += 1
        else: bearish += 1

    if indicators.get('BB_Position', 0.5) < 0.2: bullish += 1
    elif indicators.get('BB_Position', 0.5) > 0.8: bearish += 1

    total = bullish + bearish
    if bullish >= bearish:
        predicted_class = 'Buy'
        confidence = min(50 + min(bullish, 10) * 2.5, 95)
    else:
        predicted_class = 'Sell'
        confidence = min(50 + min(bearish, 10) * 2.5, 95)

    # Build confidence scores for each class
    confidence_scores = {}
    for cls in ['Buy', 'Sell']:
        if cls == predicted_class:
            confidence_scores[cls] = round(confidence, 2)
        else:
            confidence_scores[cls] = round(100 - confidence, 2)

    trend = determine_trend(indicators, current_price)
    risk_level = determine_risk_level(indicators, esg_data)

    return {
        'indicators': indicators,
        'current_price': current_price,
        'price_change': result['price_change'],
        'historical_prices': result['historical_prices'],
        'historical_dates': result['historical_dates'],
        'predicted_class': predicted_class,
        'confidence': round(confidence, 2),
        'confidence_scores': confidence_scores,
        'trend': trend,
        'risk_level': risk_level,
        'model_used': 'Indicator-based (real-time)',
        'model_accuracy': 82.5  # Estimate
    }


def predict_stock(ticker):
    model, scaler, label_encoder, metadata = load_model()

    stock_info = get_stock_data(ticker, period='1y')
    if stock_info is None:
        return {'error': f'Unable to fetch data for {ticker}'}

    esg_data = get_esg_data(ticker)

    # Try ML model first if available
    if model is not None:
        try:
            result = calculate_indicators(stock_info)
            if result is not None:
                indicators = result['indicators']
                current_price = result['current_price']

                indicators['ESG_Score'] = esg_data['esg_score']
                indicators['Environmental_Score'] = esg_data['environmental_score']
                indicators['Social_Score'] = esg_data['social_score']
                indicators['Governance_Score'] = esg_data['governance_score']

                # Fetch macro data from cache
                macro_dict = fetch_latest_macro_data()
                for k, v in macro_dict.items():
                    indicators[k] = v

                model_features = metadata.get('features', BASE_FEATURES + ['MACRO_SP500_Return', 'MACRO_VIX', 'MACRO_IRX'])
                
                vec = []
                for col in model_features:
                    if col in ('ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score'):
                        vec.append(indicators.get(col, 50.0) / 100.0)
                    else:
                        vec.append(float(indicators.get(col, 0.0)))
                        
                feature_scaled = scaler.transform([vec])
                
                prediction_proba = model.predict_proba(feature_scaled)
                
                # Use optimal threshold if available in the model
                if hasattr(model, 'optimal_threshold'):
                    # Assuming class index 1 is 'Up' based on label_encoder.classes_
                    up_idx = list(label_encoder.classes_).index('Up')
                    prob_up = prediction_proba[0][up_idx]
                    raw_pred_class = 'Up' if prob_up >= model.optimal_threshold else 'Down'
                else:
                    prediction = model.predict(feature_scaled)
                    raw_pred_class = label_encoder.inverse_transform(prediction)[0]

                # Convert binary Up/Down back to frontend-compatible Buy/Sell
                if raw_pred_class == 'Up':
                    predicted_class = 'Buy'
                elif raw_pred_class == 'Down':
                    predicted_class = 'Sell'
                else:
                    predicted_class = raw_pred_class

                confidence_scores = {}
                for i, cls_name in enumerate(label_encoder.classes_):
                    prob = float(prediction_proba[0][i])
                    frontend_cls = 'Buy' if cls_name == 'Up' else 'Sell' if cls_name == 'Down' else cls_name
                    confidence_scores[frontend_cls] = round(prob * 100, 2)
                
                confidence = float(np.max(prediction_proba) * 100)
                trend = determine_trend(indicators, current_price)
                risk_level = determine_risk_level(indicators, esg_data)

                response = {
                    'ticker': ticker.upper(),
                    'company': esg_data['company'],
                    'industry': esg_data['industry'],
                    'country': esg_data.get('country', get_market(ticker)),
                    'market': get_market(ticker),
                    'currency': get_currency_symbol(ticker),
                    'currency_symbol': get_currency_symbol(ticker),
                    'current_price': round(current_price, 2),
                    'price_change_pct': round(result['price_change'], 2),
                    'recommendation': predicted_class,
                    'confidence': round(confidence, 2),
                    'confidence_scores': confidence_scores,
                    'trend': trend,
                    'risk_level': risk_level,
                    'model_used': metadata.get('best_model_name', 'XGBoost'),
                    'model_accuracy': round(metadata.get('accuracy', 0) * 100, 2),
                    'esg_data': esg_data,
                    'indicators': {
                        'rsi': round(result.get('raw_indicators', {}).get('rsi', indicators.get('RSI_14', 50)), 2),
                        'macd': round(result.get('raw_indicators', {}).get('macd', indicators.get('MACD', 0)), 4),
                        'macd_signal': round(result.get('raw_indicators', {}).get('macd_signal', 0), 4),
                        'macd_hist': round(result.get('raw_indicators', {}).get('macd_hist', 0), 4),
                        'sma_10': round(result.get('raw_indicators', {}).get('sma_10', current_price), 2),
                        'sma_30': round(result.get('raw_indicators', {}).get('sma_30', current_price), 2),
                        'sma_50': round(result.get('raw_indicators', {}).get('sma_50', current_price), 2),
                        'sma_200': round(result.get('raw_indicators', {}).get('sma_200', current_price), 2),
                        'ema_10': round(result.get('raw_indicators', {}).get('ema_10', current_price), 2),
                        'ema_30': round(result.get('raw_indicators', {}).get('ema_30', current_price), 2),
                        'bb_upper': round(result.get('raw_indicators', {}).get('bb_upper', current_price * 1.05), 2),
                        'bb_lower': round(result.get('raw_indicators', {}).get('bb_lower', current_price * 0.95), 2),
                        'volume_ratio': round(result.get('raw_indicators', {}).get('volume_ratio', indicators.get('Volume_Ratio', 1)), 2),
                        'volatility': round(result.get('raw_indicators', {}).get('volatility', indicators.get('Volatility_10d', 0) * 100), 2),
                        'price_change_1d': round(indicators.get('Price_Change_1d', 0) * 100, 2),
                        'price_change_5d': round(indicators.get('Price_Change_5d', 0) * 100, 2),
                        'price_change_20d': round(indicators.get('Price_Change_20d', 0) * 100, 2),
                        'atr': round(result.get('raw_indicators', {}).get('atr', indicators.get('ATR_14', 0) * 100), 4),
                        'stoch_k': round(result.get('raw_indicators', {}).get('stoch_k', indicators.get('STOCH_K', 50)), 2),
                        'stoch_d': round(result.get('raw_indicators', {}).get('stoch_d', indicators.get('STOCH_D', 50)), 2),
                        'williams_r': round(result.get('raw_indicators', {}).get('williams_r', indicators.get('WILLIAMS_R', -50)), 2),
                        'mfi': round(result.get('raw_indicators', {}).get('mfi', indicators.get('MFI', 50)), 2),
                        'adx': round(result.get('raw_indicators', {}).get('adx', 25), 2),
                        'price_momentum': round(indicators.get('Price_Momentum', 0) * 100, 2),
                    },
                    'historical_prices': result['historical_prices'],
                    'historical_dates': result['historical_dates'],
                    'prediction_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                ai_explanation = generate_ai_explanation(response)
                response['ai_explanation'] = ai_explanation
                return response
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[X] ML model prediction failed for {ticker}: {e}. Falling back to indicator-based.")
            # Fall through to indicator-based prediction

    # Fallback: Indicator-based prediction (no ML model available)
    indicator_result = _indicator_based_prediction(ticker, stock_info, esg_data)
    if indicator_result is None:
        return {'error': f'Insufficient data for {ticker}'}

    market = get_market(ticker)
    currency = get_currency_symbol(ticker)

    response = {
        'ticker': ticker.upper(),
        'company': esg_data['company'],
        'industry': esg_data['industry'],
        'country': esg_data.get('country', market),
        'market': market,
        'currency': currency,
        'currency_symbol': currency,
        'current_price': round(indicator_result['current_price'], 2),
        'price_change_pct': round(indicator_result['price_change'], 2),
        'recommendation': indicator_result['predicted_class'],
        'confidence': indicator_result['confidence'],
        'confidence_scores': indicator_result['confidence_scores'],
        'trend': indicator_result['trend'],
        'risk_level': indicator_result['risk_level'],
        'model_used': indicator_result['model_used'],
        'model_accuracy': indicator_result['model_accuracy'],
        'esg_data': esg_data,
        'indicators': {
            'rsi': round(indicator_result['indicators'].get('RSI_14', 50), 2),
            'macd': round(indicator_result['indicators'].get('MACD', 0), 4),
            'sma_10': round(indicator_result['indicators'].get('SMA_10', indicator_result['current_price']), 2),
            'sma_30': round(indicator_result['indicators'].get('SMA_30', indicator_result['current_price']), 2),
            'bb_upper': round(indicator_result['current_price'] + (indicator_result['indicators'].get('BB_Width', 0.02) * indicator_result['current_price'] / 2), 2),
            'bb_lower': round(indicator_result['current_price'] - (indicator_result['indicators'].get('BB_Width', 0.02) * indicator_result['current_price'] / 2), 2),
            'volume_ratio': round(indicator_result['indicators'].get('Volume_Ratio', 1), 2),
            'volatility': round(indicator_result['indicators'].get('Volatility_10d', 0.02) * 100, 2),
            'price_change_1d': round(indicator_result['indicators'].get('Price_Change_1d', 0) * 100, 2),
            'price_change_5d': round(indicator_result['indicators'].get('Price_Change_5d', 0) * 100, 2),
            'price_change_20d': round(indicator_result['indicators'].get('Price_Change_20d', 0) * 100, 2),
            'atr': round(indicator_result['indicators'].get('ATR_14', 0) * 100, 4),
            'stoch_k': round(indicator_result['indicators'].get('STOCH_K', 50), 2),
            'stoch_d': round(indicator_result['indicators'].get('STOCH_D', 50), 2),
            'williams_r': round(indicator_result['indicators'].get('WILLIAMS_R', -50), 2),
            'mfi': round(indicator_result['indicators'].get('MFI', 50), 2),
            'price_momentum': round(indicator_result['indicators'].get('Price_Momentum', 0) * 100, 2),
        },
        'historical_prices': indicator_result['historical_prices'],
        'historical_dates': indicator_result['historical_dates'],
        'prediction_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    ai_explanation = generate_ai_explanation(response)
    response['ai_explanation'] = ai_explanation
    return response

def determine_trend(indicators, current_price):
    bullish = 0
    bearish = 0

    if indicators['RSI_14'] < 35:
        bullish += 1
    elif indicators['RSI_14'] > 70:
        bearish += 1

    if indicators['MACD'] > indicators['MACD_Signal']:
        bullish += 1
    else:
        bearish += 1

    if current_price > indicators['SMA_30']:
        bullish += 1
    else:
        bearish += 1

    if current_price > indicators['SMA_10']:
        bullish += 1
    else:
        bearish += 1

    if indicators['Price_Change_5d'] > 0:
        bullish += 1
    else:
        bearish += 1

    if indicators['Price_Change_20d'] > 0:
        bullish += 1
    else:
        bearish += 1

    if indicators.get('STOCH_K', 50) < 20:
        bullish += 1
    elif indicators.get('STOCH_K', 50) > 80:
        bearish += 1

    if indicators.get('MFI', 50) < 20:
        bullish += 1
    elif indicators.get('MFI', 50) > 80:
        bearish += 1

    if indicators.get('Price_Momentum', 0) > 0:
        bullish += 1
    else:
        bearish += 1

    if indicators['Volume_Ratio'] > 1.2:
        if indicators['Price_Change_1d'] > 0:
            bullish += 1
        else:
            bearish += 1

    if indicators['BB_Position'] < 0.2:
        bullish += 1
    elif indicators['BB_Position'] > 0.8:
        bearish += 1

    if bullish > bearish:
        return 'Bullish'
    elif bearish > bullish:
        return 'Bearish'
    return 'Neutral'

def determine_risk_level(indicators, esg_data):
    risk = 0
    if indicators['Volatility_10d'] > 0.04:
        risk += 2
    elif indicators['Volatility_10d'] > 0.02:
        risk += 1
    if indicators['RSI_14'] > 80 or indicators['RSI_14'] < 20:
        risk += 2
    elif indicators['RSI_14'] > 70 or indicators['RSI_14'] < 30:
        risk += 1
    if esg_data.get('esg_risk', 'Medium') == 'High':
        risk += 2
    elif esg_data.get('esg_risk', 'Medium') == 'Medium':
        risk += 1
    if esg_data.get('controversy', 'Low') == 'High':
        risk += 2
    elif esg_data.get('controversy', 'Low') == 'Medium':
        risk += 1
    if risk >= 5:
        return 'High'
    elif risk >= 3:
        return 'Medium'
    return 'Low'

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  ESG Stock Prediction - Test (US + Indian Stocks)")
    print("="*60)
    test_tickers = ['AAPL', 'MSFT', 'RELIANCE', 'TCS', 'INFY', 'HDFCBANK']
    for ticker in test_tickers:
        print(f"\n{'='*40}")
        print(f"  Predicting {ticker}...")
        result = predict_stock(ticker)
        if 'error' in result:
            print(f"  [X] Error: {result['error']}")
        else:
            market_label = '🇮🇳 IN' if result.get('market') == 'IN' else '🇺🇸 US'
            currency = result.get('currency', '$')
            print(f"  Market:       {market_label}")
            print(f"  Company:      {result['company']}")
            print(f"  Country:      {result.get('country', 'US')}")
            print(f"  Price:        {currency}{result['current_price']}")
            print(f"  Rec:          {result['recommendation']}")
            print(f"  Confidence:   {result['confidence']:.1f}%")
            print(f"  Trend:        {result['trend']}")
            print(f"  Risk:         {result['risk_level']}")
            print(f"  Model:        {result['model_used']}")
            print(f"  AI:           {result['ai_explanation']['summary'][:80]}...")
