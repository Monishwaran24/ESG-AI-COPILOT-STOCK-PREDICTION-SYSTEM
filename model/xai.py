"""
Explainable AI (XAI) module for ESG Stock Prediction.
Uses SHAP (SHapley Additive exPlanations) for model interpretability.
Provides feature-grouped explanations for stock predictions.
"""

import os, sys, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from model.predict import (
    load_model, get_stock_data, calculate_indicators, get_esg_data,
    feature_cols, BASE_FEATURES, determine_trend, determine_risk_level,
    get_market, get_currency_symbol
)

# ---------------------------------------------------------------------------
# Feature Grouping
# ---------------------------------------------------------------------------
# Maps raw feature names to human-readable categories for explanation
FEATURE_GROUPS = {
    'ESG Score': {
        'features': ['ESG_Score', 'Environmental_Score', 'Social_Score', 'Governance_Score'],
        'icon': 'leaf',
        'description': 'Environmental, Social, and Governance metrics'
    },
    'Price Momentum': {
        'features': ['Price_Momentum', 'Price_Acceleration', 'Price_Change_1d',
                     'Price_Change_5d', 'Price_Change_20d',
                     'Log_Return_1d', 'Log_Return_5d', 'Log_Return_20d'],
        'icon': 'trending-up',
        'description': 'Short and long-term price trends and acceleration'
    },
    'Technical Indicators': {
        'features': ['RSI_14', 'MACD', 'MACD_Signal', 'MACD_Histogram',
                     'SMA_10', 'SMA_30', 'EMA_10', 'EMA_30',
                     'BB_Width', 'BB_Position', 'Price_Position',
                     'Close_Open_Ratio'],
        'icon': 'bar-chart',
        'description': 'RSI, MACD, Bollinger Bands, and other technical signals'
    },
    'Volatility & Risk': {
        'features': ['Volatility_10d', 'ATR_14', 'High_Low_Ratio',
                     'High_Low_Pct', 'STOCH_K', 'STOCH_D', 'WILLIAMS_R'],
        'icon': 'activity',
        'description': 'Price volatility, risk metrics, and stochastic oscillators'
    },
    'Volume & Money Flow': {
        'features': ['Volume_Ratio', 'Volume_Change_1d', 'VPT_Change',
                     'MFI', 'RSI_SMA'],
        'icon': 'dollar-sign',
        'description': 'Trading volume analysis and money flow indicators'
    },
}

# Use all features (67) to match the trained model
ALL_FEATURES = feature_cols


def _get_feature_group(feature_name):
    """Get the human-readable group name for a feature."""
    for group_name, group_info in FEATURE_GROUPS.items():
        if feature_name in group_info['features']:
            return group_name
    return 'Other Factors'


def _get_feature_direction(feature_name, value, recommendation):
    """Determine if a feature value is contributing positively or negatively."""
    if feature_name == 'RSI_14':
        if value < 30:
            return 'positive' if recommendation == 'Buy' else 'negative'
        elif value > 70:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if feature_name in ('MACD', 'MACD_Histogram'):
        if value > 0:
            return 'positive' if recommendation == 'Buy' else 'negative'
        else:
            return 'positive' if recommendation == 'Sell' else 'negative'
    if feature_name == 'Volume_Ratio':
        if value > 1.2:
            return 'positive'
        return 'neutral'
    if 'Momentum' in feature_name or 'Return' in feature_name or 'Change' in feature_name:
        if value > 0:
            return 'positive' if recommendation == 'Buy' else 'negative'
        else:
            return 'positive' if recommendation == 'Sell' else 'negative'
    if feature_name in ('Volatility_10d', 'ATR_14'):
        if value > 0.03:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if 'ESG' in feature_name or 'Environmental' in feature_name or 'Social' in feature_name or 'Governance' in feature_name:
        if value > 65:
            return 'positive' if recommendation == 'Buy' else 'negative'
        elif value < 45:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if feature_name in ('STOCH_K', 'STOCH_D'):
        if value < 20:
            return 'positive' if recommendation == 'Buy' else 'negative'
        elif value > 80:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if feature_name == 'WILLIAMS_R':
        if value < -80:
            return 'positive' if recommendation == 'Buy' else 'negative'
        elif value > -20:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if feature_name == 'MFI':
        if value < 20:
            return 'positive' if recommendation == 'Buy' else 'negative'
        elif value > 80:
            return 'positive' if recommendation == 'Sell' else 'negative'
        return 'neutral'
    if value > 0:
        return 'positive' if recommendation == 'Buy' else 'negative'
    elif value < 0:
        return 'positive' if recommendation == 'Sell' else 'negative'
    return 'neutral'


def compute_shap_explanation(feature_vector_scaled, feature_vector_raw,
                              predicted_class, recommendation):
    """
    Compute SHAP-based explanations for a prediction.
    Uses SHAP TreeExplainer for XGBoost models.
    Handles both 2D output (binary) and 3D output (multiclass) shapes.
    """
    model, scaler, label_encoder, metadata = load_model()
    if model is None:
        return {'shap_available': False, 'contributions': [], 'method': 'none'}

    try:
        import shap

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(feature_vector_scaled)

        # shap_values shapes:
        # - List of arrays (one per class): XGBoost multiclass older API
        # - 2D array (n_samples, n_features): binary/regression
        # - 3D array (n_samples, n_features, n_classes): newer API for multiclass
        class_idx = int(predicted_class)

        if isinstance(shap_values, list):
            # Old multiclass API: list of (1, n_features) arrays
            vals = shap_values[class_idx] if class_idx < len(shap_values) else shap_values[0]
            instance_shap = vals[0] if vals.ndim == 2 else vals
        elif shap_values.ndim == 3:
            # New multiclass API: (1, n_features, n_classes)
            instance_shap = shap_values[0, :, class_idx]
        elif shap_values.ndim == 2:
            # Binary/regression: (1, n_features)
            instance_shap = shap_values[0]
        else:
            instance_shap = shap_values

        # instance_shap is now a 1D array of SHAP values per feature
        n_features = min(len(ALL_FEATURES), len(instance_shap))

        group_contributions = {}
        for i in range(n_features):
            feat_name = ALL_FEATURES[i]
            shap_val = float(instance_shap[i])
            raw_val = 0.0
            if feature_vector_raw.ndim == 2 and feature_vector_raw.shape[1] > i:
                raw_val = float(feature_vector_raw[0, i])
            group = _get_feature_group(feat_name)

            if group not in group_contributions:
                gi = FEATURE_GROUPS.get(group, {})
                group_contributions[group] = {
                    'total_shap': 0.0, 'details': [],
                    'icon': gi.get('icon', 'help-circle'),
                    'description': gi.get('description', 'Other factors')
                }
            group_contributions[group]['total_shap'] += shap_val
            direction = _get_feature_direction(feat_name, raw_val, recommendation)
            group_contributions[group]['details'].append({
                'feature': feat_name,
                'shap_value': round(shap_val, 4),
                'raw_value': round(raw_val, 4),
                'direction': direction
            })

        total_abs_shap = sum(abs(g['total_shap']) for g in group_contributions.values())
        if total_abs_shap > 0:
            contributions = []
            for group_name, group_data in sorted(
                group_contributions.items(),
                key=lambda x: abs(x[1]['total_shap']),
                reverse=True
            ):
                impact_pct = round((group_data['total_shap'] / total_abs_shap) * 100, 1)
                direction = 'positive' if group_data['total_shap'] >= 0 else 'negative'
                contributions.append({
                    'factor': group_name,
                    'impact': abs(impact_pct),
                    'direction': direction,
                    'icon': group_data['icon'],
                    'description': group_data['description'],
                    'details': group_data['details'][:3]
                })
            return {
                'shap_available': True, 'method': 'SHAP (Shapley Values)',
                'contributions': contributions,
                'total_abs_shap': round(total_abs_shap, 4)
            }
        return {'shap_available': False, 'contributions': [], 'method': 'empty_shap'}

    except ImportError:
        return {'shap_available': False, 'contributions': [], 'method': 'shap_not_installed'}
    except Exception as e:
        print("[XAI] SHAP error: " + str(e))
        return {'shap_available': False, 'contributions': [], 'method': 'shap_error',
                'error': str(e)}


def compute_lime_explanation(feature_vector_scaled, feature_vector_raw,
                               predicted_class, recommendation):
    """
    Compute LIME-based explanations for a prediction.
    Uses LIME (Local Interpretable Model-agnostic Explanations) to create
    a local surrogate model around the prediction point.
    Falls back gracefully if LIME is unavailable or fails.
    """
    model, scaler, label_encoder, metadata = load_model()
    if model is None or not hasattr(model, 'predict_proba'):
        return {'lime_available': False, 'contributions': [], 'method': 'no_model'}

    try:
        from lime.lime_tabular import LimeTabularExplainer

        # Get class names from label encoder
        class_names = ['Sell', 'Hold', 'Buy']
        if label_encoder is not None and hasattr(label_encoder, 'classes_'):
            class_names = list(label_encoder.classes_)

        # Generate background dataset for LIME (StandardScaler produces ~N(0,1) features)
        np.random.seed(42)
        n_background = 200
        n_features = feature_vector_scaled.shape[1]
        background_data = np.random.randn(n_background, n_features).astype(np.float64)

        # Create LIME explainer
        explainer = LimeTabularExplainer(
            training_data=background_data,
            feature_names=ALL_FEATURES[:n_features],
            class_names=class_names,
            mode='classification',
            random_state=42
        )

        # Define prediction function for LIME (expects 2D array, returns probs)
        def predict_fn(x):
            return model.predict_proba(x)

        # Explain the instance
        instance = feature_vector_scaled[0]  # 1D array
        exp = explainer.explain_instance(
            data_row=instance,
            predict_fn=predict_fn,
            num_features=n_features,
            num_samples=500
        )

        # Get feature weights from LIME
        # exp.as_list() returns [(feature_name, weight), ...]
        lime_weights = dict(exp.as_list())

        # Also get the full feature weights with original feature names
        feature_weights = {}
        if hasattr(exp, 'local_exp'):
            # local_exp is a dict mapping class index to list of (feature_idx, weight)
            class_idx = int(predicted_class)
            if class_idx in exp.local_exp:
                for feat_idx, weight in exp.local_exp[class_idx]:
                    if feat_idx < n_features:
                        feature_weights[ALL_FEATURES[feat_idx]] = weight

        # If local_exp didn't work, try mapping from exp.as_list()
        if not feature_weights:
            for feat_name, weight in lime_weights.items():
                # Try to find the matching feature
                for cf in ALL_FEATURES:
                    if cf in feat_name or feat_name.replace(' ', '_') in cf:
                        feature_weights[cf] = weight
                        break

        # Group feature weights by category
        group_contributions = {}
        for i, feat_name in enumerate(ALL_FEATURES[:n_features]):
            weight = feature_weights.get(feat_name, 0.0)
            raw_val = 0.0
            if feature_vector_raw.ndim == 2 and feature_vector_raw.shape[1] > i:
                raw_val = float(feature_vector_raw[0, i])
            group = _get_feature_group(feat_name)

            if group not in group_contributions:
                gi = FEATURE_GROUPS.get(group, {})
                group_contributions[group] = {
                    'total_lime': 0.0, 'details': [],
                    'icon': gi.get('icon', 'help-circle'),
                    'description': gi.get('description', 'Other factors')
                }
            group_contributions[group]['total_lime'] += weight
            direction = _get_feature_direction(feat_name, raw_val, recommendation)
            group_contributions[group]['details'].append({
                'feature': feat_name,
                'lime_weight': round(weight, 4),
                'raw_value': round(raw_val, 4),
                'direction': direction
            })

        # Convert to contribution percentages
        total_abs = sum(abs(g['total_lime']) for g in group_contributions.values())
        if total_abs > 0:
            contributions = []
            for group_name, group_data in sorted(
                group_contributions.items(),
                key=lambda x: abs(x[1]['total_lime']),
                reverse=True
            ):
                impact_pct = round((group_data['total_lime'] / total_abs) * 100, 1)
                direction = 'positive' if group_data['total_lime'] >= 0 else 'negative'
                contributions.append({
                    'factor': group_name,
                    'impact': abs(impact_pct),
                    'direction': direction,
                    'icon': group_data['icon'],
                    'description': group_data['description'],
                    'details': group_data['details'][:3]
                })
            return {
                'lime_available': True, 'method': 'LIME (Local Interpretable Model-agnostic Explanations)',
                'contributions': contributions,
                'total_abs_lime': round(total_abs, 4)
            }
        return {'lime_available': False, 'contributions': [], 'method': 'empty_lime'}

    except ImportError:
        return {'lime_available': False, 'contributions': [], 'method': 'lime_not_installed'}
    except Exception as e:
        print("[XAI] LIME error: " + str(e))
        return {'lime_available': False, 'contributions': [], 'method': 'lime_error',
                'error': str(e)}


def compute_fallback_explanation(feature_vector_raw, predicted_class,
                                  recommendation, indicators):
    """
    Robust explanation when SHAP and LIME are unavailable.
    Uses model feature importance + domain heuristics.
    """
    model, scaler, label_encoder, metadata = load_model()

    feature_importances = {}
    if model and hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
        for i, feat_name in enumerate(ALL_FEATURES):
            if i < len(importances):
                feature_importances[feat_name] = float(importances[i])

    if not feature_importances:
        for feat_name in ALL_FEATURES:
            feature_importances[feat_name] = 1.0 / len(ALL_FEATURES)

    group_scores = {}
    group_details = {}
    for i, feat_name in enumerate(ALL_FEATURES):
        if i >= feature_vector_raw.shape[1]:
            break
        raw_val = float(feature_vector_raw[0, i])
        importance = feature_importances.get(feat_name, 1.0)
        direction_val = _get_feature_direction(feat_name, raw_val, recommendation)
        sign = 1.0 if direction_val == 'positive' else (-1.0 if direction_val == 'negative' else (0.5 if recommendation == 'Buy' else -0.5))
        contribution = (importance + 0.1) * sign
        group = _get_feature_group(feat_name)
        group_scores[group] = group_scores.get(group, 0.0) + contribution
        if group not in group_details:
            group_details[group] = []
        group_details[group].append({
            'feature': feat_name,
            'importance': round(importance, 4),
            'raw_value': round(raw_val, 4),
            'direction': direction_val
        })

    total_abs = sum(abs(s) for s in group_scores.values()) or 1.0
    contributions = []
    for group_name, score in sorted(
        group_scores.items(), key=lambda x: abs(x[1]), reverse=True
    ):
        impact_pct = round((abs(score) / total_abs) * 100, 1)
        direction = 'positive' if score >= 0 else 'negative'
        gi = FEATURE_GROUPS.get(group_name, {})
        contributions.append({
            'factor': group_name,
            'impact': max(impact_pct, 5.0),
            'direction': direction,
            'icon': gi.get('icon', 'help-circle'),
            'description': gi.get('description', 'Other factors'),
            'details': group_details.get(group_name, [])[:3]
        })

    # Normalize impact percentages to sum to 100%
    sum_imp = sum(c['impact'] for c in contributions) or 100.0
    for c in contributions:
        c['impact'] = round((c['impact'] / sum_imp) * 100, 1)

    return {'method': 'Feature Importance (AI Factor Analysis)', 'contributions': contributions}


def generate_xai_breakdown(ticker, prediction_result=None, method='auto'):
    """
    Generate a complete XAI breakdown for a stock prediction.

    Args:
        ticker: Stock ticker symbol
        prediction_result: Optional pre-computed prediction result
        method: Explanation method - 'shap', 'lime', or 'auto' (default: 'auto')
                'auto' tries SHAP first, then LIME, then feature importance fallback

    Returns:
        dict with full XAI explanation
    """
    try:
        if prediction_result is None:
            from model.predict import predict_stock
            prediction_result = predict_stock(ticker)
            if 'error' in prediction_result:
                return {'error': prediction_result['error']}

        recommendation = prediction_result.get('recommendation', 'Hold')
        confidence = prediction_result.get('confidence', 50)

        stock_info = get_stock_data(ticker, period='1y')
        if stock_info is None:
            return {'error': 'Unable to fetch data for ' + ticker}

        calc_result = calculate_indicators(stock_info)
        if calc_result is None:
            return {'error': 'Insufficient data for ' + ticker}

        indicators = calc_result['indicators']
        esg_data = get_esg_data(ticker)

        indicators['ESG_Score'] = esg_data['esg_score']
        indicators['Environmental_Score'] = esg_data['environmental_score']
        indicators['Social_Score'] = esg_data['social_score']
        indicators['Governance_Score'] = esg_data['governance_score']

        fv_raw = []
        for col in ALL_FEATURES:
            fv_raw.append(indicators.get(col, 0.0))
        feature_vector_raw = np.array(fv_raw).reshape(1, -1)

        model, scaler, label_encoder, metadata = load_model()
        if scaler is None:
            return {'error': 'Scaler not available'}

        feature_scaled = scaler.transform(feature_vector_raw)

        if model is not None:
            prediction = model.predict(feature_scaled)
            predicted_class = prediction[0]
        else:
            rec_map = {'Buy': 2, 'Hold': 1, 'Sell': 0}
            predicted_class = rec_map.get(recommendation, 1)

        # Determine explanation strategy based on method parameter
        use_method = (method or 'auto').lower().strip()

        if use_method == 'shap':
            # Only SHAP, no fallback to LIME
            xai_result = compute_shap_explanation(
                feature_scaled, feature_vector_raw, predicted_class, recommendation
            )
            if xai_result.get('shap_available', False):
                contributions = xai_result.get('contributions', [])
                method_name = 'SHAP (Shapley Additive Explanations)'
            else:
                contributions = []
                method_name = 'SHAP unavailable'

        elif use_method == 'lime':
            # Only LIME, no fallback to SHAP
            lime_result = compute_lime_explanation(
                feature_scaled, feature_vector_raw, predicted_class, recommendation
            )
            if lime_result.get('lime_available', False):
                contributions = lime_result.get('contributions', [])
                method_name = lime_result.get('method', 'LIME (Local Interpretable Model-agnostic Explanations)')
            else:
                contributions = []
                method_name = 'LIME unavailable'

        else:
            # 'auto' (default): Try SHAP first, then LIME, then fallback
            xai_result = compute_shap_explanation(
                feature_scaled, feature_vector_raw, predicted_class, recommendation
            )
            if xai_result.get('shap_available', False):
                contributions = xai_result.get('contributions', [])
                method_name = 'SHAP (Shapley Additive Explanations)'
            else:
                # Try LIME as second method
                lime_result = compute_lime_explanation(
                    feature_scaled, feature_vector_raw, predicted_class, recommendation
                )
                if lime_result.get('lime_available', False):
                    contributions = lime_result.get('contributions', [])
                    method_name = lime_result.get('method', 'LIME')
                else:
                    # Final fallback: feature importance
                    fallback = compute_fallback_explanation(
                        feature_vector_raw, predicted_class, recommendation, indicators
                    )
                    contributions = fallback.get('contributions', [])
                    method_name = fallback.get('method', 'none')

        summary = _generate_xai_summary(contributions, recommendation, confidence)
        price_impact = _estimate_price_impact(contributions)

        return {
            'ticker': ticker.upper(),
            'recommendation': recommendation,
            'confidence': confidence,
            'price_impact': price_impact,
            'contributions': contributions,
            'summary': summary,
            'method': method_name,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        return {'error': str(e)}


def _generate_xai_summary(contributions, recommendation, confidence):
    """Generate a human-readable summary from contributions."""
    if not contributions:
        msg = ('The model predicts **' + recommendation + '** with '
               + str(round(confidence, 1)) + '% confidence, '
               + 'but detailed factor breakdown is unavailable.')
        return msg

    top_positive = [c for c in contributions if c['direction'] == 'positive']
    top_negative = [c for c in contributions if c['direction'] == 'negative']

    parts = [
        'The AI model recommends **' + recommendation + '** with **'
        + str(round(confidence, 1)) + '%** confidence based on the following factor analysis.'
    ]

    if top_positive:
        pos_items = []
        for c in top_positive[:3]:
            pos_items.append(c['factor'] + ' (+' + str(c['impact']) + '%)')
        parts.append('Positive drivers: ' + ', '.join(pos_items) + '.')

    if top_negative:
        neg_items = []
        for c in top_negative[:3]:
            neg_items.append(c['factor'] + ' (-' + str(c['impact']) + '%)')
        parts.append('Negative factors: ' + ', '.join(neg_items) + '.')

    return ' '.join(parts)


def _estimate_price_impact(contributions):
    """Estimate the overall price impact from contributions."""
    if not contributions:
        return 0
    net_score = sum(
        c['impact'] if c['direction'] == 'positive' else -c['impact']
        for c in contributions
    )
    max_possible = sum(c['impact'] for c in contributions) or 100
    scaled = (net_score / max_possible) * 15
    return round(scaled, 1)


if __name__ == '__main__':
    print()
    print('=' * 60)
    print('  Explainable AI (XAI) - Test')
    print('=' * 60)
    test_tickers = ['AAPL', 'MSFT', 'RELIANCE']
    for ticker in test_tickers:
        print()
        print('-' * 50)
        print('  Stock: ' + ticker)
        print('-' * 50)
        r = generate_xai_breakdown(ticker)
        if 'error' in r:
            print('  Error: ' + r['error'])
            continue
        print('  Recommendation: ' + r['recommendation'])
        print('  Confidence: ' + str(round(r['confidence'], 1)) + '%')
        print('  Method: ' + r['method'])
        print('  Price Impact: ' + ('+' if r['price_impact'] >= 0 else '') + str(r['price_impact']) + '%')
        print('  Contributions:')
        for c in r['contributions']:
            sign = '+' if c['direction'] == 'positive' else '-'
            print('    ' + c['factor'].ljust(25) + ' ' + sign + str(c['impact']).rjust(5) + '%')
        print('  Summary: ' + r['summary'][:120] + '...')
