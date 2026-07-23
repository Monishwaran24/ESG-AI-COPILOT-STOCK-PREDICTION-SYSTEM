import os
import sqlite3
import json
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'esg_stock.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company TEXT,
            industry TEXT,
            recommendation TEXT NOT NULL,
            confidence REAL,
            confidence_scores TEXT,
            current_price REAL,
            price_change_pct REAL,
            trend TEXT,
            risk_level TEXT,
            esg_score REAL,
            model_used TEXT,
            model_accuracy REAL,
            ai_summary TEXT,
            is_simulated INTEGER DEFAULT 0,
            prediction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS watched_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alert_enabled INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 1 REFERENCES users(id),
            UNIQUE(ticker, user_id)
        );

        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL DEFAULT 0,
            buy_price REAL NOT NULL DEFAULT 0,
            user_id INTEGER DEFAULT 1 REFERENCES users(id),
            UNIQUE(ticker, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_predictions_ticker ON predictions(ticker);
        CREATE INDEX IF NOT EXISTS idx_predictions_time ON predictions(prediction_time DESC);
        CREATE INDEX IF NOT EXISTS idx_predictions_recommendation ON predictions(recommendation);
    ''')

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, display_name) VALUES (?, ?)",
                       ('default', 'Default User'))

    conn.commit()
    conn.close()

def save_prediction(data):
    conn = get_connection()
    cursor = conn.cursor()

    confidence_scores = data.get('confidence_scores', {})
    if isinstance(confidence_scores, dict):
        confidence_scores = json.dumps(confidence_scores)

    esg = data.get('esg_data', {})
    ai = data.get('ai_explanation', {})

    cursor.execute('''
        INSERT INTO predictions (
            ticker, company, industry, recommendation, confidence,
            confidence_scores, current_price, price_change_pct,
            trend, risk_level, esg_score, model_used, model_accuracy,
            ai_summary, is_simulated, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('ticker', '').upper(),
        data.get('company', ''),
        data.get('industry', ''),
        data.get('recommendation', ''),
        data.get('confidence', 0.0),
        confidence_scores,
        data.get('current_price', 0.0),
        data.get('price_change_pct', 0.0),
        data.get('trend', ''),
        data.get('risk_level', ''),
        esg.get('esg_score', 0.0),
        data.get('model_used', ''),
        data.get('model_accuracy', 0.0),
        ai.get('summary', ''),
        1 if data.get('is_simulated') else 0,
        1
    ))

    prediction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return prediction_id

def get_prediction_history(limit=50, offset=0, ticker=None):
    conn = get_connection()
    cursor = conn.cursor()

    if ticker:
        cursor.execute('''
            SELECT * FROM predictions
            WHERE ticker = ?
            ORDER BY prediction_time DESC
            LIMIT ? OFFSET ?
        ''', (ticker.upper(), limit, offset))
    else:
        cursor.execute('''
            SELECT * FROM predictions
            ORDER BY prediction_time DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_prediction_by_id(prediction_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_recent_predictions_for_ticker(ticker, limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM predictions
        WHERE ticker = ?
        ORDER BY prediction_time DESC
        LIMIT ?
    ''', (ticker.upper(), limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_prediction_stats():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM predictions")
    total = cursor.fetchone()[0]

    cursor.execute('''
        SELECT recommendation, COUNT(*) as count
        FROM predictions GROUP BY recommendation
    ''')
    by_rec = {r['recommendation']: r['count'] for r in cursor.fetchall()}

    cursor.execute('''
        SELECT ticker, COUNT(*) as count
        FROM predictions GROUP BY ticker
        ORDER BY count DESC LIMIT 5
    ''')
    top_stocks = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
        SELECT prediction_time FROM predictions
        ORDER BY prediction_time DESC LIMIT 1
    ''')
    last = cursor.fetchone()

    conn.close()
    return {
        'total_predictions': total,
        'by_recommendation': by_rec,
        'top_stocks': top_stocks,
        'last_prediction': dict(last)['prediction_time'] if last else None
    }

def add_watched_stock(ticker):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO watched_stocks (ticker, user_id)
            VALUES (?, 1)
        ''', (ticker.upper(),))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def remove_watched_stock(ticker):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watched_stocks WHERE ticker = ? AND user_id = 1",
                   (ticker.upper(),))
    conn.commit()
    conn.close()

def get_watched_stocks():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ws.*, COUNT(p.id) as prediction_count,
               MAX(p.prediction_time) as last_prediction,
               p.recommendation as last_recommendation,
               p.confidence as last_confidence
        FROM watched_stocks ws
        LEFT JOIN predictions p ON ws.ticker = p.ticker
        WHERE ws.user_id = 1
        GROUP BY ws.ticker
        ORDER BY ws.added_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_tickers_in_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ticker FROM predictions ORDER BY ticker")
    rows = cursor.fetchall()
    conn.close()
    return [r['ticker'] for r in rows]

def add_portfolio_holding(ticker, shares, buy_price):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        existing = cursor.execute("SELECT id, shares FROM portfolio WHERE ticker = ? AND user_id = 1", (ticker.upper(),)).fetchone()
        if existing:
            total_shares = existing['shares'] + shares
            cursor.execute("UPDATE portfolio SET shares = ? WHERE id = ?", (total_shares, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO portfolio (ticker, shares, buy_price, user_id)
                VALUES (?, ?, ?, 1)
            ''', (ticker.upper(), shares, buy_price))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def sell_portfolio_holding(ticker, shares):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        existing = cursor.execute("SELECT id, shares FROM portfolio WHERE ticker = ? AND user_id = 1", (ticker.upper(),)).fetchone()
        if not existing or existing['shares'] < shares:
            return False
        remaining = existing['shares'] - shares
        if remaining <= 0:
            cursor.execute("DELETE FROM portfolio WHERE id = ?", (existing['id'],))
        else:
            cursor.execute("UPDATE portfolio SET shares = ? WHERE id = ?", (remaining, existing['id']))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def get_portfolio():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio WHERE user_id = 1 ORDER BY ticker")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_portfolio_summary():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count, SUM(shares) as total_shares, SUM(shares * buy_price) as total_invested FROM portfolio WHERE user_id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {'count': 0, 'total_shares': 0, 'total_invested': 0}
