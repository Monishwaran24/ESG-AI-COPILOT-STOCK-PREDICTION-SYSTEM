import os, sys, warnings, numpy as np, pandas as pd, yfinance as yf
import joblib, json
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
METADATA_PATH = os.path.join(MODEL_DIR, 'model_metadata.json')
ESG_DATA_PATH = os.path.join(DATA_DIR, 'esg_data.csv')

_model_cache = None
_scaler_cache = None
_encoder_cache = None
_metadata_cache = None

feature_cols = [
    'SMA_10','SMA_30','EMA_10','EMA_30','RSI_14',
    'MACD','MACD_Signal','MACD_Histogram',
    'BB_Width','BB_Position',
    'Price_Change_1d','Price_Change_5d','Price_Change_20d',
    'Volume_Ratio','High_Low_Ratio','Close_Open_Ratio','Volatility_10d',
    'Price_Acceleration','VPT_Change','RSI_SMA','Price_Position',
    'ESG_Score','Environmental_Score','Social_Score','Governance_Score'
]

def load_model():
    global _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    if _model_cache is not None:
        return _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    try:
        _model_cache = joblib.load(MODEL_PATH)
        _scaler_cache = joblib.load(SCALER_PATH)
        _encoder_cache = joblib.load(ENCODER_PATH)
        with open(METADATA_PATH, 'r') as f:
            _metadata_cache = json.load(f)
        return _model_cache, _scaler_cache, _encoder_cache, _metadata_cache
    except Exception as e:
        print(f"[X] Error loading model: {e}")
        return None, None, None, None

def get_stock_data(ticker, period='6mo'):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period)
        if data.empty:
            return None
        return data
    except Exception as e:
        print(f"[X] Error: {e}")
        return None

def calculate_indicators(df):
    df = df.copy()
    if len(df) < 30:
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
    df['High_Low_Ratio'] = (df['High'] - df['Low']) / df['Close']
    df['Close_Open_Ratio'] = (df['Close'] - df['Open']) / df['Open']
    df['Volatility_10d'] = df['Price_Change_1d'].rolling(window=10, min_periods=1).std()
    df['Price_Acceleration'] = df['Price_Change_5d'] - df['Price_Change_20d'].shift(5)
    df['Volume_Price_Trend'] = df['Close'] * df['Volume']
    df['VPT_Change'] = df['Volume_Price_Trend'].pct_change(periods=5)
    df['RSI_SMA'] = df['RSI_14'] - df['RSI_14'].rolling(window=10, min_periods=1).mean()
    df['Price_Position'] = (df['Close'] - df['Low'].rolling(window=20, min_periods=1).min()) / (df['High'].rolling(window=20, min_periods=1).max() - df['Low'].rolling(window=20, min_periods=1).min() + 1e-10)

    latest = df.iloc[-1:]
    indicators_obj = {}
    for col in feature_cols[:21]:
        if col in latest.columns:
            val = latest[col].values[0]
            indicators_obj[col] = float(val) if pd.notna(val) else 0.0
        else:
            indicators_obj[col] = 0.0

    historical_prices = df['Close'].tail(180).tolist()
    historical_dates = df.index[-180:].strftime('%Y-%m-%d').tolist()

    return {
        'indicators': indicators_obj,
        'current_price': float(df['Close'].iloc[-1]),
        'current_open': float(df['Open'].iloc[-1]),
        'current_high': float(df['High'].iloc[-1]),
        'current_low': float(df['Low'].iloc[-1]),
        'current_volume': int(df['Volume'].iloc[-1]),
        'price_change': float(df['Close'].pct_change().iloc[-1] * 100),
        'historical_prices': historical_prices,
        'historical_dates': historical_dates
    }

def get_esg_data(ticker):
    try:
        esg_df = pd.read_csv(ESG_DATA_PATH)
        ticker_data = esg_df[esg_df['Ticker'].str.upper() == ticker.upper()]
        if not ticker_data.empty:
            row = ticker_data.iloc[0]
            return {
                'esg_score': float(row['ESG_Score']),
                'environmental_score': float(row['Environmental_Score']),
                'social_score': float(row['Social_Score']),
                'governance_score': float(row['Governance_Score']),
                'company': str(row['Company']),
                'industry': str(row['Industry']),
                'esg_risk': str(row['ESG_Risk_Rating']),
                'controversy': str(row['Controversy_Level'])
            }
        ticker_info = yf.Ticker(ticker)
        info = ticker_info.info if hasattr(ticker_info, 'info') else {}
        return {
            'esg_score': 50.0, 'environmental_score': 50.0,
            'social_score': 50.0, 'governance_score': 50.0,
            'company': info.get('longName', ticker.upper()),
            'industry': info.get('industry', 'N/A'),
            'esg_risk': 'Medium', 'controversy': 'Low'
        }
    except FileNotFoundError:
        return {
            'esg_score': 50.0, 'environmental_score': 50.0,
            'social_score': 50.0, 'governance_score': 50.0,
            'company': ticker.upper(), 'industry': 'N/A',
            'esg_risk': 'Medium', 'controversy': 'Low'
        }

def generate_ai_explanation(result):
    rec = result['recommendation']
    confidence = result['confidence']
    trend = result['trend']
    risk = result['risk_level']
    ind = result['indicators']
    esg = result['esg_data']

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

    price_5d = ind.get('price_change_5d', 0)
    price_20d = ind.get('price_change_20d', 0)
    if price_20d > 3:
        reasons.append("Strong positive performance over the last month")
    elif price_20d < -3:
        reasons.append("Notable decline over the last month")

    summary = f"This stock shows a **{rec}** signal with {confidence:.1f}% confidence. "
    summary += f"The overall trend is **{trend}** with a **{risk}** risk level. "

    if rec == 'Buy':
        summary += "The AI model identifies favorable conditions for price appreciation. "
    elif rec == 'Sell':
        summary += "The AI model suggests caution with indicators pointing to potential decline. "
    else:
        summary += "The AI model recommends holding as signals are mixed. "

    summary += "Key factors driving this prediction: "
    summary += "; ".join(reasons[:4])
    summary += "."

    return {
        'summary': summary,
        'reasons': reasons,
        'verdict': rec,
        'confidence': confidence,
        'risk_level': risk,
        'trend': trend
    }

def predict_stock(ticker):
    model, scaler, label_encoder, metadata = load_model()
    if model is None:
        return {'error': 'Model not trained'}

    stock_info = get_stock_data(ticker)
    if stock_info is None:
        return {'error': f'Unable to fetch data for {ticker}'}

    result = calculate_indicators(stock_info)
    if result is None:
        return {'error': f'Insufficient data for {ticker}'}

    indicators = result['indicators']
    current_price = result['current_price']
    esg_data = get_esg_data(ticker)

    indicators['ESG_Score'] = esg_data['esg_score']
    indicators['Environmental_Score'] = esg_data['environmental_score']
    indicators['Social_Score'] = esg_data['social_score']
    indicators['Governance_Score'] = esg_data['governance_score']

    feature_vector = []
    for col in feature_cols:
        if col in indicators:
            feature_vector.append(indicators[col])
        else:
            feature_vector.append(0.0)

    feature_vector = np.array(feature_vector).reshape(1, -1)
    feature_scaled = scaler.transform(feature_vector)

    prediction = model.predict(feature_scaled)
    if hasattr(model, 'predict_proba'):
        prediction_proba = model.predict_proba(feature_scaled)
    else:
        prediction_proba = np.array([[0.33, 0.34, 0.33]])

    predicted_class = label_encoder.inverse_transform(prediction)[0]

    confidence_scores = {}
    for i, cls_name in enumerate(label_encoder.classes_):
        prob = float(prediction_proba[0][i]) if i < prediction_proba.shape[1] else 0.33
        confidence_scores[str(cls_name)] = round(prob * 100, 2)

    confidence = float(np.max(prediction_proba) * 100)

    trend = determine_trend(indicators, current_price)
    risk_level = determine_risk_level(indicators, esg_data)

    response = {
        'ticker': ticker.upper(),
        'company': esg_data['company'],
        'industry': esg_data['industry'],
        'current_price': round(current_price, 2),
        'price_change_pct': round(result['price_change'], 2),
        'recommendation': predicted_class,
        'confidence': round(confidence, 2),
        'confidence_scores': confidence_scores,
        'trend': trend,
        'risk_level': risk_level,
        'model_used': metadata.get('best_model_name', 'Ensemble'),
        'model_accuracy': round(metadata.get('accuracy', 0) * 100, 2),
        'esg_data': esg_data,
        'indicators': {
            'rsi': round(indicators['RSI_14'], 2),
            'macd': round(indicators['MACD'], 4),
            'sma_10': round(indicators['SMA_10'], 2),
            'sma_30': round(indicators['SMA_30'], 2),
            'bb_upper': round(current_price + (indicators['BB_Width'] * current_price / 2), 2),
            'bb_lower': round(current_price - (indicators['BB_Width'] * current_price / 2), 2),
            'volume_ratio': round(indicators['Volume_Ratio'], 2),
            'volatility': round(indicators['Volatility_10d'] * 100, 2),
            'price_change_1d': round(indicators['Price_Change_1d'] * 100, 2),
            'price_change_5d': round(indicators['Price_Change_5d'] * 100, 2),
            'price_change_20d': round(indicators['Price_Change_20d'] * 100, 2),
        },
        'historical_prices': result['historical_prices'],
        'historical_dates': result['historical_dates'],
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
    print("  ESG Stock Prediction - Test")
    print("="*60)
    for ticker in ['AAPL', 'MSFT', 'TSLA']:
        print(f"\n{'='*40}")
        print(f"  Predicting {ticker}...")
        result = predict_stock(ticker)
        if 'error' in result:
            print(f"  [X] Error: {result['error']}")
        else:
            print(f"  Company:      {result['company']}")
            print(f"  Price:        ${result['current_price']}")
            print(f"  Rec:          {result['recommendation']}")
            print(f"  Confidence:   {result['confidence']:.1f}%")
            print(f"  Trend:        {result['trend']}")
            print(f"  Risk:         {result['risk_level']}")
            print(f"  Model:        {result['model_used']}")
            print(f"  AI:           {result['ai_explanation']['summary'][:80]}...")
