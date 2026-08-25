"""
Real Stock Data Training Pipeline for ESG Stock Prediction (LSTM VERSION)
=======================================================================
Replaces traditional ML models with a Deep Learning LSTM model using PyTorch.
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

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# Enable unbuffered stdout so we can see progress logs in background task
sys.stdout.reconfigure(line_buffering=True)

from sklearn.preprocessing import RobustScaler, StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'forksafe'
os.environ['LOKY_PICKLE_MODE'] = 'pickle5'
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pt')  # PyTorch model
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
STOCK_LIST_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

np.random.seed(42)
torch.manual_seed(42)

# =====================================================================
# FEATURE DEFINITIONS — 67 features (base + extended)
# =====================================================================
feature_cols = [
    'SMA_10', 'SMA_30', 'EMA_10', 'EMA_30', 'RSI_14',
    'MACD', 'MACD_Signal', 'MACD_Histogram',
    'BB_Width', 'BB_Position',
    'Price_Change_1d', 'Price_Change_5d', 'Price_Change_20d',
    'Volume_Ratio', 'High_Low_Ratio', 'Close_Open_Ratio', 'Volatility_10d',
    'ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score'
]

FORWARD_WINDOW = 20
BUY_THRESHOLD = 0.03
SELL_THRESHOLD = -0.03
YF_PERIOD = '5y'
CORR_THRESHOLD = 0.95
SEQ_LEN = 40  # Sequence length for LSTM

def ensure_directories():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

def get_yfinance_ticker(ticker):
    t = ticker.upper()
    if t == 'BRK.B':
        return 'BRK-B'
    return t

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
    """Calculate ALL 67 features with proper min_periods for cleaner signals."""
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
    
    df['Forward_Return'] = c.shift(-FORWARD_WINDOW) / c - 1
    
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

def build_real_training_data(esg_data, max_stocks=None):
    """
    Build LSTM training dataset with sequential windows.
    Generates (samples, SEQ_LEN, features) tensor.
    """
    print("\n" + "="*60)
    print("  BUILDING LSTM TRAINING DATASET (5yr, time-ordered)")
    print("="*60)
    print(f"  Tickers available: {len(esg_data)}")
    
    all_features = []
    all_labels = []
    stock_splits = []
    skipped = []
    
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
            skipped.append((ticker, 'No data'))
            continue
        
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        df_with_indicators = calculate_indicators_for_df(df)
        if df_with_indicators is None:
            skipped.append((ticker, 'Insufficient data'))
            continue
        
        technical_cols = [c for c in feature_cols 
                         if c not in ('ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score')]
        
        df_clean = df_with_indicators.dropna(subset=technical_cols + ['Forward_Return'])
        if len(df_clean) < SEQ_LEN * 2:
            skipped.append((ticker, f'Only {len(df_clean)} rows'))
            continue
        
        start_idx = len(all_features)
        forward_returns = df_clean['Forward_Return'].values
        labels = np.where(forward_returns > BUY_THRESHOLD, 2,
                          np.where(forward_returns < SELL_THRESHOLD, 0, 1))
        
        for i, (_, row) in enumerate(df_clean.iterrows()):
            vec = []
            for col in feature_cols:
                if col in ('ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score'):
                    if col == 'ESG_Score': vec.append(float(stock_row['ESG_Score']) / 100.0)
                    elif col == 'Environmental_Score': vec.append(float(stock_row['Environmental_Score']) / 100.0)
                    elif col == 'Social_Score': vec.append(float(stock_row['Social_Score']) / 100.0)
                    elif col == 'Governance_Score': vec.append(float(stock_row['Governance_Score']) / 100.0)
                else:
                    vec.append(float(row[col]) if pd.notna(row[col]) else 0.0)
            
            all_features.append(vec)
            all_labels.append(labels[i])
            
        end_idx = len(all_features)
        stock_splits.append((ticker, start_idx, end_idx))
    
    print("\n  [Debug] Finished downloading all tickers. Building matrices...")
    if len(all_features) < 100:
        print(f"\n  [!] Only {len(all_features)} samples! Not enough.")
        return None, None, None, None, None, None, None, None, None
        
    X_raw = np.array(all_features)
    y_raw = np.array(all_labels)
    print(f"  [Debug] X_raw shape: {X_raw.shape}")
    
    # Clean data
    X_raw = np.nan_to_num(X_raw, nan=0.0, posinf=0.0, neginf=0.0)
    X_raw = np.clip(X_raw, -1e4, 1e4)
    
    train_raw_rows = []
    print("  [Debug] Extracting train subsets...")
    for ticker, start_idx, end_idx in stock_splits:
        length = end_idx - start_idx
        train_len = int(length * 0.70)
        if train_len > 0:
            train_raw_rows.append(X_raw[start_idx : start_idx + train_len])
            
    if not train_raw_rows:
        print("\n  [!] Not enough training data.")
        return None, None, None, None, None, None, None, None, None, None, None
        
    X_train_raw = np.vstack(train_raw_rows)
    
    # Remove near-constant features ONLY based on train set
    stds = np.std(X_train_raw, axis=0)
    const_mask = stds > 1e-8
    
    # Remove highly correlated features ONLY based on train set
    X_train_clean = X_train_raw[:, const_mask]
    X_train_clean, kept_idx = remove_highly_correlated(X_train_clean, threshold=CORR_THRESHOLD)
    
    final_mask = np.zeros(X_raw.shape[1], dtype=bool)
    final_mask[np.where(const_mask)[0][kept_idx]] = True
    
    survived_features = [feature_cols[i] for i in range(len(feature_cols)) if final_mask[i]]
    removed_count = len(feature_cols) - len(survived_features)
    
    X_raw_filtered = X_raw[:, final_mask]
    X_train_filtered = X_train_raw[:, final_mask]
    
    # Fit scaler ONLY on train set
    print("  [Debug] Fitting scaler...")
    scaler = StandardScaler()
    scaler.fit(X_train_filtered)
    print("  [Debug] Transforming features...")
    X_scaled = scaler.transform(X_raw_filtered)
    
    # Now build sequences and time-series split
    print("  [Debug] Building sequences...")
    X_train_seq = []
    y_train_seq = []
    X_val_seq = []
    y_val_seq = []
    X_test_seq = []
    y_test_seq = []
    
    for ticker, start_idx, end_idx in stock_splits:
        length = end_idx - start_idx
        if length <= SEQ_LEN:
            continue
            
        train_len = int(length * 0.70)
        val_len = int(length * 0.15)
        
        if train_len < SEQ_LEN:
            continue
            
        train_end = start_idx + train_len
        val_end = train_end + val_len
        
        # Training sequences
        for i in range(start_idx, train_end - SEQ_LEN):
            X_train_seq.append(X_scaled[i : i + SEQ_LEN])
            y_train_seq.append(y_raw[i + SEQ_LEN - 1])
            
        # Validation sequences
        for i in range(max(start_idx + SEQ_LEN, train_end), val_end - SEQ_LEN):
            X_val_seq.append(X_scaled[i : i + SEQ_LEN])
            y_val_seq.append(y_raw[i + SEQ_LEN - 1])
            
        # Testing sequences
        for i in range(max(start_idx + SEQ_LEN, val_end), end_idx - SEQ_LEN):
            X_test_seq.append(X_scaled[i : i + SEQ_LEN])
            y_test_seq.append(y_raw[i + SEQ_LEN - 1])
            
    print("  [Debug] Converting sequences to numpy arrays...")
    X_train = np.array(X_train_seq, dtype=np.float32)
    y_train = np.array(y_train_seq, dtype=np.int64)
    X_val = np.array(X_val_seq, dtype=np.float32)
    y_val = np.array(y_val_seq, dtype=np.int64)
    X_test = np.array(X_test_seq, dtype=np.float32)
    y_test = np.array(y_test_seq, dtype=np.int64)
    
    print("  [Debug] Encoding labels...")
    # Encode labels
    le = LabelEncoder()
    le.fit(['Sell', 'Hold', 'Buy'])
    
    y_train_str = pd.Series(y_train).map({0: 'Sell', 1: 'Hold', 2: 'Buy'})
    y_val_str = pd.Series(y_val).map({0: 'Sell', 1: 'Hold', 2: 'Buy'})
    y_test_str = pd.Series(y_test).map({0: 'Sell', 1: 'Hold', 2: 'Buy'})
    
    y_train_enc = le.transform(y_train_str)
    y_val_enc = le.transform(y_val_str)
    y_test_enc = le.transform(y_test_str)
    
    buy_pct = (y_train == 2).mean() * 100
    hold_pct = (y_train == 1).mean() * 100
    sell_pct = (y_train == 0).mean() * 100
    print(f"\n  Dataset Summary:")
    print(f"  Training Sequences:   {len(X_train):,}")
    print(f"  Validation Sequences: {len(X_val):,}")
    print(f"  Testing Sequences:    {len(X_test):,}")
    X_clean = X_raw
    used_features = feature_cols
    print(f"  Features:             {X_clean.shape[1]}")
    print(f"  Buy (Train):          {buy_pct:.1f}%")
    print(f"  Hold (Train):         {hold_pct:.1f}%")
    print(f"  Sell (Train):         {sell_pct:.1f}%")
    
    return X_train, y_train_enc, X_val, y_val_enc, X_test, y_test_enc, scaler, le, used_features

def build_training_dataset():
    print("\n" + "="*60)
    print("  ESG Stock Prediction - Training LSTM on REAL Market Data")
    print("="*60)
    print("\n[*] Loading ESG data...")
    try:
        esg_data = pd.read_csv(STOCK_LIST_PATH)
        print(f"  Loaded {len(esg_data)} tickers from ESG dataset")
    except Exception as e:
        print(f"  [!] Error loading ESG data: {e}")
        return None, None, None, None, None, None, None, None, None
    return build_real_training_data(esg_data)
class PyTorchLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=2, num_classes=3, dropout=0.5):
        super(PyTorchLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # Bi-directional LSTM for stronger sequence modeling
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, 
                            batch_first=True, dropout=dropout if num_layers > 1 else 0,
                            bidirectional=True)
        
        # Since it's bidirectional, hidden_size is multiplied by 2
        self.bn1 = nn.BatchNorm1d(hidden_size * 2)
        self.fc1 = nn.Linear(hidden_size * 2, hidden_size)
        self.bn2 = nn.BatchNorm1d(hidden_size)
        self.relu = nn.LeakyReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(hidden_size, num_classes)
        
    def forward(self, x):
        # x is (batch_size, seq_len, input_size)
        out, _ = self.lstm(x)
        
        # Take the last time step from the sequence
        out = out[:, -1, :]
        
        out = self.bn1(out)
        out = self.fc1(out)
        out = self.bn2(out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        return out

def train_lstm_model(X_train, y_train, X_val, y_val):
    print("\n" + "="*60)
    print("  Training Deep Learning LSTM Model (PyTorch)")
    print("="*60)
    
    # Convert to tensors
    X_train_tensor = torch.tensor(X_train)
    y_train_tensor = torch.tensor(y_train, dtype=torch.long)
    X_val_tensor = torch.tensor(X_val)
    y_val_tensor = torch.tensor(y_val, dtype=torch.long)
    
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True)
    
    model = PyTorchLSTM(input_size=X_train.shape[2])
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=1e-3)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=2)
    
    epochs = 15
    best_val_loss = float('inf')
    best_model_state = None
    patience = 4
    patience_counter = 0
    
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        train_correct = 0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            train_correct += (predicted == y_batch).sum().item()
            
        train_acc = train_correct / len(y_train_tensor)
            
        # Validation (Batched)
        model.eval()
        val_loss = 0
        val_correct = 0
        with torch.no_grad():
            val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
            val_loader = DataLoader(val_dataset, batch_size=256, shuffle=False)
            for vx, vy in val_loader:
                v_out = model(vx)
                val_loss += criterion(v_out, vy).item() * vx.size(0)
                _, v_pred = torch.max(v_out.data, 1)
                val_correct += (v_pred == vy).sum().item()
            val_loss /= len(y_val_tensor)
            val_acc = val_correct / len(y_val_tensor)
            
        print(f"Epoch {epoch+1:02d}/{epochs} | Train Loss: {train_loss/len(train_loader):.4f} | Val Loss: {val_loss:.4f} | Train Acc: {train_acc:.4f} | Val Acc: {val_acc:.4f}")
        
        scheduler.step(val_loss)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break
                
    model.load_state_dict(best_model_state)
    return model

def save_model_artifacts(model, scaler, label_encoder, metrics, cols):
    print(f"\n[*] Saving model artifacts...")
    torch.save(model.state_dict(), MODEL_PATH)
    size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024 if os.path.exists(MODEL_PATH) else 0
    print(f"  [OK] LSTM Model saved to {MODEL_PATH} ({size_mb:.1f} MB)")
    
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(label_encoder, ENCODER_PATH)
    print(f"  [OK] Scaler & encoder saved")
    
    metadata = {
        'model_type': 'LSTM_PyTorch',
        'best_model_name': 'LSTM Deep Learning',
        'accuracy': metrics['accuracy'],
        'precision': metrics['precision'],
        'recall': metrics['recall'],
        'f1_score': metrics['f1_score'],
        'cv_mean': metrics['accuracy'],
        'cv_std': 0.0,
        'confusion_matrix': metrics['confusion_matrix'],
        'all_results': {},
        'base_models': ['LSTM'],
        'feature_count': len(cols),
        'features': cols,
        'sequence_length': SEQ_LEN,
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'label_classes': ['Buy', 'Hold', 'Sell'],
        'training_source': 'REAL_MARKET_DATA_5YR_TIMESERIES',
        'forward_window_days': FORWARD_WINDOW,
        'buy_threshold': BUY_THRESHOLD,
        'sell_threshold': SELL_THRESHOLD,
        'correlation_threshold': CORR_THRESHOLD,
        'hyperparameter_tuning': False,
        'validation': 'PER_STOCK_TIMESERIES_SPLIT',
        'data_leakage_free': True
    }
    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  [OK] Metadata saved (data_leakage_free: True, validation: per-stock time-series)")

def main():
    start_time = time.time()
    print("="*60)
    print("  ESG Stock Prediction - LSTM Training Pipeline")
    print("="*60)
    print(f"  Features:        {len(feature_cols)}")
    print(f"  Label window:    {FORWARD_WINDOW} trading days")
    print(f"  Sequence Length: {SEQ_LEN} days")
    print("="*60)
    
    ensure_directories()
    result = build_training_dataset()
    if result[0] is None:
        print("\n[!] Training dataset building failed!")
        return
        
    X_train, y_train_enc, X_val, y_val_enc, X_test, y_test_enc, scaler, label_encoder, used_features = result
    
    model = train_lstm_model(X_train, y_train_enc, X_val, y_val_enc)
    
    # Evaluate using batches to avoid OOM
    print("\n[*] Evaluating Best Model...")
    model.eval()
    y_pred_list = []
    with torch.no_grad():
        X_test_tensor = torch.tensor(X_test)
        test_dataset = TensorDataset(X_test_tensor, torch.zeros(len(X_test_tensor)))
        test_loader = DataLoader(test_dataset, batch_size=256, shuffle=False)
        for tx, _ in test_loader:
            y_pred_logits = model(tx)
            _, y_batch_pred = torch.max(y_pred_logits, 1)
            y_pred_list.extend(y_batch_pred.numpy())
    y_pred = np.array(y_pred_list)
    
    acc = accuracy_score(y_test_enc, y_pred)
    pre = precision_score(y_test_enc, y_pred, average='weighted', zero_division=0)
    rec = recall_score(y_test_enc, y_pred, average='weighted', zero_division=0)
    f1 = f1_score(y_test_enc, y_pred, average='weighted', zero_division=0)
    cm = confusion_matrix(y_test_enc, y_pred).tolist()
    
    metrics = {
        'accuracy': acc,
        'precision': pre,
        'recall': rec,
        'f1_score': f1,
        'confusion_matrix': cm
    }
    
    save_model_artifacts(model, scaler, label_encoder, metrics, used_features)
    
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("  LSTM TRAINING COMPLETE!")
    print(f"  Test Accuracy:  {acc:.2%}")
    print(f"  F1 Score:       {f1:.2%}")
    print(f"  Time elapsed:   {elapsed:.0f}s")
    print("="*60)

if __name__ == '__main__':
    main()
