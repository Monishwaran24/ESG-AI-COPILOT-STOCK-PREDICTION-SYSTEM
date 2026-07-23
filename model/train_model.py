import os, sys, warnings, numpy as np, pandas as pd, yfinance as yf
from datetime import datetime, timedelta
import joblib, json
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier, AdaBoostClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.feature_selection import SelectFromModel

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
STOCK_LIST_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

STOCK_TICKERS = [
    'AAPL','MSFT','GOOGL','AMZN','TSLA','JPM','V','JNJ',
    'WMT','PG','NVDA','DIS','NFLX','ADBE','CRM','INTC',
    'AMD','PYPL','BA','NKE','UNH','HD','MRK','PFE',
    'KO','PEP','COST','ABT','ACN','LIN','IBM','CSCO',
    'SBUX','MCD','CAT','INTU','VZ'
]

TRAINING_PERIOD = '2y'
np.random.seed(42)

def ensure_directories():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

def calculate_technical_indicators(df):
    df = df.copy()
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
    df['High_Low_Ratio'] = (df['High'] - df['Low']) / df['Close']
    df['Close_Open_Ratio'] = (df['Close'] - df['Open']) / df['Open']
    df['Volatility_10d'] = df['Price_Change_1d'].rolling(window=10, min_periods=1).std()
    df['Price_Acceleration'] = df['Price_Change_5d'] - df['Price_Change_20d'].shift(5)
    df['Volume_Price_Trend'] = df['Close'] * df['Volume']
    df['VPT_Change'] = df['Volume_Price_Trend'].pct_change(periods=5)
    df['RSI_SMA'] = df['RSI_14'] - df['RSI_14'].rolling(window=10, min_periods=1).mean()
    df['Price_Position'] = (df['Close'] - df['Low'].rolling(window=20, min_periods=1).min()) / (df['High'].rolling(window=20, min_periods=1).max() - df['Low'].rolling(window=20, min_periods=1).min() + 1e-10)
    return df

def generate_target_labels(df):
    df = df.copy()
    df['Future_Return_10d'] = df['Close'].shift(-10) / df['Close'] - 1
    df['Future_Return_20d'] = df['Close'].shift(-20) / df['Close'] - 1
    df['Future_Return_30d'] = df['Close'].shift(-30) / df['Close'] - 1
    composite_return = (df['Future_Return_10d'] * 0.5 + df['Future_Return_20d'] * 0.3 + df['Future_Return_30d'] * 0.2)
    conditions = [composite_return > 0.04, composite_return < -0.025]
    choices = ['Buy', 'Sell']
    df['Target'] = np.select(conditions, choices, default='Hold')
    return df

def build_training_dataset():
    print("\n" + "="*60)
    print("  ESG Stock Prediction - Training Dataset Builder")
    print("="*60)

    print("\n[*] Loading ESG data...")
    try:
        esg_df = pd.read_csv(STOCK_LIST_PATH)
        print(f"[OK] Loaded ESG data for {len(esg_df)} companies")
    except FileNotFoundError:
        print("[*] Creating synthetic ESG data...")
        esg_df = create_synthetic_esg_data()

    feature_cols = [
        'SMA_10','SMA_30','EMA_10','EMA_30','RSI_14',
        'MACD','MACD_Signal','MACD_Histogram',
        'BB_Width','BB_Position',
        'Price_Change_1d','Price_Change_5d','Price_Change_20d',
        'Volume_Ratio','High_Low_Ratio','Close_Open_Ratio','Volatility_10d',
        'Price_Acceleration','VPT_Change','RSI_SMA','Price_Position',
        'ESG_Score','Environmental_Score','Social_Score','Governance_Score'
    ]

    all_features = []
    all_labels = []
    successful_tickers = []

    for ticker in STOCK_TICKERS:
        print(f"\n[*] Processing {ticker}...")
        try:
            ticker_esg = esg_df[esg_df['Ticker'] == ticker]
            if ticker_esg.empty:
                print(f"  [!] No ESG data for {ticker}")
                continue

            stock_data = yf.download(ticker, period=TRAINING_PERIOD, interval='1d', progress=False)
            if stock_data.empty or len(stock_data) < 60:
                print(f"  [!] Insufficient data for {ticker}")
                continue

            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)

            stock_data = calculate_technical_indicators(stock_data)
            stock_data = generate_target_labels(stock_data)
            stock_data = stock_data.dropna()

            if len(stock_data) < 20:
                print(f"  [!] Not enough clean data for {ticker}")
                continue

            for idx in range(len(stock_data) - 30):
                row = stock_data.iloc[idx]
                row_features = {}
                for col in feature_cols:
                    if col in row and pd.notna(row[col]):
                        row_features[col] = row[col]
                    elif col in ticker_esg.iloc[0] and pd.notna(ticker_esg.iloc[0][col]):
                        row_features[col] = ticker_esg.iloc[0][col]
                    else:
                        row_features[col] = 0.0

                all_features.append(row_features)
                all_labels.append(stock_data['Target'].iloc[idx])

            print(f"  [OK] Added samples from {ticker}")

        except Exception as e:
            print(f"  [X] Error: {str(e)[:50]}")
            continue

    if not all_features:
        print("\n[X] No training data collected! Generating synthetic data...")
        return generate_synthetic_training_data(feature_cols)

    X = pd.DataFrame(all_features)
    y = pd.Series(all_labels)

    print(f"\n{'='*60}")
    print(f"  Dataset Summary:")
    print(f"  Total Samples: {len(X)}")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Class Distribution:")
    for cls in ['Buy', 'Hold', 'Sell']:
        print(f"    {cls}: {(y == cls).sum()}")
    print(f"{'='*60}")

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    X = X.fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X_scaled, y_encoded, scaler, label_encoder, feature_cols

def create_synthetic_esg_data():
    tickers = STOCK_TICKERS
    np.random.seed(42)
    data = []
    for ticker in tickers:
        data.append({
            'Ticker': ticker,
            'ESG_Score': np.random.uniform(50, 90),
            'Environmental_Score': np.random.uniform(40, 85),
            'Social_Score': np.random.uniform(50, 90),
            'Governance_Score': np.random.uniform(55, 90)
        })
    return pd.DataFrame(data)

def generate_synthetic_training_data(feature_cols):
    np.random.seed(42)
    n_samples = 5000

    X_raw = np.random.randn(n_samples, len(feature_cols))

    for c in range(len(feature_cols)):
        if feature_cols[c] in ['RSI_14']:
            X_raw[:, c] = np.clip(X_raw[:, c] * 15 + 50, 0, 100)
        elif feature_cols[c] in ['SMA_10', 'SMA_30', 'EMA_10', 'EMA_30']:
            X_raw[:, c] = X_raw[:, c] * 50 + 150
        elif feature_cols[c] in ['MACD', 'MACD_Signal', 'MACD_Histogram']:
            X_raw[:, c] = X_raw[:, c] * 0.5
        elif feature_cols[c] in ['Volatility_10d']:
            X_raw[:, c] = np.abs(X_raw[:, c]) * 0.02 + 0.01
        elif feature_cols[c] in ['BB_Width']:
            X_raw[:, c] = np.abs(X_raw[:, c]) * 0.02 + 0.02
        elif feature_cols[c] in ['BB_Position']:
            X_raw[:, c] = np.clip(X_raw[:, c] * 0.15 + 0.5, 0, 1)
        elif feature_cols[c] in ['Price_Change_1d', 'Price_Change_5d', 'Price_Change_20d']:
            X_raw[:, c] = X_raw[:, c] * 0.02
        elif feature_cols[c] in ['Volume_Ratio']:
            X_raw[:, c] = np.abs(X_raw[:, c]) * 0.5 + 1.0
        elif feature_cols[c] in ['ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score']:
            X_raw[:, c] = np.clip(X_raw[:, c] * 10 + 65, 30, 100)

    rsi_idx = feature_cols.index('RSI_14')
    macd_idx = feature_cols.index('MACD')
    vol_idx = feature_cols.index('Volatility_10d')
    pc20_idx = feature_cols.index('Price_Change_20d')
    esg_idx = feature_cols.index('ESG_Score')

    signal = (
        0.15 * (X_raw[:, rsi_idx] < 35).astype(float) -
        0.15 * (X_raw[:, rsi_idx] > 70).astype(float) +
        0.20 * X_raw[:, macd_idx] * 2 +
        0.15 * X_raw[:, pc20_idx] * 10 +
        0.10 * (X_raw[:, esg_idx] > 75).astype(float) -
        0.05 * (X_raw[:, esg_idx] < 50).astype(float) +
        0.15 * (X_raw[:, vol_idx] < 0.02).astype(float) -
        0.10 * (X_raw[:, vol_idx] > 0.04).astype(float) +
        np.random.normal(0, 0.3, n_samples)
    )

    y = np.where(signal > 0.4, 2, np.where(signal < -0.3, 0, 1))

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(pd.Series(y).map({0: 'Sell', 1: 'Hold', 2: 'Buy'}))

    print(f"[!] Using {n_samples} enhanced synthetic training samples")
    return X_scaled, y_encoded, scaler, label_encoder, feature_cols

def train_models(X_train, X_test, y_train, y_test):
    print("\n" + "="*60)
    print("  Training Machine Learning Models")
    print("="*60)

    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

    rf = RandomForestClassifier(n_estimators=200, max_depth=18, min_samples_split=5, min_samples_leaf=2, random_state=42, n_jobs=-1)
    dt = DecisionTreeClassifier(max_depth=15, min_samples_split=5, min_samples_leaf=3, random_state=42)
    gb = GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, max_depth=5, subsample=0.8, random_state=42)
    ada = AdaBoostClassifier(n_estimators=80, learning_rate=0.1, random_state=42)

    models = {
        'Random Forest': rf,
        'Decision Tree': dt,
        'Gradient Boosting': gb,
        'AdaBoost': ada
    }

    try:
        import xgboost as xgb
        models['XGBoost'] = xgb.XGBClassifier(n_estimators=150, learning_rate=0.1, max_depth=6, subsample=0.8, random_state=42, eval_metric='mlogloss')
        print("[OK] XGBoost included")
    except ImportError:
        print("[!] XGBoost not available")

    results = {}
    trained_models = {}
    best_model = None
    best_score = 0
    best_name = ""

    for name, model in models.items():
        print(f"\n[*] Training {name}...")
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='accuracy')

        results[name] = {
            'model': model,
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'cv_mean': cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist()
        }
        trained_models[name] = model

        print(f"  Accuracy:  {accuracy:.4f}")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall:    {recall:.4f}")
        print(f"  F1 Score:  {f1:.4f}")
        print(f"  CV Score:  {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

        if f1 > best_score:
            best_score = f1
            best_model = model
            best_name = name

    voting_clf = VotingClassifier(
        estimators=[(name, trained_models[name]) for name in trained_models],
        voting='soft'
    )
    print(f"\n[*] Training Ensemble Voting Classifier...")
    voting_clf.fit(X_train, y_train)
    y_pred_vote = voting_clf.predict(X_test)

    vote_accuracy = accuracy_score(y_test, y_pred_vote)
    vote_precision = precision_score(y_test, y_pred_vote, average='weighted', zero_division=0)
    vote_recall = recall_score(y_test, y_pred_vote, average='weighted', zero_division=0)
    vote_f1 = f1_score(y_test, y_pred_vote, average='weighted', zero_division=0)
    vote_cv = cross_val_score(voting_clf, X_train[:5000], y_train[:5000], cv=3, scoring='accuracy')

    results['Ensemble (Voting)'] = {
        'model': voting_clf,
        'accuracy': vote_accuracy, 'precision': vote_precision,
        'recall': vote_recall, 'f1_score': vote_f1,
        'cv_mean': vote_cv.mean(), 'cv_std': vote_cv.std(),
        'confusion_matrix': confusion_matrix(y_test, y_pred_vote).tolist()
    }

    print(f"\n[*] Ensemble Voting Classifier:")
    print(f"  Accuracy:  {vote_accuracy:.4f}")
    print(f"  F1 Score:  {vote_f1:.4f}")
    print(f"  CV Score:  {vote_cv.mean():.4f} (+/- {vote_cv.std():.4f})")

    if vote_f1 > best_score:
        best_score = vote_f1
        best_model = voting_clf
        best_name = "Ensemble (Voting)"

    print(f"\n{'='*60}")
    print(f"  BEST MODEL: {best_name} (F1: {best_score:.4f})")
    print(f"{'='*60}")

    all_results = {}
    for name, r in results.items():
        all_results[name] = {
            'accuracy': float(r['accuracy']),
            'precision': float(r['precision']),
            'recall': float(r['recall']),
            'f1_score': float(r['f1_score']),
            'cv_mean': float(r['cv_mean']),
            'cv_std': float(r['cv_std'])
        }

    best_metrics = results[best_name]
    return best_model, {
        'best_model_name': best_name,
        'accuracy': float(best_metrics['accuracy']),
        'precision': float(best_metrics['precision']),
        'recall': float(best_metrics['recall']),
        'f1_score': float(best_metrics['f1_score']),
        'cv_mean': float(best_metrics['cv_mean']),
        'cv_std': float(best_metrics['cv_std']),
        'confusion_matrix': best_metrics['confusion_matrix'],
        'all_results': all_results
    }

def save_model_artifacts(model, scaler, label_encoder, metrics, feature_cols):
    print(f"\n[*] Saving model artifacts...")
    joblib.dump(model, MODEL_PATH)
    print(f"  [OK] Model saved")
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
        'feature_count': len(feature_cols),
        'features': feature_cols,
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'label_classes': ['Buy', 'Hold', 'Sell']
    }

    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  [OK] Metadata saved")

def main():
    print("\n" + "="*60)
    print("  ESG Stock Prediction - Advanced Model Training")
    print("="*60)

    ensure_directories()
    X_scaled, y_encoded, scaler, label_encoder, feature_cols = build_training_dataset()

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )

    print(f"\n[*] Data Split:")
    print(f"  Training:   {X_train.shape[0]}")
    print(f"  Testing:    {X_test.shape[0]}")
    print(f"  Features:   {X_train.shape[1]}")

    best_model, metrics = train_models(X_train, X_test, y_train, y_test)
    save_model_artifacts(best_model, scaler, label_encoder, metrics, feature_cols)

    print("\n" + "="*60)
    print("  TRAINING COMPLETE!")
    print(f"  Best Model: {metrics['best_model_name']}")
    print(f"  Accuracy:   {metrics['accuracy']:.2%}")
    print(f"  F1 Score:   {metrics['f1_score']:.2%}")
    print("="*60)

if __name__ == '__main__':
    main()
