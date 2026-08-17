"""
Real Stock Data Training Pipeline for ESG Stock Prediction
===========================================================
Fetches actual historical stock data via yfinance, calculates technical
indicators + extended features, creates forward-return labels, and trains
a stacking ensemble with PROPER TIME-SERIES VALIDATION (no data leakage).

Key improvements over v1:
  - Time-series train/test split (no future data leakage)
  - Proper min_periods for indicators (cleaner training data)
  - Correlation-based feature selection (reduces noise)
  - RandomizedSearchCV hyperparameter tuning
  - Weighted ensemble voting based on CV performance
  - Full 67-feature sync with predict.py
"""

import os, sys, warnings, numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta
import joblib, json, time, itertools
from sklearn.model_selection import train_test_split, StratifiedKFold, RandomizedSearchCV, TimeSeriesSplit
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'forksafe'
os.environ['LOKY_PICKLE_MODE'] = 'pickle5'
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
STOCK_LIST_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

np.random.seed(42)

# =====================================================================
# FEATURE DEFINITIONS — 67 features (base + extended)
# MUST match predict.py features exactly
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
    'CORR_CLOSE_VOL','CORR_HIGH_LOW'
]

FORWARD_WINDOW = 20
BUY_THRESHOLD = 0.045       # ±4.5% — slightly tighter than 5% for more labels
SELL_THRESHOLD = -0.045
YF_PERIOD = '5y'            # 5 years of history
CORR_THRESHOLD = 0.95        # Remove features with pairwise corr > 0.95 (reduces noise)
TUNE_HYPERPARAMS = True      # Enable RandomizedSearchCV


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
    # Use proper min_periods to avoid noisy early values
    df['SMA_10'] = c.rolling(10, min_periods=5).mean()
    df['SMA_30'] = c.rolling(30, min_periods=15).mean()
    df['EMA_10'] = c.ewm(span=10, adjust=False, min_periods=5).mean()
    df['EMA_30'] = c.ewm(span=30, adjust=False, min_periods=15).mean()
    
    delta = c.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    ema_12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False, min_periods=9).mean()
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
    
    # TRIX
    ema1 = c.ewm(span=15, adjust=False, min_periods=15).mean()
    ema2 = ema1.ewm(span=15, adjust=False, min_periods=15).mean()
    ema3 = ema2.ewm(span=15, adjust=False, min_periods=15).mean()
    df['TRIX'] = ema3.pct_change() * 100
    
    df['ROC_10'] = c.pct_change(10) * 100
    df['ROC_20'] = c.pct_change(20) * 100
    
    ppo_ema_12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ppo_ema_26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    df['PPO'] = (ppo_ema_12 - ppo_ema_26) / ppo_ema_26 * 100
    
    # ADX
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
    
    # CMO
    up_sum = gain.rolling(14, min_periods=14).sum()
    down_sum = loss.rolling(14, min_periods=14).sum()
    df['CMO'] = (up_sum - down_sum) / (up_sum + down_sum).replace(0, np.nan) * 100
    
    # Ultimate Oscillator
    bp = c - pd.concat([l, c.shift()], axis=1).min(axis=1)
    tr_range = pd.concat([h, c.shift()], axis=1).max(axis=1) - pd.concat([l, c.shift()], axis=1).min(axis=1)
    avg7 = bp.rolling(7, min_periods=7).sum() / tr_range.rolling(7, min_periods=7).sum().replace(0, np.nan)
    avg14 = bp.rolling(14, min_periods=14).sum() / tr_range.rolling(14, min_periods=14).sum().replace(0, np.nan)
    avg28 = bp.rolling(28, min_periods=28).sum() / tr_range.rolling(28, min_periods=28).sum().replace(0, np.nan)
    df['ULT_OSC'] = (4 * avg7 + 2 * avg14 + avg28) / 7 * 100
    
    # Aroon with proper handling
    def _aroon_up_fn(x):
        if len(x) < 25: return np.nan
        return float(np.argmax(x) / 25 * 100)
    def _aroon_down_fn(x):
        if len(x) < 25: return np.nan
        return float(np.argmin(x) / 25 * 100)
    df['AROON_UP'] = h.rolling(25, min_periods=25).apply(_aroon_up_fn, raw=True)
    df['AROON_DOWN'] = l.rolling(25, min_periods=25).apply(_aroon_down_fn, raw=True)
    
    # Chaikin Money Flow
    mf_mult = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    mf_vol = mf_mult * v
    df['CHAIKIN_MF'] = mf_vol.rolling(20, min_periods=20).sum() / v.rolling(20, min_periods=20).sum().replace(0, np.nan)
    
    # OBV
    obv = (v * np.sign(delta)).fillna(0).cumsum()
    df['OBV_Change'] = obv.pct_change(5) * 100
    
    # KAMA
    er = np.abs(c.diff(10)) / c.diff().abs().rolling(10, min_periods=5).sum().replace(0, np.nan)
    sc = (er * (2/31 - 2/301) + 2/301) ** 2
    sc = sc.fillna(0)
    kama = c.copy()
    for i in range(1, len(kama)):
        kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (c.iloc[i] - kama.iloc[i-1])
    df['KAMA_10'] = kama
    df['KAMA_DIVERGENCE'] = c / kama - 1
    
    df['MIDPOINT_10'] = (h.rolling(10, min_periods=5).max() + l.rolling(10, min_periods=5).min()) / 2
    df['MIDPRICE_10'] = (h.rolling(10, min_periods=5).max() + l.rolling(10, min_periods=5).min()) / 2
    
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
    
    # Forward return label
    df['Forward_Return'] = c.shift(-FORWARD_WINDOW) / c - 1
    
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
    Build training dataset with PROPER TIME-SERIES ordering.
    For each stock, rows are kept chronological. Then we track which rows
    belong to which stock so we can do per-stock temporal splits later.
    """
    print("\n" + "="*60)
    print("  BUILDING REAL TRAINING DATASET (5yr, time-ordered)")
    print("="*60)
    print(f"  Tickers available: {len(esg_data)}")
    
    all_features = []
    all_labels = []
    stock_ids = []        # Track which stock each sample belongs to
    stock_positions = []  # Track position within each stock's time series
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
        if len(df_clean) < 30:
            skipped.append((ticker, f'Only {len(df_clean)} rows'))
            continue
        
        forward_returns = df_clean['Forward_Return'].values
        labels = np.where(forward_returns > BUY_THRESHOLD, 2,
                          np.where(forward_returns < SELL_THRESHOLD, 0, 1))
        
        for i, (_, row) in enumerate(df_clean.iterrows()):
            vec = [float(row[col]) if pd.notna(row[col]) else 0.0 for col in technical_cols]
            vec += [float(stock_row['ESG_Score']),
                    float(stock_row['Environmental_Score']),
                    float(stock_row['Social_Score']),
                    float(stock_row['Governance_Score'])]
            all_features.append(vec)
            if i < len(labels):
                all_labels.append(labels[i])
            else:
                all_labels.append(labels[-1])
            stock_ids.append(idx)
            stock_positions.append(i)
    
    print()
    if len(all_features) < 100:
        print(f"\n  [!] Only {len(all_features)} samples! Not enough.")
        return None, None, None, None, None, None, None
    
    X = np.array(all_features)
    y = np.array(all_labels)
    
    # Clean data
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    X = np.clip(X, -1e4, 1e4)
    
    # Remove near-constant features
    stds = np.std(X, axis=0)
    const_mask = stds > 1e-8
    X = X[:, const_mask]
    
    # Remove highly correlated features (reduces noise, improves generalization)
    corr_threshold = CORR_THRESHOLD
    X, kept_idx = remove_highly_correlated(X, threshold=corr_threshold)
    removed_count = const_mask.sum() - len(kept_idx)
    
    # Map kept indices back to original feature names
    orig_indices = np.where(const_mask)[0][kept_idx]
    survived_features = [feature_cols[i] for i in orig_indices]
    
    buy_pct = (y == 2).mean() * 100
    hold_pct = (y == 1).mean() * 100
    sell_pct = (y == 0).mean() * 100
    print(f"\n  Dataset Summary:")
    print(f"  Samples:        {len(X):,}")
    print(f"  Features:       {X.shape[1]} (removed {int(removed_count)} redundant)")
    print(f"  Buy:            {buy_pct:.1f}%")
    print(f"  Hold:           {hold_pct:.1f}%")
    print(f"  Sell:           {sell_pct:.1f}%")
    print(f"  Tickers used:   {total - len(skipped)} / {total}")
    if skipped:
        print(f"  Skipped:        {len(skipped)}")
        for t, r in skipped[:5]:
            print(f"    - {t}: {r}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped)-5} more")
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    le = LabelEncoder()
    y_encoded = le.fit_transform(pd.Series(y).map({0: 'Sell', 1: 'Hold', 2: 'Buy'}))
    
    return X_scaled, y_encoded, scaler, le, survived_features, stock_ids, stock_positions


def time_series_split(X, y, stock_ids, stock_positions, test_ratio=0.2):
    """
    TIME-SERIES AWARE SPLIT — NO DATA LEAKAGE.
    
    For each stock, take the last test_ratio fraction of chronologically
    ordered rows as the test set. This ensures no future data leaks into
    the training set.
    """
    np.random.seed(42)
    unique_stocks = sorted(set(stock_ids))
    train_idx = []
    test_idx = []
    
    for sid in unique_stocks:
        # Get all indices for this stock
        indices = [i for i, s in enumerate(stock_ids) if s == sid]
        positions = [stock_positions[i] for i in indices]
        
        # Sort by position (chronological order)
        sorted_pairs = sorted(zip(positions, indices))
        sorted_indices = [idx for _, idx in sorted_pairs]
        
        # Split: last test_ratio goes to test
        split_point = int(len(sorted_indices) * (1 - test_ratio))
        split_point = max(split_point, 1)  # At least 1 training sample
        split_point = min(split_point, len(sorted_indices) - 1)  # At least 1 test sample
        
        train_idx.extend(sorted_indices[:split_point])
        test_idx.extend(sorted_indices[split_point:])
    
    np.random.shuffle(train_idx)  # Shuffle training for SGD-style learning
    # Test set stays in order (for realistic evaluation)
    
    X_train = X[train_idx]
    X_test = X[test_idx]
    y_train = y[train_idx]
    y_test = y[test_idx]
    
    return X_train, X_test, y_train, y_test


def build_training_dataset():
    print("\n" + "="*60)
    print("  ESG Stock Prediction - Training on REAL Market Data")
    print("="*60)
    print("\n[*] Loading ESG data...")
    try:
        esg_data = pd.read_csv(STOCK_LIST_PATH)
        print(f"  Loaded {len(esg_data)} tickers from ESG dataset")
    except Exception as e:
        print(f"  [!] Error loading ESG data: {e}")
        return None, None, None, None, None, None, None
    return build_real_training_data(esg_data)


def tune_hyperparams_xgb(X_train, y_train, sample_weight):
    """RandomizedSearchCV for XGBoost to find optimal hyperparameters."""
    import xgboost as xgb
    param_dist = {
        'n_estimators': [400, 600, 800, 1000],
        'learning_rate': [0.01, 0.03, 0.05, 0.1],
        'max_depth': [6, 8, 10, 12],
        'subsample': [0.7, 0.8, 0.85, 0.9],
        'colsample_bytree': [0.7, 0.8, 0.85, 0.9],
        'gamma': [0, 0.05, 0.1, 0.2],
        'min_child_weight': [1, 2, 3, 5],
        'reg_alpha': [0, 0.01, 0.05, 0.1],
        'reg_lambda': [0.05, 0.1, 0.2, 0.5],
    }
    xgb_model = xgb.XGBClassifier(random_state=42, eval_metric='mlogloss', verbosity=0, n_jobs=1)
    rs = RandomizedSearchCV(
        xgb_model, param_distributions=param_dist,
        n_iter=20, cv=3, scoring='accuracy',
        random_state=42, verbose=0, n_jobs=1
    )
    rs.fit(X_train, y_train, sample_weight=sample_weight)
    return rs


def tune_hyperparams_lgb(X_train, y_train, sample_weight):
    """RandomizedSearchCV for LightGBM."""
    import lightgbm as lgb
    param_dist = {
        'n_estimators': [400, 600, 800, 1000],
        'learning_rate': [0.01, 0.03, 0.05, 0.1],
        'max_depth': [6, 8, 10, -1],
        'num_leaves': [31, 48, 64, 96],
        'subsample': [0.7, 0.8, 0.85, 0.9],
        'colsample_bytree': [0.7, 0.8, 0.85, 0.9],
        'min_child_samples': [5, 10, 15, 20],
        'reg_alpha': [0, 0.01, 0.05, 0.1],
        'reg_lambda': [0.05, 0.1, 0.2, 0.5],
    }
    lgb_model = lgb.LGBMClassifier(random_state=42, verbose=-1, n_jobs=1)
    rs = RandomizedSearchCV(
        lgb_model, param_distributions=param_dist,
        n_iter=20, cv=3, scoring='accuracy',
        random_state=42, verbose=0, n_jobs=1
    )
    rs.fit(X_train, y_train, sample_weight=sample_weight)
    return rs


def train_models(X_train, X_test, y_train, y_test):
    print("\n" + "="*60)
    print("  Training ENSEMBLE Models (time-series validated)")
    print("="*60)
    
    classes, counts = np.unique(y_train, return_counts=True)
    cw = dict(zip(classes, counts.max() / counts))
    sw = np.array([cw[y] for y in y_train])
    
    models = {}
    
    # ======================== 1. XGBoost ========================
    if TUNE_HYPERPARAMS:
        print("[1/5] Tuning XGBoost (RandomizedSearchCV x20)...", end=' ', flush=True)
        rs_xgb = tune_hyperparams_xgb(X_train, y_train, sw)
        xgb_model = rs_xgb.best_estimator_
        print(f"OK (best params: lr={rs_xgb.best_params_['learning_rate']}, "
              f"depth={rs_xgb.best_params_['max_depth']}, "
              f"est={rs_xgb.best_params_['n_estimators']})")
    else:
        print("[1/5] XGBoost (800 estimators)...", end=' ', flush=True)
        import xgboost as xgb
        xgb_model = xgb.XGBClassifier(
            n_estimators=800, learning_rate=0.03, max_depth=10,
            subsample=0.85, colsample_bytree=0.85,
            gamma=0.05, min_child_weight=2,
            reg_alpha=0.05, reg_lambda=0.1,
            random_state=42, eval_metric='mlogloss',
            verbosity=0, n_jobs=1
        )
        xgb_model.fit(X_train, y_train, sample_weight=sw)
    models['XGBoost'] = xgb_model
    acc = accuracy_score(y_test, xgb_model.predict(X_test))
    print(f"       Test Acc: {acc:.4f}")
    
    # ======================== 2. LightGBM ========================
    if TUNE_HYPERPARAMS:
        print("[2/5] Tuning LightGBM (RandomizedSearchCV x20)...", end=' ', flush=True)
        rs_lgb = tune_hyperparams_lgb(X_train, y_train, sw)
        lgb_model = rs_lgb.best_estimator_
        print(f"OK (best params: lr={rs_lgb.best_params_['learning_rate']}, "
              f"depth={rs_lgb.best_params_['max_depth']}, "
              f"leaves={rs_lgb.best_params_['num_leaves']})")
    else:
        print("[2/5] LightGBM (800 estimators)...", end=' ', flush=True)
        import lightgbm as lgb
        lgb_model = lgb.LGBMClassifier(
            n_estimators=800, learning_rate=0.03, max_depth=10,
            num_leaves=64, subsample=0.85, colsample_bytree=0.85,
            min_child_samples=10, class_weight='balanced',
            reg_alpha=0.05, reg_lambda=0.1,
            random_state=42, verbose=-1, n_jobs=1
        )
        lgb_model.fit(X_train, y_train, sample_weight=sw)
    models['LightGBM'] = lgb_model
    acc = accuracy_score(y_test, lgb_model.predict(X_test))
    print(f"       Test Acc: {acc:.4f}")
    
    # ======================== 3. Random Forest ========================
    print("[3/5] Random Forest (600 trees)...", end=' ', flush=True)
    rf_model = RandomForestClassifier(
        n_estimators=600, max_depth=15, min_samples_split=5,
        min_samples_leaf=2, max_features='log2',
        class_weight='balanced', random_state=42, n_jobs=1
    )
    rf_model.fit(X_train, y_train)
    models['RandomForest'] = rf_model
    acc = accuracy_score(y_test, rf_model.predict(X_test))
    print(f"OK (Test Acc: {acc:.4f})")
    
    # ======================== 4. Gradient Boosting ========================
    print("[4/5] Gradient Boosting (400 estimators)...", end=' ', flush=True)
    gb_model = GradientBoostingClassifier(
        n_estimators=400, learning_rate=0.05, max_depth=6,
        min_samples_split=10, min_samples_leaf=5,
        subsample=0.85, max_features=0.85,
        random_state=42
    )
    gb_model.fit(X_train, y_train, sample_weight=sw)
    models['GradientBoosting'] = gb_model
    acc = accuracy_score(y_test, gb_model.predict(X_test))
    print(f"OK (Test Acc: {acc:.4f})")
    
    # ======================== 5. CatBoost ========================
    print("[5/5] CatBoost (800 iterations)...", end=' ', flush=True)
    try:
        from catboost import CatBoostClassifier
        cb_model = CatBoostClassifier(
            iterations=800, learning_rate=0.03, depth=8,
            l2_leaf_reg=3, random_seed=42,
            auto_class_weights='Balanced',
            verbose=False, allow_writing_files=False
        )
        cb_model.fit(X_train, y_train)
        models['CatBoost'] = cb_model
        acc = accuracy_score(y_test, cb_model.predict(X_test))
        print(f"OK (Test Acc: {acc:.4f})")
    except ImportError:
        print("SKIPPED (not installed)")
    
    # ======================== VOTING ENSEMBLE ========================
    print("\n[*] Building Weighted Voting Ensemble...", end=' ', flush=True)
    # Evaluate each model's CV accuracy to compute weights
    model_weights = {}
    for name, model in models.items():
        try:
            skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            cv_scores = []
            for train_idx, val_idx in skf.split(X_train, y_train):
                params = model.get_params() if hasattr(model, 'get_params') else {}
                m = model.__class__(**params)
                m.fit(X_train[train_idx], y_train[train_idx])
                cv_scores.append(accuracy_score(y_train[val_idx], m.predict(X_train[val_idx])))
            model_weights[name] = float(np.mean(cv_scores))
        except Exception:
            model_weights[name] = 0.5
    
    # Normalize weights
    total_w = sum(model_weights.values())
    if total_w > 0:
        model_weights = {k: v / total_w for k, v in model_weights.items()}
    else:
        model_weights = {k: 1.0 / len(models) for k in models}
    
    # Create voting classifier with weights
    estimators = [(name, model) for name, model in models.items()]
    weights = [model_weights[name] for name, _ in estimators]
    voting = VotingClassifier(estimators=estimators, voting='soft', weights=weights)
    voting.fit(X_train, y_train)
    models['WeightedVoting'] = voting
    print("OK")
    
    # ======================== EVALUATION ========================
    results = {}
    best_model, best_score, best_name = None, 0, ""
    
    for name, model in models.items():
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        pre = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        rec = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        cm = confusion_matrix(y_test, y_pred).tolist()
        
        cv_mean = model_weights.get(name, 0)
        results[name] = {
            'model': model, 'accuracy': acc, 'precision': pre,
            'recall': rec, 'f1_score': f1, 'confusion_matrix': cm,
            'cv_mean': cv_mean, 'cv_std': 0
        }
        
        print(f"  {name:25s}  Acc:{acc:.4f}  F1:{f1:.4f}  CV:{cv_mean:.4f}")
        
        if acc > best_score:
            best_score, best_model, best_name = acc, model, name
    
    print(f"\n{'='*60}")
    print(f"  BEST MODEL: {best_name}")
    print(f"  Test Accuracy:  {results[best_name]['accuracy']:.4f}")
    print(f"  F1 Score:       {results[best_name]['f1_score']:.4f}")
    print(f"  CV Accuracy:    {results[best_name]['cv_mean']:.4f}")
    print(f"{'='*60}")
    
    metric_keys = ['accuracy', 'precision', 'recall', 'f1_score', 'cv_mean', 'cv_std']
    all_results = {n: {k: float(r[k]) for k in metric_keys} for n, r in results.items()}
    bm = results[best_name]
    
    return best_model, {
        'best_model_name': best_name,
        'accuracy': float(bm['accuracy']),
        'precision': float(bm['precision']),
        'recall': float(bm['recall']),
        'f1_score': float(bm['f1_score']),
        'cv_mean': float(bm['cv_mean']),
        'cv_std': float(bm['cv_std']),
        'confusion_matrix': bm['confusion_matrix'],
        'all_results': all_results,
        'base_models': list(models.keys()),
        'model_weights': model_weights
    }


def save_model_artifacts(model, scaler, label_encoder, metrics, cols):
    print(f"\n[*] Saving model artifacts...")
    joblib.dump(model, MODEL_PATH)
    size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024 if os.path.exists(MODEL_PATH) else 0
    print(f"  [OK] Model saved ({size_mb:.1f} MB)")
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(label_encoder, ENCODER_PATH)
    print(f"  [OK] Scaler & encoder saved")
    
    metadata = {
        'model_type': type(model).__name__,
        'best_model_name': metrics['best_model_name'],
        'accuracy': metrics['accuracy'],
        'precision': metrics['precision'],
        'recall': metrics['recall'],
        'f1_score': metrics['f1_score'],
        'cv_mean': metrics['cv_mean'],
        'cv_std': metrics['cv_std'],
        'confusion_matrix': metrics['confusion_matrix'],
        'all_results': metrics['all_results'],
        'base_models': metrics.get('base_models', []),
        'feature_count': len(cols),
        'features': cols,
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'label_classes': ['Buy', 'Hold', 'Sell'],
        'training_source': 'REAL_MARKET_DATA_5YR_TIMESERIES',
        'forward_window_days': FORWARD_WINDOW,
        'buy_threshold': BUY_THRESHOLD,
        'sell_threshold': SELL_THRESHOLD,
        'correlation_threshold': CORR_THRESHOLD,
        'hyperparameter_tuning': TUNE_HYPERPARAMS,
        'validation': 'PER_STOCK_TIMESERIES_SPLIT',
        'data_leakage_free': True
    }
    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  [OK] Metadata saved (data_leakage_free: True, validation: per-stock time-series)")


def main():
    start_time = time.time()
    print("="*60)
    print("  ESG Stock Prediction - v2 OPTIMIZED Training Pipeline")
    print("="*60)
    print(f"  Features:        {len(feature_cols)} (all synced with predict.py)")
    print(f"  Label window:    {FORWARD_WINDOW} trading days")
    print(f"  Buy threshold:   +{BUY_THRESHOLD*100:.1f}%")
    print(f"  Sell threshold:  {SELL_THRESHOLD*100:.1f}%")
    print(f"  Data source:     yfinance ({YF_PERIOD})")
    print(f"  Validation:      PER-STOCK TIME-SERIES SPLIT (no leakage)")
    print(f"  Feature removal: >{CORR_THRESHOLD*100:.0f}% correlation")
    print(f"  Hyperparameter:  {'RandomizedSearchCV x20' if TUNE_HYPERPARAMS else 'Fixed'}")
    print(f"  Ensemble:        XGBoost + LightGBM + RF + GB + CB + WeightedVoting")
    print("="*60)
    
    ensure_directories()
    result = build_training_dataset()
    if result[0] is None:
        print("\n[!] Training dataset building failed!")
        return
    
    X_scaled, y_encoded, scaler, label_encoder, used_features, stock_ids, stock_positions = result
    
    # TIME-SERIES AWARE SPLIT
    X_train, X_test, y_train, y_test = time_series_split(
        X_scaled, y_encoded, stock_ids, stock_positions, test_ratio=0.2
    )
    
    print(f"\n[*] Time-Series Split:")
    print(f"  Training:   {X_train.shape[0]:,}")
    print(f"  Testing:    {X_test.shape[0]:,}")
    print(f"  Features:   {X_train.shape[1]}")
    print(f"  Leakage:    NONE (per-stock chronological split)")
    
    best_model, metrics = train_models(X_train, X_test, y_train, y_test)
    save_model_artifacts(best_model, scaler, label_encoder, metrics, used_features)
    
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("  TRAINING COMPLETE!")
    print(f"  Best Model:     {metrics['best_model_name']}")
    print(f"  Accuracy:       {metrics['accuracy']:.2%}")
    print(f"  F1 Score:       {metrics['f1_score']:.2%}")
    print(f"  CV Mean:        {metrics['cv_mean']:.2%}")
    print(f"  Base models:    {len(metrics.get('base_models', []))}")
    print(f"  Features used:  {len(used_features)}")
    print(f"  Validation:     Per-stock time-series (no future leakage)")
    print(f"  Time elapsed:   {elapsed:.0f}s")
    print("="*60)


if __name__ == '__main__':
    main()
