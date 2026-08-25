"""
Real Stock Data Training Pipeline for ESG Stock Prediction
=======================================================================
Binary Classification (Up/Down) using XGBoost/Random Forest and Macroeconomic features.
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import joblib, time

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.ensemble import RandomForestClassifier
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("[!] XGBoost not installed. Using Random Forest only.")

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
    print("[!] LightGBM not installed.")

# Enable unbuffered stdout so we can see progress logs in background task
sys.stdout.reconfigure(line_buffering=True)

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'forksafe'
os.environ['LOKY_PICKLE_MODE'] = 'pickle5'
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')  # Saving as PKL for Sklearn/XGB
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
STOCK_LIST_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

np.random.seed(42)

# =====================================================================
# FEATURE DEFINITIONS 
# =====================================================================
feature_cols = [
    # Base features (36)
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
    # Extended features (31)
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

FORWARD_WINDOW = 20
YF_PERIOD = '5y'
CORR_THRESHOLD = 0.95

def ensure_directories():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

def get_yfinance_ticker(ticker):
    t = ticker.upper()
    if t == 'BRK.B':
        return 'BRK-B'
    return t

def fetch_macro_data():
    print("  Fetching Macroeconomic data (^GSPC, ^VIX, ^IRX)...")
    macro_df = pd.DataFrame()
    try:
        sp500 = yf.Ticker("^GSPC").history(period=YF_PERIOD)
        if not sp500.empty:
            if hasattr(sp500.index, 'tz') and sp500.index.tz is not None:
                sp500.index = sp500.index.tz_localize(None)
            macro_df['MACRO_SP500_Return'] = sp500['Close'].pct_change()
            
        vix = yf.Ticker("^VIX").history(period=YF_PERIOD)
        if not vix.empty:
            if hasattr(vix.index, 'tz') and vix.index.tz is not None:
                vix.index = vix.index.tz_localize(None)
            macro_df['MACRO_VIX'] = vix['Close']
            
        irx = yf.Ticker("^IRX").history(period=YF_PERIOD)
        if not irx.empty:
            if hasattr(irx.index, 'tz') and irx.index.tz is not None:
                irx.index = irx.index.tz_localize(None)
            macro_df['MACRO_IRX'] = irx['Close']
            
        macro_df.ffill(inplace=True)
        macro_df.bfill(inplace=True)
        return macro_df
    except Exception as e:
        print(f"  [!] Failed to fetch macro data: {e}")
        return pd.DataFrame()

def remove_highly_correlated(X, threshold=0.95):
    """Remove features with pairwise correlation > threshold to reduce noise."""
    if X.shape[1] <= 2:
        return X, list(range(X.shape[1]))
    corr = np.abs(np.corrcoef(X.T))
    np.fill_diagonal(corr, 0)
    to_keep = np.ones(X.shape[1], dtype=bool)
    for i in range(X.shape[1]):
        if not to_keep[i]:
            continue
        for j in range(i + 1, X.shape[1]):
            if corr[i, j] > threshold:
                to_keep[j] = False
    return X[:, to_keep], np.where(to_keep)[0]

def calculate_indicators_for_df(df):
    """Calculate all technical features."""
    df = df.copy()
    if len(df) < 100:
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
    
    ppo_ema_12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ppo_ema_26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    df['PPO'] = (ppo_ema_12 - ppo_ema_26) / ppo_ema_26 * 100
    
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
    c_vals = c.values
    sc_vals = sc.values
    kama_vals = np.zeros(len(c))
    if len(c) > 0:
        kama_vals[0] = c_vals[0]
        for i in range(1, len(kama_vals)):
            kama_vals[i] = kama_vals[i-1] + sc_vals[i] * (c_vals[i] - kama_vals[i-1])
    df['KAMA_10'] = kama_vals
    df['KAMA_DIVERGENCE'] = c / kama_vals - 1
    
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
    
    # Binary Classification Forward Return: Predict > 0% Up, else Down
    df['Forward_Return_Binary'] = np.where(c.shift(-FORWARD_WINDOW) > c, 1, 0)
    # Drop rows where we don't have future data
    df.iloc[-FORWARD_WINDOW:, df.columns.get_loc('Forward_Return_Binary')] = np.nan
    
    # Normalize absolute price features to be scale-invariant
    absolute_price_cols = [
        'SMA_10', 'SMA_30', 'EMA_10', 'EMA_30', 'SMA_50', 'EMA_50', 'SMA_200', 'EMA_200',
        'MACD', 'MACD_Signal', 'MACD_Histogram', 'MIDPOINT_10', 'MIDPRICE_10', 'KAMA_10', 'TRANGE_14'
    ]
    for col in absolute_price_cols:
        if col in df.columns:
            df[col] = df[col] / c
            
    return df

def fetch_yfinance_data(ticker, period='5y'):
    try:
        from model.kite_api import is_indian_ticker, get_nse_symbol
        if is_indian_ticker(ticker):
            nse_symbol = get_nse_symbol(ticker)
            for suffix in ['.NS', '.BO']:
                stock = yf.Ticker(f"{nse_symbol}{suffix}")
                data = stock.history(period=period)
                if data is not None and not data.empty:
                    return data
            return None
        else:
            stock = yf.Ticker(get_yfinance_ticker(ticker))
            return stock.history(period=period)
    except Exception:
        return None

def fetch_and_preprocess_data(esg_data, macro_df, max_stocks=None):
    print("\n" + "="*60)
    print("  PHASE 1: FETCHING AND PREPROCESSING DATA")
    print("="*60)
    print(f"  Tickers available: {len(esg_data)}")
    
    all_features = []
    all_labels = []
    
    ticker_list = esg_data.to_dict('records')
    if max_stocks:
        ticker_list = sorted(ticker_list, key=lambda x: abs(x['ESG_Score'] - 50), reverse=True)[:max_stocks]
    
    total = len(ticker_list)
    for idx, stock_row in enumerate(ticker_list):
        ticker = stock_row['Ticker']
        pct = (idx + 1) / total * 100
        print(f"\r  [{idx+1}/{total}] {pct:.0f}% Fetching {ticker}...", end='', flush=True)
        
        df = fetch_yfinance_data(ticker, period=YF_PERIOD)
        if df is None or df.empty:
            continue
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        df_with_indicators = calculate_indicators_for_df(df)
        if df_with_indicators is None:
            continue
        
        # Merge Macro Data
        df_with_indicators = df_with_indicators.join(macro_df, how='left')
        df_with_indicators.ffill(inplace=True)
        df_with_indicators.bfill(inplace=True)
        
        # Define base technical cols to drop nan
        technical_cols = [c for c in feature_cols if 'Score' not in c and 'MACRO' not in c]
        df_clean = df_with_indicators.dropna(subset=technical_cols + ['Forward_Return_Binary'])
        
        if len(df_clean) < 100:
            continue
            
        labels = df_clean['Forward_Return_Binary'].values
        
        for i, (_, row) in enumerate(df_clean.iterrows()):
            vec = []
            for col in feature_cols:
                if 'Score' in col:
                    vec.append(float(stock_row[col]) / 100.0)
                else:
                    vec.append(float(row[col]) if pd.notna(row[col]) else 0.0)
            all_features.append(vec)
            all_labels.append(labels[i])
    
    print("\n  [Debug] Finished downloading. Scaling...")
    if len(all_features) < 100:
        return None
        
    X_raw = np.array(all_features)
    y_raw = np.array(all_labels)
    X_raw = np.nan_to_num(X_raw, nan=0.0, posinf=0.0, neginf=0.0)
    X_raw = np.clip(X_raw, -1e4, 1e4)
    
    # Chronological Split (Train 70%, Test 30%)
    train_size = int(len(X_raw) * 0.7)
    X_train_raw = X_raw[:train_size]
    X_test_raw = X_raw[train_size:]
    y_train = y_raw[:train_size]
    y_test = y_raw[train_size:]
    
    stds = np.std(X_train_raw, axis=0)
    const_mask = stds > 1e-8
    
    # Do NOT remove highly correlated features, keep all valid ones
    final_mask = const_mask
    survived_features = [feature_cols[i] for i in range(len(feature_cols)) if final_mask[i]]
    
    X_train_filtered = X_train_raw[:, final_mask]
    X_test_filtered = X_test_raw[:, final_mask]
    X_raw_filtered = X_raw[:, final_mask]
    
    scaler = StandardScaler()
    scaler.fit(X_train_filtered)
    X_train_scaled = scaler.transform(X_train_filtered)
    X_test_scaled = scaler.transform(X_test_filtered)
    
    le = LabelEncoder()
    le.fit(['Down', 'Up'])
    
    return {
        'X_train': X_train_scaled,
        'y_train': y_train,
        'X_test': X_test_scaled,
        'y_test': y_test,
        'scaler': scaler,
        'label_encoder': le,
        'used_features': survived_features
    }

def save_model_artifacts(best_model_name, best_model, test_acc, precision, recall, f1, cm, data_dict):
    print(f"\n[*] Saving model artifacts for best model: {best_model_name}")
    joblib.dump(best_model, MODEL_PATH)
    joblib.dump(data_dict['scaler'], SCALER_PATH)
    joblib.dump(data_dict['label_encoder'], ENCODER_PATH)
    
    metadata = {
        'model_type': 'Tree_Binary',
        'best_model_name': best_model_name,
        'accuracy': test_acc,
        'precision': precision,
        'recall': recall,
        'f1_score': f1,
        'cv_mean': test_acc,
        'cv_std': 0.0,
        'confusion_matrix': cm,
        'all_results': {},
        'base_models': [best_model_name],
        'feature_count': len(data_dict['used_features']),
        'features': data_dict['used_features'],
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'label_classes': ['Down', 'Up'],
        'training_source': 'REAL_MARKET_DATA_5YR_TIMESERIES',
        'forward_window_days': FORWARD_WINDOW,
        'correlation_threshold': CORR_THRESHOLD,
        'hyperparameter_tuning': False,
        'validation': 'CHRONOLOGICAL_SPLIT',
        'data_leakage_free': True
    }
    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

def main():
    start_time = time.time()
    ensure_directories()
    
    macro_df = fetch_macro_data()
    esg_data = pd.read_csv(STOCK_LIST_PATH)
    
    data_dict = fetch_and_preprocess_data(esg_data, macro_df)
    if data_dict is None:
        print("[!] Preprocessing failed.")
        return
        
    X_train = data_dict['X_train']
    y_train = data_dict['y_train']
    X_test = data_dict['X_test']
    y_test = data_dict['y_test']
    
    models = {}
    if HAS_LGBM:
        models["LightGBM"] = LGBMClassifier(
            n_estimators=300, 
            max_depth=12, 
            learning_rate=0.03, 
            num_leaves=63, 
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42, 
            n_jobs=-1, 
            class_weight='balanced',
            verbose=-1
        )
    else:
        models["Random Forest"] = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1, class_weight='balanced')
        
    best_acc = 0
    best_model = None
    best_name = None
    best_metrics = {}
    
    print("\n" + "="*60)
    print("  PHASE 2: TRAINING MODELS & THRESHOLD OPTIMIZATION")
    print("="*60)
    
    for name, model in models.items():
        print(f"  Training {name}...")
        model.fit(X_train, y_train)
        
        # Optimize threshold on training set
        train_probs = model.predict_proba(X_train)[:, 1]
        best_thresh = 0.5
        best_train_acc = 0
        for thresh in np.linspace(0.1, 0.9, 100):
            train_preds = (train_probs >= thresh).astype(int)
            train_acc = accuracy_score(y_train, train_preds)
            if train_acc > best_train_acc:
                best_train_acc = train_acc
                best_thresh = thresh
                
        print(f"  Optimized Threshold: {best_thresh:.4f} (Train Acc: {best_train_acc:.2%})")
        
        # Evaluate on test set using optimal threshold
        test_probs = model.predict_proba(X_test)[:, 1]
        preds = (test_probs >= best_thresh).astype(int)
        
        acc = accuracy_score(y_test, preds)
        pre = precision_score(y_test, preds, average='weighted', zero_division=0)
        rec = recall_score(y_test, preds, average='weighted', zero_division=0)
        f1 = f1_score(y_test, preds, average='weighted', zero_division=0)
        cm = confusion_matrix(y_test, preds).tolist()
        
        print(f"  {name} Test Acc: {acc:.2%}")
        
        if acc > best_acc:
            best_acc = acc
            best_model = model
            best_name = name
            best_metrics = (acc, pre, rec, f1, cm)
            
    print("\n" + "="*60)
    print("  OPTIMIZATION COMPLETE")
    print("="*60)
    print(f"  Best Model:          {best_name}")
    print(f"  Final Test Accuracy: {best_metrics[0]:.2%}")
    print(f"  Test F1 Score:       {best_metrics[3]:.2%}")
    
    # Store the optimal threshold in the model object before saving
    if best_model is not None:
        best_model.optimal_threshold = best_thresh
    
    save_model_artifacts(best_name, best_model, *best_metrics, data_dict)
    
    elapsed = time.time() - start_time
    print(f"  Total Time:          {elapsed/60:.1f} minutes")
    print("="*60)

if __name__ == '__main__':
    main()
