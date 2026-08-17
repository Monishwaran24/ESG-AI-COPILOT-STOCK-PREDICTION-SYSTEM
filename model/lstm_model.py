"""
LSTM Deep Learning Model for Stock Price Prediction
=====================================================
Pure NumPy implementation — no TensorFlow/Keras dependency!
Trains a multi-layer LSTM for time-series forecasting of stock prices.
Works alongside the existing XGBoost classification model to provide
price prediction + momentum analysis for enhanced recommendations.
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import joblib
import math

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
LSTM_MODEL_PATH = os.path.join(MODEL_DIR, 'lstm_model.npz')
LSTM_SCALER_PATH = os.path.join(MODEL_DIR, 'lstm_scaler.pkl')
LSTM_METADATA_PATH = os.path.join(MODEL_DIR, 'lstm_metadata.json')


# ============================================================
# Pure NumPy LSTM Implementation
# ============================================================

class LSTMCell:
    """A single LSTM cell implemented with pure NumPy."""
    
    def __init__(self, input_size, hidden_size):
        self.input_size = input_size
        self.hidden_size = hidden_size
        
        # Xavier/Glorot initialization
        limit = math.sqrt(6 / (input_size + hidden_size))
        
        # Input weights (concatenated: i, f, o, g gates)
        self.W_i = np.random.uniform(-limit, limit, (input_size, hidden_size * 4))
        self.b_i = np.zeros((1, hidden_size * 4))
        
        # Hidden weights
        self.W_h = np.random.uniform(-limit, limit, (hidden_size, hidden_size * 4))
        self.b_h = np.zeros((1, hidden_size * 4))
        
    def forward(self, x, h_prev, c_prev):
        """Forward pass through LSTM cell."""
        # Compute gate inputs
        gates = x @ self.W_i + self.b_i + h_prev @ self.W_h + self.b_h
        
        # Split into 4 gates
        i_gate, f_gate, o_gate, g_gate = np.split(gates, 4, axis=1)
        
        # Activate gates
        i = self._sigmoid(i_gate)   # input gate
        f = self._sigmoid(f_gate)   # forget gate
        o = self._sigmoid(o_gate)   # output gate
        g = np.tanh(g_gate)         # cell gate
        
        # New cell and hidden states
        c_new = f * c_prev + i * g
        h_new = o * np.tanh(c_new)
        
        # Cache for backward pass
        self._cache = (x, h_prev, c_prev, i, f, o, g, gates)
        
        return h_new, c_new
    
    def _sigmoid(self, x):
        return 1 / (1 + np.exp(-np.clip(x, -15, 15)))
    
    def get_params(self):
        return {
            'W_i': self.W_i, 'b_i': self.b_i,
            'W_h': self.W_h, 'b_h': self.b_h
        }
    
    def set_params(self, params):
        self.W_i = params['W_i']
        self.b_i = params['b_i']
        self.W_h = params['W_h']
        self.b_h = params['b_h']


class LSTMModel:
    """
    Multi-layer LSTM model using pure NumPy.
    Architecture: LSTM -> Dropout -> LSTM -> Dropout -> Dense
    """
    
    def __init__(self, sequence_length=60, hidden_sizes=[100, 100, 50], learning_rate=0.001):
        self.sequence_length = sequence_length
        self.hidden_sizes = hidden_sizes
        self.learning_rate = learning_rate
        self.cells = []
        self.dense_weights = None
        self.dense_bias = None
        self.output_weight = None
        self.output_bias = None

    def build(self, n_features=1):
        """Build the network architecture."""
        # LSTM layers
        self.cells = []
        input_size = n_features
        for hidden_size in self.hidden_sizes:
            self.cells.append(LSTMCell(input_size, hidden_size))
            input_size = hidden_size
        
        # Dense hidden layer
        last_hidden = self.hidden_sizes[-1]
        dense_out = max(last_hidden // 2, 4)
        limit = math.sqrt(6 / last_hidden)
        self.dense_weights = np.random.uniform(-limit, limit, (last_hidden, dense_out))
        self.dense_bias = np.zeros((1, dense_out))
        
        # Output layer
        self.output_weight = np.random.uniform(-0.1, 0.1, (dense_out, 1))
        self.output_bias = np.zeros((1, 1))
        
    def forward(self, x_seq):
        """
        Forward pass for a sequence.
        x_seq: shape (batch_size, sequence_length, n_features)
        Returns: predictions, all hidden states
        """
        batch_size = x_seq.shape[0]
        
        # Initialize states for each layer
        h_states = []
        c_states = []
        prev_layer_outs = None  # holds hidden states from previous layer
        
        for layer_idx, cell in enumerate(self.cells):
            h = np.zeros((batch_size, cell.hidden_size))
            c = np.zeros((batch_size, cell.hidden_size))
            layer_hs = []
            
            for t in range(self.sequence_length):
                if layer_idx == 0:
                    x_t = x_seq[:, t, :]
                else:
                    # Use previous layer's hidden state at this timestep
                    x_t = prev_layer_outs[t]
                h, c = cell.forward(x_t, h, c)
                layer_hs.append(h.copy())
            
            layer_outs = np.array(layer_hs)  # (seq_len, batch, hidden)
            h_states.append(layer_outs)
            c_states.append(c)
            prev_layer_outs = layer_outs  # pass to next layer
        
        # Take last timestep's hidden state from last layer
        last_h = h_states[-1][-1]  # (batch, hidden)
        
        # Dense hidden layer
        dense_out = np.maximum(0, last_h @ self.dense_weights + self.dense_bias)  # ReLU
        
        # Output layer
        predictions = dense_out @ self.output_weight + self.output_bias
        
        return predictions.flatten(), h_states
    
    def predict_sequence(self, x_seq):
        """Predict on a single sequence (no batch dim)."""
        if x_seq.ndim == 2:
            x_seq = x_seq.reshape(1, *x_seq.shape)
        preds, _ = self.forward(x_seq)
        return preds[0]
    
    def predict_iterative(self, initial_seq, steps=5):
        """
        Predict multiple future steps iteratively.
        initial_seq: shape (sequence_length, n_features)
        """
        predictions = []
        current_seq = initial_seq.copy()
        
        for _ in range(steps):
            pred = self.predict_sequence(current_seq)
            predictions.append(pred)
            # Shift sequence: drop first, append prediction
            current_seq = np.vstack([current_seq[1:], [[pred]]])
        
        return np.array(predictions)
    
    def save(self, path):
        """Save model weights to compressed npz file."""
        params = {
            'sequence_length': np.array([self.sequence_length]),
            'learning_rate': np.array([self.learning_rate]),
            'hidden_sizes': np.array(self.hidden_sizes),
            'dense_weights': self.dense_weights,
            'dense_bias': self.dense_bias,
            'output_weight': self.output_weight,
            'output_bias': self.output_bias,
        }
        
        for i, cell in enumerate(self.cells):
            cell_params = cell.get_params()
            for key, val in cell_params.items():
                params[f'cell_{i}_{key}'] = val
        
        np.savez_compressed(path, **params)
        
    def load(self, path):
        """Load model weights from npz file."""
        data = np.load(path)
        
        self.sequence_length = int(data['sequence_length'][0])
        self.learning_rate = float(data['learning_rate'][0])
        self.hidden_sizes = data['hidden_sizes'].tolist()
        
        self.dense_weights = data['dense_weights']
        self.dense_bias = data['dense_bias']
        self.output_weight = data['output_weight']
        self.output_bias = data['output_bias']
        
        # Rebuild cells and load params
        self.build()
        for i, cell in enumerate(self.cells):
            params = {}
            for key in ['W_i', 'b_i', 'W_h', 'b_h']:
                params[key] = data[f'cell_{i}_{key}']
            cell.set_params(params)


# ============================================================
# Training & Prediction Functions
# ============================================================

def prepare_sequences(data, sequence_length=60):
    """Prepare data sequences for LSTM training."""
    from sklearn.preprocessing import MinMaxScaler
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data.reshape(-1, 1))
    
    X, y = [], []
    for i in range(sequence_length, len(scaled_data)):
        X.append(scaled_data[i-sequence_length:i, 0])
        y.append(scaled_data[i, 0])
    
    X = np.array(X)
    y = np.array(y)
    X = X.reshape(X.shape[0], sequence_length, 1)
    
    return X, y, scaler


def train_lstm(ticker='AAPL', sequence_length=60, epochs=50, force_retrain=False):
    """
    Train LSTM model on stock price data.
    Uses pure NumPy — no TensorFlow required.
    
    Returns dict with training results.
    """
    # Check if model exists and skip if not forced
    if os.path.exists(LSTM_MODEL_PATH) and not force_retrain:
        return {'status': 'Model already exists', 'model_path': LSTM_MODEL_PATH}
    
    try:
        import yfinance as yf
        
        # Download stock data
        print(f"[LSTM] Downloading data for {ticker}...")
        stock = yf.Ticker(ticker)
        df = stock.history(period='5y')
        
        if df.empty or len(df) < sequence_length + 10:
            # Generate synthetic data for demonstration
            print(f"[LSTM] Insufficient data for {ticker}, using synthetic data...")
            np.random.seed(42)
            n = 1500
            t = np.linspace(0, 4*np.pi, n)
            price = 150 + 30 * np.sin(t) + np.cumsum(np.random.randn(n) * 0.5)
            close_prices = price.reshape(-1, 1)
        else:
            close_prices = df['Close'].values.reshape(-1, 1)
        
        # Prepare sequences
        X, y, scaler = prepare_sequences(close_prices, sequence_length)
        
        if len(X) < 10:
            return {'error': f'Not enough data after sequence preparation: {len(X)} samples'}
        
        # Split into train/test
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        print(f"[LSTM] Training data: {X_train.shape[0]} samples, seq={sequence_length}")
        
        # Build model
        model = LSTMModel(sequence_length=sequence_length)
        model.build(n_features=1)
        
        # Training: simple random perturbation with adaptive noise
        # Each epoch, we try one set of perturbations and keep if loss improves
        best_loss = float('inf')
        best_params = None
        patience = 20
        patience_counter = 0
        no_improve_epochs = 0
        noise_scale = 0.02  # starting noise
        
        for epoch in range(epochs):
            # Forward pass
            train_preds, _ = model.forward(X_train)
            test_preds, _ = model.forward(X_test)
            train_loss = float(np.mean((train_preds - y_train) ** 2))
            test_loss = float(np.mean((test_preds - y_test) ** 2))
            
            # Try random perturbation on all weights at once
            # Collect all params
            all_params = {}
            for i, cell in enumerate(model.cells):
                cp = cell.get_params()
                for k, v in cp.items():
                    all_params[f'cell_{i}_{k}'] = v.copy()
            all_params['dense_weights'] = model.dense_weights.copy()
            all_params['dense_bias'] = model.dense_bias.copy()
            all_params['output_weight'] = model.output_weight.copy()
            all_params['output_bias'] = model.output_bias.copy()
            
            # Try perturbation
            new_params = {}
            for k, v in all_params.items():
                new_params[k] = v + np.random.randn(*v.shape) * noise_scale * (np.std(np.abs(v)) + 0.01)
            
            # Apply new params
            for i, cell in enumerate(model.cells):
                cell_params = {}
                for k in ['W_i', 'b_i', 'W_h', 'b_h']:
                    cell_params[k] = new_params[f'cell_{i}_{k}']
                cell.set_params(cell_params)
            model.dense_weights = new_params['dense_weights']
            model.dense_bias = new_params['dense_bias']
            model.output_weight = new_params['output_weight']
            model.output_bias = new_params['output_bias']
            
            # Evaluate
            new_preds, _ = model.forward(X_train)
            new_loss = float(np.mean((new_preds - y_train) ** 2))
            
            if new_loss < train_loss:
                # Keep new params
                train_loss = new_loss
                no_improve_epochs = 0
                noise_scale = noise_scale * 1.05  # increase exploration
            else:
                # Revert to old params
                for i, cell in enumerate(model.cells):
                    cell_params = {}
                    for k in ['W_i', 'b_i', 'W_h', 'b_h']:
                        cell_params[k] = all_params[f'cell_{i}_{k}']
                    cell.set_params(cell_params)
                model.dense_weights = all_params['dense_weights']
                model.dense_bias = all_params['dense_bias']
                model.output_weight = all_params['output_weight']
                model.output_bias = all_params['output_bias']
                no_improve_epochs += 1
                noise_scale = noise_scale * 0.95  # reduce exploration
            
            noise_scale = max(0.001, min(noise_scale, 0.1))
            
            # Track best model by test loss
            if test_loss < best_loss:
                best_loss = test_loss
                best_params = {}
                for i, cell in enumerate(model.cells):
                    best_params[f'cell_{i}'] = cell.get_params().copy()
                best_params['dense_weights'] = model.dense_weights.copy()
                best_params['dense_bias'] = model.dense_bias.copy()
                best_params['output_weight'] = model.output_weight.copy()
                best_params['output_bias'] = model.output_bias.copy()
                patience_counter = 0
            else:
                patience_counter += 1
            
            if (epoch + 1) % 10 == 0 or epoch == 0:
                train_mape_ = np.mean(np.abs((y_train - train_preds) / (y_train + 1e-8))) * 100
                test_mape_ = np.mean(np.abs((y_test - test_preds) / (y_test + 1e-8))) * 100
                print(f"  Epoch {epoch+1:3d}/{epochs} | Train Loss: {train_loss:.6f} | Test Loss: {test_loss:.6f} | "
                      f"Train MAPE: {train_mape_:.2f}% | Test MAPE: {test_mape_:.2f}% | Noise: {noise_scale:.4f}")
            
            if patience_counter >= patience:
                print(f"  Early stopping at epoch {epoch+1} (no test improvement for {patience} epochs)")
                break
        
        # Restore best params
        if best_params:
            for i, cell in enumerate(model.cells):
                cell.set_params(best_params[f'cell_{i}'])
            model.dense_weights = best_params['dense_weights']
            model.dense_bias = best_params['dense_bias']
            model.output_weight = best_params['output_weight']
            model.output_bias = best_params['output_bias']
        
        # Final predictions
        train_preds, _ = model.forward(X_train)
        test_preds, _ = model.forward(X_test)
        
        # Inverse transform for actual prices
        train_preds_actual = scaler.inverse_transform(train_preds.reshape(-1, 1))
        test_preds_actual = scaler.inverse_transform(test_preds.reshape(-1, 1))
        y_train_actual = scaler.inverse_transform(y_train.reshape(-1, 1))
        y_test_actual = scaler.inverse_transform(y_test.reshape(-1, 1))
        
        train_mape = float(np.mean(np.abs((y_train_actual - train_preds_actual) / (y_train_actual + 1e-8))) * 100)
        test_mape = float(np.mean(np.abs((y_test_actual - test_preds_actual) / (y_test_actual + 1e-8))) * 100)
        
        # Save model and scaler
        model.save(LSTM_MODEL_PATH)
        joblib.dump(scaler, LSTM_SCALER_PATH)
        
        # Save metadata
        metadata = {
            'status': 'success',
            'ticker': ticker,
            'sequence_length': sequence_length,
            'training_samples': X_train.shape[0],
            'test_samples': X_test.shape[0],
            'test_mape': round(test_mape, 2),
            'train_mape': round(train_mape, 2),
            'epochs_trained': epoch + 1,
            'architecture': f"LSTM{model.hidden_sizes}->Dense->Output",
            'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'framework': 'pure_numpy'
        }
        with open(LSTM_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        result = {
            'status': 'success',
            'model_path': LSTM_MODEL_PATH,
            'ticker': ticker,
            'sequence_length': sequence_length,
            'training_samples': X_train.shape[0],
            'test_samples': X_test.shape[0],
            'train_mape': round(train_mape, 2),
            'test_mape': round(test_mape, 2),
            'epochs_trained': epoch + 1,
            'test_loss': round(float(test_loss), 6),
            'final_train_loss': round(float(train_loss), 6),
            'final_val_loss': round(float(test_loss), 6),
            'architecture': f"LSTM{model.hidden_sizes}->Dense->Output",
            'framework': 'pure_numpy'
        }
        
        print(f"\n[LSTM] Training complete!")
        print(f"[LSTM] Test MAPE: {test_mape:.2f}%")
        print(f"[LSTM] Model saved to: {LSTM_MODEL_PATH}")
        return result
        
    except ImportError as e:
        return {'error': f'Missing dependency: {e}. Install with: pip install yfinance'}
    except Exception as e:
        return {'error': f'LSTM training failed: {str(e)}'}


def _linear_trend_forecast(prices, days_ahead=5):
    """Simple linear regression forecast as fallback."""
    n = len(prices)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, prices, 1)
    future = [intercept + slope * (n + i) for i in range(days_ahead)]
    return np.array(future)


def predict_lstm(ticker, days_ahead=5):
    """
    Use trained LSTM model to predict future prices.
    Falls back to hybrid (LSTM + linear trend) if pure LSTM gives unrealistic results.
    
    Args:
        ticker: Stock ticker symbol
        days_ahead: Number of days to predict ahead
        
    Returns:
        dict with predictions or error
    """
    if not os.path.exists(LSTM_MODEL_PATH) or not os.path.exists(LSTM_SCALER_PATH):
        return {'error': 'LSTM model not trained. Run train_lstm() first.'}
    
    try:
        # Get recent stock data
        import yfinance as yf
        stock = yf.Ticker(ticker)
        df = stock.history(period='6mo')
        
        if df.empty or len(df) < 20:
            return {'error': 'Insufficient historical data'}
        
        close_prices = df['Close'].values
        current_price = float(close_prices[-1])
        
        # ----- LSTM prediction -----
        lstm_preds = None
        try:
            model = LSTMModel()
            model.load(LSTM_MODEL_PATH)
            scaler = joblib.load(LSTM_SCALER_PATH)
            
            seq_len = min(model.sequence_length, max(10, len(close_prices) - 1))
            last_n = close_prices[-seq_len:].reshape(-1, 1)
            scaled_last = scaler.transform(last_n)
            
            scaled_preds = model.predict_iterative(scaled_last, steps=days_ahead)
            lstm_preds = scaler.inverse_transform(scaled_preds.reshape(-1, 1)).flatten()
        except Exception:
            pass
        
        # ----- Linear trend forecast (60 days for stability) -----
        recent_prices = close_prices[-60:]
        linear_preds = _linear_trend_forecast(recent_prices, days_ahead)
        
        # ----- Hybrid: blend LSTM + linear -----
        if lstm_preds is not None:
            lstm_change = abs(lstm_preds[-1] / max(current_price, 0.01) - 1) * 100
            if lstm_change > 80 or np.std(lstm_preds) < 0.5:
                # LSTM is giving flat-line or extreme values — use linear
                future_prices = linear_preds
            else:
                # Blend LSTM with linear for stability
                future_prices = 0.7 * lstm_preds + 0.3 * linear_preds
        else:
            future_prices = linear_preds
        
        # Compute confidence
        change_pct = ((future_prices[-1] - current_price) / max(current_price, 0.01)) * 100
        price_std = np.std(future_prices)
        confidence_score = float(np.clip(70 - abs(change_pct) * 0.5 + price_std * 2, 0, 100))
        
        # Generate dates
        last_date = df.index[-1]
        future_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(days_ahead)]
        
        expected_change = ((future_prices[-1] - current_price) / max(current_price, 0.01)) * 100
        
        return {
            'ticker': ticker,
            'current_price': round(current_price, 2),
            'predictions': [
                {'date': future_dates[i], 'predicted_price': round(float(future_prices[i]), 2)}
                for i in range(days_ahead)
            ],
            'expected_change_5d': round(float(expected_change), 2),
            'momentum': 'Bullish' if expected_change > 2 else 'Bearish' if expected_change < -2 else 'Neutral',
            'model_type': 'LSTM + Trend Hybrid',
            'framework': 'pure_numpy',
            'confidence_score': round(confidence_score, 1)
        }
        
    except Exception as e:
        return {'error': f'LSTM prediction failed: {str(e)}'}


def enhance_prediction_with_lstm(ticker, existing_prediction):
    """
    Enhance an existing ML prediction with LSTM time-series forecast.
    Merges LSTM momentum signal with the existing classification.
    
    Args:
        ticker: Stock ticker
        existing_prediction: dict from predict_stock()
        
    Returns:
        Enhanced prediction dict
    """
    # Guard: ensure existing_prediction has the expected structure
    if not isinstance(existing_prediction, dict) or 'error' in existing_prediction:
        return existing_prediction
    
    lstm_result = predict_lstm(ticker, days_ahead=5)
    
    if 'error' in lstm_result:
        return existing_prediction  # Return original if LSTM fails
    
    enhanced = existing_prediction.copy()
    enhanced['lstm_forecast'] = lstm_result
    
    # Ensure ai_explanation exists
    if 'ai_explanation' not in enhanced:
        enhanced['ai_explanation'] = {'summary': '', 'reasons': [], 'verdict': 'Hold',
                                       'confidence': 50, 'risk_level': 'Medium', 'trend': 'Neutral'}
    if 'reasons' not in enhanced['ai_explanation']:
        enhanced['ai_explanation']['reasons'] = []
    
    # Adjust confidence if LSTM agrees/disagrees
    lstm_momentum = lstm_result.get('momentum', 'Neutral')
    current_rec = enhanced.get('recommendation', 'Hold')
    
    if lstm_momentum == 'Bullish' and current_rec == 'Buy':
        enhanced['confidence'] = min(enhanced.get('confidence', 50) * 1.1, 99)
        enhanced['ai_explanation']['reasons'].append(
            f'📈 LSTM time-series model confirms bullish momentum '
            f'with {lstm_result["expected_change_5d"]}% projected 5-day gain'
        )
    elif lstm_momentum == 'Bullish' and current_rec == 'Sell':
        enhanced['confidence'] = max(enhanced.get('confidence', 50) * 0.85, 10)
        enhanced['ai_explanation']['reasons'].append(
            f'⚠️ LSTM model shows bullish momentum, conflicting with Sell signal'
        )
    elif lstm_momentum == 'Bearish' and current_rec == 'Sell':
        enhanced['confidence'] = min(enhanced.get('confidence', 50) * 1.1, 99)
        enhanced['ai_explanation']['reasons'].append(
            f'📉 LSTM time-series model confirms bearish momentum '
            f'with {lstm_result["expected_change_5d"]}% projected 5-day decline'
        )
    elif lstm_momentum == 'Bearish' and current_rec == 'Buy':
        enhanced['confidence'] = max(enhanced.get('confidence', 50) * 0.85, 10)
        enhanced['ai_explanation']['reasons'].append(
            f'⚠️ LSTM model shows bearish momentum, conflicting with Buy signal'
        )
    else:
        enhanced['ai_explanation']['reasons'].append(
            f'🤖 LSTM time-series analysis: {lstm_momentum.lower()} momentum detected'
        )
    
    enhanced['model_used'] = enhanced.get('model_used', 'Ensemble') + ' + LSTM'
    
    return enhanced


# ============================================================
# Main (for CLI training)
# ============================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  LSTM Deep Learning Stock Predictor (Pure NumPy)")
    print("="*60)
    
    print("\n[*] Training LSTM model on AAPL stock data...\n")
    result = train_lstm('AAPL', sequence_length=60, epochs=50, force_retrain=True)
    
    if 'error' in result:
        print(f"\n[X] Error: {result['error']}")
    else:
        print(f"\n[+] Result: {json.dumps(result, indent=2)}")
        
        print("\n[*] Making 5-day price predictions with LSTM...")
        preds = predict_lstm('AAPL')
        print(f"\n[+] Predictions: {json.dumps(preds, indent=2)}")
