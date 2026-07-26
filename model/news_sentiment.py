"""
News Sentiment Analysis Module
================================
Fetches recent news articles for a stock via NewsAPI and performs
sentiment analysis using TextBlob (primary) or a simple keyword fallback.

NewsAPI Key: Reads from NEWS_API_KEY in .env or environment variables.
Free tier: 100 requests/day.
Completely fail-safe — if anything fails, returns neutral sentiment.
"""

import os
import json
import time
from datetime import datetime, timedelta

# Try to import TextBlob for proper sentiment analysis
try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False

# Cache for news results to avoid hitting rate limits
_news_cache = {}
_NEWS_CACHE_TTL = 1800  # 30 minutes

# Company name lookup for better NewsAPI queries
COMPANY_NAMES = {
    'AAPL': 'Apple', 'MSFT': 'Microsoft', 'GOOGL': 'Google', 'AMZN': 'Amazon',
    'TSLA': 'Tesla', 'META': 'Meta', 'NVDA': 'NVIDIA', 'JPM': 'JPMorgan',
    'V': 'Visa', 'JNJ': 'Johnson & Johnson', 'WMT': 'Walmart', 'PG': 'Procter Gamble',
    'DIS': 'Disney', 'NFLX': 'Netflix', 'ADBE': 'Adobe', 'CRM': 'Salesforce',
    'INTC': 'Intel', 'AMD': 'AMD', 'PYPL': 'PayPal', 'BA': 'Boeing',
    'NKE': 'Nike', 'KO': 'Coca-Cola', 'PEP': 'Pepsi', 'COST': 'Costco',
    'IBM': 'IBM', 'CSCO': 'Cisco',
    'RELIANCE': 'Reliance Industries', 'TCS': 'Tata Consultancy Services',
    'HDFCBANK': 'HDFC Bank', 'INFY': 'Infosys', 'ICICIBANK': 'ICICI Bank',
    'HINDUNILVR': 'Hindustan Unilever', 'ITC': 'ITC Limited', 'SBIN': 'State Bank of India',
    'BHARTIARTL': 'Bharti Airtel', 'KOTAKBANK': 'Kotak Mahindra Bank',
    'BAJFINANCE': 'Bajaj Finance', 'LT': 'Larsen & Toubro', 'WIPRO': 'Wipro',
    'AXISBANK': 'Axis Bank', 'TITAN': 'Titan', 'MARUTI': 'Maruti Suzuki',
    'ASIANPAINT': 'Asian Paints', 'SUNPHARMA': 'Sun Pharma',
    'TATAMOTORS': 'Tata Motors', 'TATASTEEL': 'Tata Steel',
}


def get_news_api_key():
    """Get News API key from environment."""
    return os.environ.get('NEWS_API_KEY', '').strip()


def is_newsapi_available():
    """Check if NewsAPI key is configured and valid-looking."""
    key = get_news_api_key()
    if not key or len(key) < 10:
        return False
    if 'your_' in key.lower() or key == 'YOUR_API_KEY_HERE':
        return False
    return True


def _simple_sentiment(text):
    """Simple keyword-based sentiment fallback when TextBlob is not available."""
    positive_words = [
        'rise', 'gain', 'positive', 'growth', 'bullish', 'upgrade',
        'strong', 'profit', 'record', 'surge', 'soar', 'boom', 'rally',
        'breakthrough', 'innovation', 'success', 'outperform', 'beat',
        'expansion', 'dividend', 'buyback', 'partnership', 'launch'
    ]
    negative_words = [
        'fall', 'drop', 'decline', 'negative', 'bearish', 'downgrade',
        'weak', 'loss', 'crash', 'fear', 'plunge', 'slump', 'risk',
        'concern', 'investigation', 'lawsuit', 'ban', 'fine', 'penalty',
        'layoff', 'cut', 'downturn', 'recession', 'inflation'
    ]
    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)
    if pos_count > neg_count:
        return min(0.8, 0.2 + (pos_count - neg_count) * 0.15)
    elif neg_count > pos_count:
        return max(-0.8, -0.2 - (neg_count - pos_count) * 0.15)
    return 0.0


def fetch_news(ticker, max_articles=5):
    """
    Fetch recent news articles for a stock ticker via NewsAPI.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'RELIANCE')
        max_articles: Maximum number of articles to return (default 5)

    Returns:
        list of dicts with 'title', 'source', 'url', 'published_at', 'polarity'
        Returns empty list on any failure.
    """
    cache_key = f"news_{ticker.upper()}"
    now = time.time()

    # Check cache first
    if cache_key in _news_cache:
        entry = _news_cache[cache_key]
        if (now - entry['ts']) < _NEWS_CACHE_TTL:
            return entry['data']

    if not is_newsapi_available():
        return []

    api_key = get_news_api_key()
    company = COMPANY_NAMES.get(ticker.upper(), ticker)
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    try:
        import requests
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={company}"
            f"&language=en"
            f"&pageSize={max_articles + 3}"
            f"&sortBy=publishedAt"
            f"&from={cutoff}"
            f"&apiKey={api_key}"
        )

        resp = requests.get(url, timeout=10)
        if not resp.ok:
            return []

        data = resp.json()
        status = data.get('status', 'error')
        if status != 'ok':
            return []

        articles = data.get('articles', [])
        results = []

        for article in articles[:max_articles]:
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')

            if not title:
                continue

            # Combine text for sentiment analysis
            text_for_sentiment = f"{title}. {description or ''}"

            if HAS_TEXTBLOB:
                blob = TextBlob(text_for_sentiment)
                polarity = round(blob.sentiment.polarity, 3)
            else:
                polarity = round(_simple_sentiment(text_for_sentiment), 3)

            results.append({
                'title': title,
                'source': article.get('source', {}).get('name', 'News'),
                'url': article.get('url', ''),
                'published_at': article.get('publishedAt', '')[:10],
                'polarity': polarity,
                'sentiment': _classify_sentiment(polarity)
            })

        # Cache results
        _news_cache[cache_key] = {'data': results, 'ts': now}
        # Limit cache size
        if len(_news_cache) > 50:
            _news_cache.clear()

        return results

    except ImportError:
        return []
    except Exception:
        return []


def _classify_sentiment(polarity):
    """Classify polarity score into positive/neutral/negative label."""
    if polarity > 0.1:
        return 'positive'
    elif polarity < -0.1:
        return 'negative'
    return 'neutral'


def get_news_sentiment(ticker):
    """
    Get aggregate sentiment score from recent news for a ticker.

    Args:
        ticker: Stock ticker symbol

    Returns:
        dict with:
            - avg_polarity: average sentiment score (-1 to 1)
            - sentiment_label: 'Positive', 'Negative', or 'Neutral'
            - article_count: number of articles analyzed
            - headlines: list of recent headlines with sentiment
            - sentiment_breakdown: count of positive/neutral/negative articles
    """
    articles = fetch_news(ticker, max_articles=5)

    if not articles:
        return {
            'avg_polarity': 0.0,
            'sentiment_label': 'Neutral',
            'article_count': 0,
            'headlines': [],
            'sentiment_breakdown': {'positive': 0, 'neutral': 0, 'negative': 0}
        }

    polarities = [a['polarity'] for a in articles]
    avg_pol = sum(polarities) / len(polarities)

    if avg_pol > 0.1:
        label = 'Positive'
    elif avg_pol < -0.1:
        label = 'Negative'
    else:
        label = 'Neutral'

    breakdown = {'positive': 0, 'neutral': 0, 'negative': 0}
    for a in articles:
        s = a.get('sentiment', 'neutral')
        if s in breakdown:
            breakdown[s] += 1

    return {
        'avg_polarity': round(avg_pol, 3),
        'sentiment_label': label,
        'article_count': len(articles),
        'headlines': articles[:3],
        'sentiment_breakdown': breakdown,
        'is_available': True
    }


def sentiment_bias_for_prediction(sentiment_score):
    """
    Convert a sentiment score to a recommendation bias.
    Positive sentiment → slight bullish bias
    Negative sentiment → slight bearish bias

    Returns:
        'bullish', 'bearish', or 'neutral'
    """
    if sentiment_score > 0.15:
        return 'bullish'
    elif sentiment_score < -0.15:
        return 'bearish'
    return 'neutral'


# Run test if executed directly
if __name__ == '__main__':
    print("=" * 60)
    print("  News Sentiment Analysis - Test")
    print("=" * 60)
    print(f"  TextBlob available: {HAS_TEXTBLOB}")
    print(f"  NewsAPI key set: {bool(get_news_api_key())}")
    print()

    for ticker in ['AAPL', 'RELIANCE', 'TSLA', 'TCS']:
        print(f"--- {ticker} ---")
        result = get_news_sentiment(ticker)
        print(f"  Sentiment: {result['sentiment_label']} ({result['avg_polarity']:.3f})")
        print(f"  Articles:  {result['article_count']}")
        print(f"  Breakdown: {result['sentiment_breakdown']}")
        for h in result['headlines'][:2]:
            s = h['sentiment']
            icon = '🟢' if s == 'positive' else ('🔴' if s == 'negative' else '⚪')
            print(f"  {icon} {h['title'][:80]}")
        print()
