import re
import bcrypt
from functools import wraps
from flask import session, redirect, url_for, flash, request
from users_db import get_client_by_email, update_last_login

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'client_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def create_session(client):
    session.clear()
    session['client_id'] = client['client_id']
    session['full_name'] = client['full_name']
    session['email'] = client['email']
    session['company_name'] = client.get('company_name', '')
    session.permanent = True
    update_last_login(client['client_id'])

def destroy_session():
    session.clear()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    if len(password) < 6:
        return False, 'Password must be at least 6 characters long.'
    return True, ''

def validate_name(name):
    name = name.strip()
    if len(name) < 2:
        return False, 'Name must be at least 2 characters long.'
    if len(name) > 100:
        return False, 'Name is too long.'
    return True, ''

def validate_company(company):
    company = company.strip()
    if len(company) > 200:
        return False, 'Company name is too long.'
    return True, ''

def sanitize_input(text):
    if text:
        return text.strip()
    return ''
