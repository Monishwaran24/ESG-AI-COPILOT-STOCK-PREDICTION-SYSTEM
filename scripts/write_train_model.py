import os

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
target_path = os.path.join(project_root, 'model', 'train_model.py')

content = r'''"""
Real Stock Data Training Pipeline for ESG Stock Prediction
===========================================================
Fetches actual historical stock data via yfinance (no rate limits for bulk training),
calculates technical indicators, creates forward-return labels, and trains
XGBoost + LightGBM ensemble models on REAL market data.
"""

import os, sys, warnings, numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta
import joblib, json, time
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'forksafe'
os.environ['LOKY_PICKLE_MODE'] = 'pickle5'
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
STOCK_LIST_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

np.random.seed(42)

feature_cols = [
    'SMA_10','SMA_30','EMA_10','EMA_30','RSI_14',
    'MACD','MACD_Signal','MACD_Histogram',
    'BB_Width','BB_Position',
    'Price_Change_1d','Price_Change_5d','Price_Change_20d',
    'Volume_Ratio','High_Low_Ratio','Close_Open_Ratio','Volatility_10d',
    'Price_Acceleration','VPT_Change','RSI_SMA','Price_Position',
    'ATR_14','STOCH_K','STOCH_D','WILLIAMS_R','MFI',
    'Log_Return_1d','Log_Return_5d','Log_Return_20d',
    'Price_Momentum','Volume_Change_1d','High_Low_Pct',
    'ESG_Score','Environmental_Score','Social_Score','Governance_Score'
]

FORWARD_WINDOW = 20
BUY_THRESHOLD = 0.03
SELL_THRESHOLD = -0.03

def ensure_directories():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

def get_yfinance_ticker(ticker):
    t = ticker.upper()
    if t == 'BRK.B':
        return 'BRK-B'
    return t

def calculate_indicators_for_df(df):
    df = df.copy()
    if len(df) < 50:
        return None
    df['SMA_10'] = df['Close'].rolling(window=10, min_periods=1).mean()
    df['SMA_30'] = df['Close'].rolling(window=30, min_periods=1).mean()
    df['EMA_10'] = df['Close'].ewm(span=10, adjust=False, min_periods=1).mean()
    df['EMA_30'] = df['Close'].ewm(span=30, adjust=False, min_periods=1).mean()
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(window=14, min_periods=1).mean()
    avg_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    ema_12 = df['Close'].ewm(span=12, adjust=False, min_periods=1).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False, min_periods=1).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False, min_periods=1).mean()
    df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
    df['BB_Middle'] = df['Close'].rolling(window=20, min_periods=1).mean()
    bb_std = df['Close'].rolling(window=20, min_periods=1).std()
    df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
    df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
    df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'] + 1e-10)
    df['Price_Change_1d'] = df['Close'].pct_change()
    df['Price_Change_5d'] = df['Close'].pct_change(periods=5)
    df['Price_Change_20d'] = df['Close'].pct_change(periods=20)
    df['Volume_Ratio'] = df['Volume'] / df['Volume'].rolling(window=20, min_periods=1).mean()
    df['Volume_Change_1d'] = df['Volume'].pct_change()
    df['High_Low_Ratio'] = (df['High'] - df['Low']) / df['Close']
    df['High_Low_Pct'] = (df['High'] - df['Low']) / df['Low']
    df['Close_Open_Ratio'] = (df['Close'] - df['Open']) / df['Open']
    df['Volatility_10d'] = df['Price_Change_1d'].rolling(window=10, min_periods=1).std()
    df['Price_Acceleration'] = df['Price_Change_5d'] - df['Price_Change_20d'].shift(5)
    df['Volume_Price_Trend'] = df['Close'] * df['Volume']
    df['VPT_Change'] = df['Volume_Price_Trend'].pct_change(periods=5)
    df['RSI_SMA'] = df['RSI_14'] - df['RSI_14'].rolling(window=10, min_periods=1).mean()
    df['Price_Position'] = (df['Close'] - df['Low'].rolling(window=20, min_periods=1).min()) / (df['High'].rolling(window=20, min_periods=1).max() - df['Low'].rolling(window=20, min_periods=1).min() + 1e-10)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14, min_periods=1).mean() / df['Close']
    low_14 = df['Low'].rolling(window=14, min_periods=1).min()
    high_14 = df['High'].rolling(window=14, min_periods=1).max()
    df['STOCH_K'] = 100 * (df['Close'] - low_14) / (high_14 - low_14 + 1e-10)
    df['STOCH_D'] = df['STOCH_K'].rolling(window=3, min_periods=1).mean()
    df['WILLIAMS_R'] = -100 * (high_14 - df['Close']) / (high_14 - low_14 + 1e-10)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    mf = tp * df['Volume']
    pos_mf = mf.where(tp > tp.shift(), 0).rolling(window=14, min_periods=1).sum()
    neg_mf = mf.where(tp < tp.shift(), 0).rolling(window=14, min_periods=1).sum()
    mfr = pos_mf / neg_mf.replace(0, np.nan)
    df['MFI'] = 100 - (100 / (1 + mfr))
    df['Log_Return_1d'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Log_Return_5d'] = np.log(df['Close'] / df['Close'].shift(5))
    df['Log_Return_20d'] = np.log(df['Close'] / df['Close'].shift(20))
    df['SMA_50'] = df['Close'].rolling(window=50, min_periods=1).mean()
    df['Price_Momentum'] = df['Close'] / df['SMA_50'] - 1
    df['Forward_Return'] = df['Close'].shift(-FORWARD_WINDOW) / df['Close'] - 1
    return df

def fetch_yfinance_data(ticker, period='2y'):
    try:
        from model.kite_api import is_indian_ticker, get_nse_symbol
        if is_indian_ticker(ticker):
            nse_symbol = get_nse_symbol(ticker)
            yf_ticker = f"{nse_symbol}.NS"
            stock = yf.Ticker(yf_ticker)
            data = stock.history(period=period)
            if data is None or data.empty:
                yf_ticker = f"{nse_symbol}.BO"
                stock = yf.Ticker(yf_ticker)
                data = stock.history(period=period)
            return data
        else:
            yf_t = get_yfinance_ticker(ticker)
            stock = yf.Ticker(yf_t)
            data = stock.history(period=period)
            return data
    except Exception:
        return None

def build_real_training_data(esg_data, max_stocks=None):
    print("\n" + "="*60)
    print("  BUILDING REAL TRAINING DATASET")
    print("="*60)
    print(f"  Tickers available: {len(esg_data)}")
    all_features = []
    all_labels = []
    skipped_tickers = []
    ticker_list = esg_data.to_dict('records')
    if max_stocks:
        ticker_list = sorted(ticker_list, key=lambda x: abs(x['ESG_Score'] - 50), reverse=True)[:max_stocks]
    total = len(ticker_list)
    for idx, stock in enumerate(ticker_list):
        ticker = stock['Ticker']
        pct = (idx + 1) / total * 100
        print(f"\r  [{idx+1}/{total}] {pct:.0f}% Fetching {ticker}...", end='', flush=True)
        df = fetch_yfinance_data(ticker, period='2y')
        if df is None or df.empty:
            skipped_tickers.append((ticker, 'No data'))
            continue
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df_with_indicators = calculate_indicators_for_df(df)
        if df_with_indicators is None:
            skipped_tickers.append((ticker, 'Insufficient data'))
            continue
        indicator_cols = [c for c in feature_cols if c not in ('ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score')]
        df_clean = df_with_indicators.dropna(subset=indicator_cols + ['Forward_Return'])
        if len(df_clean) < 10:
            skipped_tickers.append((ticker, f'Only {len(df_clean)} clean rows'))
            continue
        forward_returns = df_clean['Forward_Return'].values
        labels = np.where(forward_returns > BUY_THRESHOLD, 2, np.where(forward_returns < SELL_THRESHOLD, 0, 1))
        for i, (_, row) in enumerate(df_clean.iterrows()):
            vec = []
            for col in indicator_cols:
                vec.append(float(row[col]) if pd.notna(row[col]) else 0.0)
            vec.append(float(stock['ESG_Score']))
            vec.append(float(stock['Environmental_Score']))
            vec.append(float(stock['Social_Score']))
            vec.append(float(stock['Governance_Score']))
            all_features.append(vec)
            all_labels.append(labels[i])
    print()
    if len(all_features) < 100:
        print(f"\n  [!] Only {len(all_features)} samples collected. Not enough for training!")
        return None, None, None, None, None
    X = np.array(all_features)
    y = np.array(all_labels)
    buy_pct = (y == 2).mean() * 100
    hold_pct = (y == 1).mean() * 100
    sell_pct = (y == 0).mean() * 100
    print(f"\n  Dataset Summary:")
    print(f"  Samples:        {len(X)}")
    print(f"  Features:       {len(feature_cols)}")
    print(f"  Buy:            {buy_pct:.1f}%")
    print(f"  Hold:           {hold_pct:.1f}%")
    print(f"  Sell:           {sell_pct:.1f}%")
    print(f"  Tickers used:   {total - len(skipped_tickers)} / {total}")
    if skipped_tickers:
        print(f"  Skipped:        {len(skipped_tickers)}")
        for t, reason in skipped_tickers[:5]:
            print(f"    - {t}: {reason}")
        if len(skipped_tickers) > 5:
            print(f"    ... and {len(skipped_tickers) - 5} more")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(pd.Series(y).map({0: 'Sell', 1: 'Hold', 2: 'Buy'}))
    return X_scaled, y_encoded, scaler, label_encoder, feature_cols

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
        return None, None, None, None, None
    X_scaled, y_encoded, scaler, label_encoder, used_features = build_real_training_data(esg_data)
    if X_scaled is None:
        print("\n  [!] Real data collection failed! Cannot train.")
        return None, None, None, None, None
    return X_scaled, y_encoded, scaler, label_encoder, used_features

def train_models(X_train, X_test, y_train, y_test):
    print("\n" + "="*60)
    print("  Training Machine Learning Models")
    print("="*60)
    X_sub, y_sub = X_train, y_train
    classes, counts = np.unique(y_sub, return_counts=True)
    class_weights = dict(zip(classes, counts.max() / counts))
    sample_weights = np.array([class_weights[y] for y in y_sub])
    models_config = []
    print("[*] XGBoost (600 estimators, tuned for real data)...", end=' ', flush=True)
    import xgboost as xgb
    xgb_model = xgb.XGBClassifier(n_estimators=600, learning_rate=0.05, max_depth=8, subsample=0.85, colsample_bytree=0.85, gamma=0.1, min_child_weight=3, reg_alpha=0.1, reg_lambda=0.1, random_state=42, eval_metric='mlogloss', verbosity=0, n_jobs=1)
    xgb_model.fit(X_sub, y_sub, sample_weight=sample_weights)
    models_config.append(('XGBoost', xgb_model))
    print("OK")
    print("[*] LightGBM (600 estimators, tuned for real data)...", end=' ', flush=True)
    import lightgbm as lgb
    lgb_model = lgb.LGBMClassifier(n_estimators=600, learning_rate=0.05, max_depth=8, num_leaves=48, subsample=0.85, colsample_bytree=0.85, min_child_samples=15, class_weight='balanced', reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbose=-1, n_jobs=1)
    lgb_model.fit(X_sub, y_sub, sample_weight=sample_weights)
    models_config.append(('LightGBM', lgb_model))
    print("OK")
    results = {}
    best_model = None
    best_score = 0
    best_name = ""
    for name, model in models_config:
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        pre = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        rec = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        cm = confusion_matrix(y_test, y_pred).tolist()
        results[name] = {'model': model, 'accuracy': acc, 'precision': pre, 'recall': rec, 'f1_score': f1, 'cv_mean': 0, 'cv_std': 0, 'confusion_matrix': cm}
        print(f"  {name:20s}  Acc:{acc:.4f}  F1:{f1:.4f}")
        if f1 > best_score:
            best_score, best_model, best_name = f1, model, name
    print(f"\n{'='*60}")
    print(f"  BEST MODEL: {best_name} | Acc: {results[best_name]['accuracy']:.4f} | F1: {best_score:.4f}")
    print(f"{'='*60}")
    metric_keys = ['accuracy', 'precision', 'recall', 'f1_score', 'cv_mean', 'cv_std']
    all_results = {n: {k: float(r[k]) for k in metric_keys} for n, r in results.items()}
    bm = results[best_name]
    return best_model, {'best_model_name': best_name, 'accuracy': float(bm['accuracy']), 'precision': float(bm['precision']), 'recall': float(bm['recall']), 'f1_score': float(bm['f1_score']), 'cv_mean': float(bm['cv_mean']), 'cv_std': float(bm['cv_std']), 'confusion_matrix': bm['confusion_matrix'], 'all_results': all_results}

def save_model_artifacts(model, scaler, label_encoder, metrics, cols):
    print(f"\n[*] Saving model artifacts...")
    joblib.dump(model, MODEL_PATH)
    print(f"  [OK] Model saved ({os.path.getsize(MODEL_PATH)/1024/1024:.1f} MB)")
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(label_encoder, ENCODER_PATH)
    print(f"  [OK] Scaler & encoder saved")
    metadata = {'model_type': type(model).__name__, 'best_model_name': metrics['best_model_name'], 'accuracy': metrics['accuracy'], 'precision': metrics['precision'], 'recall': metrics['recall'], 'f1_score': metrics['f1_score'], 'cv_mean': metrics['cv_mean'], 'cv_std': metrics['cv_std'], 'confusion_matrix': metrics['confusion_matrix'], 'all_results': metrics['all_results'], 'feature_count': len(cols), 'features': cols, 'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'label_classes': ['Buy', 'Hold', 'Sell'], 'training_source': 'REAL_MARKET_DATA', 'forward_window_days': FORWARD_WINDOW, 'buy_threshold': BUY_THRESHOLD, 'sell_threshold': SELL_THRESHOLD}
    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  [OK] Metadata saved")
    print(f"  [OK] Training source: REAL_MARKET_DATA")

def main():
    start_time = time.time()
    print("="*60)
    print("  ESG Stock Prediction - Real Data Training Pipeline")
    print("="*60)
    print(f"  Features:      {len(feature_cols)}")
    print(f"  Label window:  {FORWARD_WINDOW} trading days")
    print(f"  Buy threshold: +{BUY_THRESHOLD*100:.0f}% forward return")
    print(f"  Sell threshold: {SELL_THRESHOLD*100:.0f}% forward return")
    print(f"  Data source:   yfinance (real historical stock data)")
    print("="*60)
    ensure_directories()
    X_scaled, y_encoded, scaler, label_encoder, used_features = build_training_dataset()
    if X_scaled is None:
        print("\n[!] Training dataset building failed!")
        return
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded)
    print(f"\n[*] Data Split:")
    print(f"  Training:   {X_train.shape[0]}")
    print(f"  Testing:    {X_test.shape[0]}")
    print(f"  Features:   {X_train.shape[1]}")
    best_model, metrics = train_models(X_train, X_test, y_train, y_test)
    save_model_artifacts(best_model, scaler, label_encoder, metrics, used_features)
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print("  TRAINING COMPLETE!")
    print(f"  Best Model:     {metrics['best_model_name']}")
    print(f"  Accuracy:       {metrics['accuracy']:.2%}")
    print(f"  F1 Score:       {metrics['f1_score']:.2%}")
    print(f"  Training data:  REAL market data from yfinance")
    print(f"  Time elapsed:   {elapsed:.0f}s")
    print("="*60)

if __name__ == '__main__':
    main()
'''

with open(target_path, 'w') as f:
    f.write(content)
print(f'Written {len(content)} bytes to {target_path}')
