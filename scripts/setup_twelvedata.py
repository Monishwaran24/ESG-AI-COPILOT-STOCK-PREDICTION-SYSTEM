"""
Twelve Data API - Setup Helper
==============================
Guides you through signing up and configuring the Twelve Data API key.

Twelve Data provides 800 free API requests/day for Indian stock data.
No credit card needed for the free tier.

Usage:
  python scripts/setup_twelvedata.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load .env from project root
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)


def main():
    print("\n" + "="*60)
    print("  Twelve Data API - Setup Helper")
    print("="*60)

    # Check if key already exists
    existing_key = os.environ.get('TWELVEDATA_API_KEY', '').strip()
    if existing_key:
        print(f"\n[OK] TWELVEDATA_API_KEY is already set:")
        print(f"    {existing_key[:8]}...{existing_key[-4:]}")
        print("\n    Indian stock data will use Twelve Data API as primary source.")
        print("    No further setup needed.")
        return

    print("\n  Twelve Data is the PRIMARY data source for Indian stocks.")
    print("  Free tier: 800 API requests/day — sufficient for personal use.")
    print("  If not configured, the system falls back to yfinance.\n")

    print("-"*60)
    print("  STEP 1: Sign up for a free API key")
    print("-"*60)
    print("\n  1. Go to: https://twelvedata.com/")
    print("  2. Click 'Sign Up' or 'Get Free API Key'")
    print("  3. Enter your email and create an account")
    print("  4. Verify your email")
    print("  5. Your API key will be shown on the dashboard\n")

    print("-"*60)
    print("  STEP 2: Add the API key to .env")
    print("-"*60)
    print("\n  1. Open the .env file in the project root")
    print("  2. Add your key (replace the placeholder):")
    print("\n     TWELVEDATA_API_KEY=your_actual_api_key_here\n")
    print("  3. Restart the Flask app")
    print("  4. Indian stocks will now use Twelve Data as primary source\n")

    print("-"*60)
    print("  STEP 3: Verify it's working")
    print("-"*60)
    print("\n  Run this script again to verify your key was set correctly.")
    print("  Or check the Flask app logs for:")
    print("    '[TDAPI] Twelve Data client initialized'\n")

    # Prompt to optionally enter key now
    key = input("  Have your API key ready? Paste it here (or press Enter to skip): ").strip()
    if key:
        # Write to .env
        try:
            with open(dotenv_path, 'r') as f:
                content = f.read()

            if 'TWELVEDATA_API_KEY=' in content:
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith('TWELVEDATA_API_KEY='):
                        new_lines.append(f'TWELVEDATA_API_KEY={key}')
                    else:
                        new_lines.append(line)
                content = '\n'.join(new_lines)
            else:
                content += f'\nTWELVEDATA_API_KEY={key}\n'

            with open(dotenv_path, 'w') as f:
                f.write(content)

            print(f"\n[✅] API key saved to .env!")
            print(f"    Key: {key[:8]}...{key[-4:]}")
            print(f"\n    Restart the Flask app to start using Twelve Data API.")
        except Exception as e:
            print(f"\n[❌] Error saving to .env: {e}")
            print("    Please add the key manually to the .env file.")
    else:
        print("\n  No problem! You can add the key later whenever ready.")


if __name__ == '__main__':
    main()
