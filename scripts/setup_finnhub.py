"""
Finnhub API Key Setup Script
==============================
This script helps you set up the Finnhub API key for stock data and news.

Steps:
  1. Get a free API key at: https://finnhub.io/register
  2. Free tier: 60 API requests per minute (enough for most use cases)
  3. Run this script to save your key in the .env file

Usage:
    python scripts/setup_finnhub.py

Or set the environment variable manually:
    FINNHUB_API_KEY=your_api_key_here
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')


def main():
    print("=" * 60)
    print("  Finnhub API Key Setup")
    print("  Your Primary Stock & News Data Source")
    print("=" * 60)
    
    existing_key = os.environ.get('FINNHUB_API_KEY', '').strip()
    
    if existing_key and len(existing_key) > 5:
        print(f"\n[OK] FINNHUB_API_KEY is already set in environment:")
        print(f"     {existing_key[:8]}...{existing_key[-4:]}")
        print("\n  Note: This key is used for:")
        print("  - Stock price data (candles)")
        print("  - Real-time quotes")
        print("  - Company profiles")
        print("  - Financial metrics")
        print("  - News articles & sentiment analysis")
        print("\n  Fallback: Twelve Data API (if configured) or yfinance")
    
    print("\n" + "-" * 60)
    print("  To get your free Finnhub API key:")
    print("  1. Go to: https://finnhub.io/register")
    print("  2. Sign up for a free account")
    print("  3. Copy your API key from the dashboard")
    print("\n  Free tier limits: 60 requests/minute")
    print("  That's enough for ~1,000 stock data fetches per day")
    print("-" * 60)
    
    key = input("\n  Enter your Finnhub API key: ").strip()
    
    if not key or len(key) < 5:
        print("\n[X] No valid key entered. Skipping.")
        print("  You can set it later in your .env file:")
        print(f"  FINNHUB_API_KEY=your_api_key_here")
        return
    
    # Save to .env file
    try:
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, 'r') as f:
                content = f.read()
            
            if 'FINNHUB_API_KEY=' in content:
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith('FINNHUB_API_KEY='):
                        new_lines.append(f'FINNHUB_API_KEY={key}')
                    else:
                        new_lines.append(line)
                content = '\n'.join(new_lines)
                
                with open(ENV_PATH, 'w') as f:
                    f.write(content)
                print(f"\n[OK] Updated FINNHUB_API_KEY in {ENV_PATH}")
            else:
                with open(ENV_PATH, 'a') as f:
                    f.write(f'\n# Finnhub API Key (primary stock data & news source)\nFINNHUB_API_KEY={key}\n')
                print(f"\n[OK] Added FINNHUB_API_KEY to {ENV_PATH}")
        else:
            with open(ENV_PATH, 'w') as f:
                f.write(f'# Finnhub API Key (primary stock data & news source)\nFINNHUB_API_KEY={key}\n')
            print(f"\n[OK] Created {ENV_PATH} with FINNHUB_API_KEY")
        
        print(f"\n  Key saved: {key[:8]}...{key[-4:]}")
        print("\n  Finnhub is now your PRIMARY stock data source.")
        print("  Twelve Data API (if configured) serves as fallback.")
        
    except Exception as e:
        print(f"\n[X] Error saving to .env: {e}")
        print(f"\n  Please manually add this to your .env file:")
        print(f"  FINNHUB_API_KEY={key}")


if __name__ == '__main__':
    main()
