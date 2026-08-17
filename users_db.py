"""
Separate User Database Module
==============================
Stores user credentials in a dedicated SQLite database (users.db),
completely isolated from the main application data (esg_stock.db).

This provides:
- Security isolation: user credentials separate from prediction data
- Easier backup/management of user accounts
- Clear separation of concerns
"""

import os
import sqlite3
from datetime import datetime, timedelta

DB_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB_PATH = os.path.join(DB_DIR, 'users.db')


def get_connection():
    """Get a connection to the users database."""
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_users_db():
    """Initialize the users database with tables for authentication."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
            client_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            company_name TEXT DEFAULT '',
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email_verified INTEGER DEFAULT 0,
            verification_token TEXT,
            verification_sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS otp_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            purpose TEXT DEFAULT 'password_reset',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_clients_email ON clients(email);
        CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_verification(email);
    ''')

    # Migration: add columns for existing databases
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN email_verified INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN verification_token TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN verification_sent_at TIMESTAMP")
        conn.commit()
    except Exception:
        pass

    conn.close()


# ============================================================
# User Account Functions
# ============================================================

def create_client(full_name, company_name, email, password_hash):
    """Create a new user account in the users database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO clients (full_name, company_name, email, password_hash)
            VALUES (?, ?, ?, ?)
        ''', (full_name.strip(), company_name.strip(), email.strip().lower(), password_hash))
        conn.commit()
        client_id = cursor.lastrowid
        return client_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_client_by_email(email):
    """Look up a user by email in the users database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_client_by_id(client_id):
    """Look up a user by ID in the users database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_last_login(client_id):
    """Update the last login timestamp for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clients SET last_login = CURRENT_TIMESTAMP WHERE client_id = ?", (client_id,))
    conn.commit()
    conn.close()


def update_password(email, new_password_hash):
    """Update a user's password hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clients SET password_hash = ? WHERE email = ?",
                   (new_password_hash, email.strip().lower()))
    conn.commit()
    conn.close()


# ============================================================
# Email Verification Functions
# ============================================================

def set_verification_token(client_id, token):
    """Store email verification token for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE clients SET verification_token = ?, verification_sent_at = CURRENT_TIMESTAMP
        WHERE client_id = ?
    ''', (token, client_id))
    conn.commit()
    conn.close()


def verify_email_token(token):
    """
    Verify a user by their email verification token.
    Token expires after 24 hours.
    Returns: (success, message)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT client_id, email, email_verified, verification_sent_at
        FROM clients WHERE verification_token = ?
    ''', (token,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False, 'Invalid or expired verification link.'

    if row['email_verified'] == 1:
        conn.close()
        return False, 'Email is already verified.'

    # Check if token is expired (24 hours)
    from datetime import datetime, timedelta
    sent_at = row['verification_sent_at']
    if sent_at:
        sent_dt = datetime.strptime(sent_at, '%Y-%m-%d %H:%M:%S') if isinstance(sent_at, str) else sent_at
        if datetime.now() - sent_dt > timedelta(hours=24):
            conn.close()
            return False, 'Verification link has expired. Please request a new one.'

    # Mark as verified
    cursor.execute('''
        UPDATE clients SET email_verified = 1, verification_token = NULL
        WHERE client_id = ?
    ''', (row['client_id'],))
    conn.commit()
    conn.close()
    return True, 'Email verified successfully! You can now log in.'


def is_email_verified(email):
    """Check if a user's email is verified."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email_verified FROM clients WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['email_verified'] == 1
    return False


def resend_verification(email):
    """Get a new verification token for an unverified user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT client_id, email_verified FROM clients WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    if row['email_verified'] == 1:
        return None
    return row['client_id']


# ============================================================
# OTP Functions (for password reset)
# ============================================================

def save_otp(email, otp, purpose='password_reset', expiry_minutes=15):
    """Save an OTP for password reset verification."""
    conn = get_connection()
    cursor = conn.cursor()
    expires_at = datetime.now() + timedelta(minutes=expiry_minutes)
    cursor.execute('''
        INSERT INTO otp_verification (email, otp, purpose, expires_at)
        VALUES (?, ?, ?, ?)
    ''', (email.strip().lower(), otp, purpose, expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def verify_otp(email, otp, purpose='password_reset'):
    """Verify an OTP code for password reset."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM otp_verification
        WHERE email = ? AND otp = ? AND purpose = ? AND used = 0
        AND expires_at > datetime('now')
        ORDER BY created_at DESC LIMIT 1
    ''', (email.strip().lower(), otp, purpose))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE otp_verification SET used = 1 WHERE id = ?", (row['id'],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


# ============================================================
# Migration: Copy existing users from esg_stock.db to users.db
# ============================================================

def migrate_existing_users():
    """Migrate existing user accounts from the main database to the users database."""
    try:
        from database import get_connection as get_main_conn
        main_conn = get_main_conn()
        main_cur = main_conn.cursor()
        main_cur.execute("SELECT * FROM clients")
        existing_users = main_cur.fetchall()
        main_conn.close()

        if not existing_users:
            return {'migrated': 0, 'message': 'No existing users to migrate'}

        count = 0
        conn = get_connection()
        cur = conn.cursor()
        for user in existing_users:
            try:
                cur.execute('''
                    INSERT OR IGNORE INTO clients (client_id, full_name, company_name, email, password_hash, email_verified, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ''', (
                    user['client_id'], user['full_name'], user['company_name'],
                    user['email'], user['password_hash'], user['created_at'], user['last_login']
                ))
                if cur.rowcount > 0:
                    count += 1
            except Exception:
                pass
        conn.commit()

        # Fix existing migrated users who may have email_verified=0 (from before the fix)
        cur.execute("UPDATE clients SET email_verified = 1 WHERE email_verified = 0 AND verification_token IS NULL")
        conn.commit()

        conn.close()
        return {'migrated': count, 'message': f'Migrated {count} user(s)'}
    except Exception as e:
        return {'migrated': 0, 'message': f'Migration error: {str(e)}'}


# ============================================================
# Initialize the database on import
# ============================================================

init_users_db()
