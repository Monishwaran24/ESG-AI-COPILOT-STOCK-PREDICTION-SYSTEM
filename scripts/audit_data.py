"""Comprehensive data quality audit for ESG stock prediction."""
import pandas as pd, numpy as np, os, sys, json, warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')

print("="*70)
print("  COMPREHENSIVE DATA QUALITY & MODEL AUDIT")
print("="*70)

# ==================== 1. ESG DATA AUDIT ====================
print("\n--- SECTION 1: ESG DATA QUALITY ---")
df = pd.read_csv(os.path.join(DATA_DIR, 'esg_data.csv'))
print(f"  Rows: {len(df)}, Columns: {len(df.columns)}")
print(f"  Columns: {list(df.columns)}")
print()

# Missing values
print("  Missing Values:")
missing = df.isna().sum()
missing = missing[missing > 0]
if len(missing) == 0:
    print("    [OK] No missing values found!")
else:
    for c, m in missing.items():
        print(f"    {c}: {m} ({m/len(df)*100:.1f}%)")

print()
print("  ESG Score Distribution:")
print(f"    Mean:   {df['ESG_Score'].mean():.1f}")
print(f"    Std:    {df['ESG_Score'].std():.1f}")
print(f"    Min:    {df['ESG_Score'].min():.1f}")
print(f"    Max:    {df['ESG_Score'].max():.1f}")
print(f"    Q25:    {df['ESG_Score'].quantile(0.25):.1f}")
print(f"    Q75:    {df['ESG_Score'].quantile(0.75):.1f}")
print()
print("  Sub-score Correlations:")
print(f"    Env vs Soc:  {df['Environmental_Score'].corr(df['Social_Score']):.3f}")
print(f"    Env vs Gov:  {df['Environmental_Score'].corr(df['Governance_Score']):.3f}")
print(f"    Soc vs Gov:  {df['Social_Score'].corr(df['Governance_Score']):.3f}")

print()
print("  Duplicate Tickers:")
dupes = df[df['Ticker'].duplicated(keep=False)]
if len(dupes) > 0:
    print(f"    [WARN] Found {len(dupes)} rows with duplicate tickers!")
    print(f"    Tickers: {dupes['Ticker'].tolist()}")
else:
    print("    [OK] No duplicate tickers")

print()
print("  Industry Distribution (top 10):")
for ind, cnt in df['Industry'].value_counts().head(10).items():
    print(f"    {ind:40s} {cnt:3d}")

print()
print("  Country Distribution:")
for cntry, cnt in df['Country'].value_counts().items():
    print(f"    {cntry:30s} {cnt:3d}")

# ==================== 2. CURRENT MODEL AUDIT ====================
print("\n--- SECTION 2: CURRENT MODEL STATE ---")
if os.path.exists(METADATA_PATH):
    with open(METADATA_PATH, 'r') as f:
        meta = json.load(f)
    print(f"  Model type:     {meta.get('best_model_name', 'N/A')}")
    print(f"  Accuracy:       {meta.get('accuracy', 0)*100:.2f}%")
    print(f"  F1 Score:       {meta.get('f1_score', 0)*100:.2f}%")
    print(f"  Training date:  {meta.get('training_date', 'N/A')}")
    print(f"  Data source:    {meta.get('training_source', 'N/A')}")
    print(f"  Features:       {meta.get('feature_count', 0)}")
    
    cm = meta.get('confusion_matrix', [])
    if cm:
        print(f"\n  Confusion Matrix:\n    {'':>10}", end='')
        labels = ['Sell', 'Hold', 'Buy']
        for l in labels:
            print(f"{l:>8}", end='')
        print()
        for i, row in enumerate(cm):
            print(f"    {labels[i]:>10}", end='')
            for v in row:
                print(f"{v:>8}", end='')
            print()
else:
    print("  [WARN] No model metadata found! Model not trained yet.")

# ==================== 3. BUG ANALYSIS ====================
print("\n--- SECTION 3: DATA LEAKAGE & BUG ANALYSIS ---")
print("""
  [CRITICAL] RANDOM TRAIN/TEST SPLIT
     Using train_test_split(random_state=42) leaks future data into training!
     Time series must use sorted split or TimeSeriesSplit.

  [MINOR] MIN_PERIODS=1 in many indicators
     Early rows with only 1-9 data points produce unreliable indicator values.
     These ~20 rows per stock add noise to training.

  [FIXED] KAMA NaN propagation (sc.fillna(0))
  [FIXED] Aroon min_periods=25
  [FIXED] Index error in build_real_training_data

  [CRITICAL] Feature list mismatch between predict.py and train_model.py
     predict.py:  36 features (base only)
     train_model.py: 67 features (base + extended)
     Prediction will use DIFFERENT features than training!

  [INFO] Forward return labeling with +-5% over 20 days
     Produces roughly balanced classes (~33% each).
""")

# ==================== 4. FEATURE COMPARISON ====================
print("--- SECTION 4: FEATURE LIST COMPARISON ---")
predict_features = [
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

train_features = predict_features + [
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

print(f"  predict.py:        {len(predict_features)} features")
print(f"  train_model.py:    {len(train_features)} features")
print(f"  MISMATCH:          {len(train_features) - len(predict_features)} features missing in predict.py")

missing = sorted(set(train_features) - set(predict_features))
for f in missing:
    print(f"    [MISSING] {f}")

print("\n  [RECOMMENDATION] Sync predict.py to compute ALL 67 features.")

# ==================== 5. MODEL FILES ====================
print("\n--- SECTION 5: MODEL FILE INTEGRITY ---")
for fname in ['model.pkl', 'scaler.pkl', 'label_encoder.pkl', 'model_metadata.json']:
    path = os.path.join(MODEL_DIR, fname)
    if os.path.exists(path):
        size_kb = os.path.getsize(path) / 1024
        print(f"  [OK] {fname:30s} {size_kb:>8.1f} KB")
    else:
        print(f"  [WARN] {fname:30s} MISSING!")

print("\n" + "="*70)
print("  AUDIT COMPLETE")
print("="*70)
