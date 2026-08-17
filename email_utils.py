"""
Email Utilities Module
======================
Sends emails via SMTP (Gmail App Password recommended).
Configure via .env file:
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=your.email@gmail.com
    SMTP_PASSWORD=your-16-char-app-password
    MAIL_FROM=your.email@gmail.com
    MAIL_FROM_NAME=ESG Stock Prediction
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional


def get_smtp_config():
    """Get SMTP configuration from environment variables."""
    return {
        'server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'port': int(os.environ.get('SMTP_PORT', 587)),
        'username': os.environ.get('SMTP_USERNAME', ''),
        'password': os.environ.get('SMTP_PASSWORD', ''),
        'from_addr': os.environ.get('MAIL_FROM', os.environ.get('SMTP_USERNAME', '')),
        'from_name': os.environ.get('MAIL_FROM_NAME', 'ESG Stock Prediction'),
    }


def is_email_configured():
    """Check if email SMTP is properly configured."""
    config = get_smtp_config()
    return bool(config['username'] and config['password'] and '@' in config['username'])


def send_email(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> tuple:
    """
    Send an email via SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML content of the email
        text_body: Plain text fallback (auto-generated from HTML if not provided)

    Returns:
        Tuple of (success: bool, message: str)
    """
    config = get_smtp_config()

    if not config['username'] or not config['password']:
        return False, "SMTP not configured. Set SMTP_USERNAME and SMTP_PASSWORD in .env"

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{config['from_name']} <{config['from_addr']}>"
    msg['To'] = to_email

    # Plain text fallback
    if text_body is None:
        import re
        text_body = re.sub(r'<[^>]+>', '', html_body)
        text_body = re.sub(r'\n\s*\n', '\n\n', text_body).strip()

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config['server'], config['port'], timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(config['username'], config['password'])
            server.sendmail(config['from_addr'], [to_email], msg.as_string())
        return True, "Email sent successfully"
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Check your email/password. For Gmail, use an App Password (16 chars, no spaces)."
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def send_verification_email(to_email: str, full_name: str, verification_url: str) -> tuple:
    """
    Send email verification link to a new user.

    Args:
        to_email: Recipient email
        full_name: User's full name
        verification_url: Full URL to the verification endpoint

    Returns:
        Tuple of (success: bool, message: str)
    """
    subject = "Verify your email - ESG Stock Prediction"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #0a1929;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <div style="font-size: 48px; margin-bottom: 10px;">📈</div>
                <h1 style="color: #ffffff; font-size: 24px; margin: 0;">ESG Stock Prediction</h1>
            </div>

            <div style="background: linear-gradient(135deg, #132f4c 0%, #0d2137 100%); border-radius: 16px; padding: 40px; border: 1px solid rgba(27, 94, 32, 0.3);">
                <h2 style="color: #ffffff; font-size: 22px; margin: 0 0 16px 0;">
                    Hi {full_name}! 👋
                </h2>
                <p style="color: #b0bec5; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
                    Thanks for signing up! Please verify your email address by clicking the button below.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a href="{verification_url}"
                       style="display: inline-block; padding: 14px 36px; background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 100%);
                              color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 600;
                              box-shadow: 0 4px 15px rgba(27, 94, 32, 0.4);">
                        Verify Email Address
                    </a>
                </div>

                <p style="color: #78909c; font-size: 14px; line-height: 1.5; margin: 0 0 8px 0;">
                    Or copy this link into your browser:
                </p>
                <p style="color: #4caf50; font-size: 13px; word-break: break-all; margin: 0;">
                    {verification_url}
                </p>

                <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 28px 0;">

                <p style="color: #78909c; font-size: 13px; line-height: 1.5; margin: 0;">
                    This link expires in 24 hours. If you didn't create an account, you can ignore this email.
                </p>
            </div>

            <div style="text-align: center; margin-top: 24px;">
                <p style="color: #546e7a; font-size: 12px; margin: 0;">
                    ESG Stock Prediction System &bull; AI-Powered Analysis
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(to_email, subject, html)


def send_password_reset_email(to_email: str, full_name: str, otp: str) -> tuple:
    """
    Send password reset OTP email.

    Args:
        to_email: Recipient email
        full_name: User's full name
        otp: 6-digit OTP code

    Returns:
        Tuple of (success: bool, message: str)
    """
    subject = "Password Reset - ESG Stock Prediction"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #0a1929;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <div style="font-size: 48px; margin-bottom: 10px;">🔐</div>
                <h1 style="color: #ffffff; font-size: 24px; margin: 0;">ESG Stock Prediction</h1>
            </div>

            <div style="background: linear-gradient(135deg, #132f4c 0%, #0d2137 100%); border-radius: 16px; padding: 40px; border: 1px solid rgba(27, 94, 32, 0.3);">
                <h2 style="color: #ffffff; font-size: 22px; margin: 0 0 16px 0;">
                    Password Reset Request
                </h2>
                <p style="color: #b0bec5; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
                    Hi {full_name}, we received a request to reset your password. Use the OTP below:
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <div style="display: inline-block; padding: 16px 40px; background: rgba(27, 94, 32, 0.2); border-radius: 12px;
                                border: 2px dashed #1b5e20; font-size: 36px; font-weight: 700; color: #4caf50;
                                letter-spacing: 8px; font-family: 'Courier New', monospace;">
                        {otp}
                    </div>
                </div>

                <p style="color: #78909c; font-size: 14px; line-height: 1.5; margin: 0;">
                    This OTP expires in 15 minutes. If you didn't request this, you can ignore this email.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(to_email, subject, html)
