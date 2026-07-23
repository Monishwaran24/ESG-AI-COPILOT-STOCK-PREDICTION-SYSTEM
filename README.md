# 🌿 ESG Stock Prediction System

> AI-powered stock market predictions using Environmental, Social, and Governance (ESG) scores combined with machine learning.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3%2B-lightgrey)
![Scikit-learn](https://img.shields.io/badge/Scikit--learn-1.3%2B-orange)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple)
![License](https://img.shields.io/badge/License-MIT-green)

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Machine Learning Pipeline](#-machine-learning-pipeline)
- [API Endpoints](#-api-endpoints)
- [Screenshots](#-screenshots)
- [Contributing](#-contributing)
- [License](#-license)
- [Disclaimer](#-disclaimer)

## 📖 Overview

The **ESG Stock Prediction System** is a comprehensive web application that leverages machine learning to predict stock market movements by combining traditional technical analysis with Environmental, Social, and Governance (ESG) scores. 

Our system trains multiple ML models (Random Forest, Gradient Boosting, XGBoost) on historical stock data and ESG metrics, automatically selecting the best-performing model to generate Buy, Hold, or Sell recommendations with confidence scores.

## ✨ Features

- **🎯 AI-Powered Predictions** - Buy, Hold, or Sell recommendations with confidence percentages
- **🌱 ESG Integration** - Environmental, Social, and Governance scores factored into every prediction
- **📊 Technical Analysis** - SMA, EMA, RSI, MACD, Bollinger Bands indicators
- **📈 Interactive Charts** - Real-time price charts and ESG visualizations using Chart.js
- **🎨 Modern Dashboard** - Responsive design with dark theme and sidebar navigation
- **📉 Model Performance** - Detailed metrics: accuracy, precision, recall, F1 score, confusion matrix
- **⚠️ Risk Assessment** - Low, Medium, High risk levels for each prediction
- **🔍 Stock Search** - Search and filter stocks by ticker or company name
- **🔄 Live Updates** - Real-time clock and dynamic data visualization

## 🛠️ Technology Stack

### Frontend
- **HTML5** & **CSS3** - Structure and styling
- **Bootstrap 5** - Responsive UI framework
- **JavaScript** - Client-side interactivity
- **Chart.js** - Interactive data visualizations

### Backend
- **Python 3.8+** - Core programming language
- **Flask 2.3+** - Web framework
- **SQLite** - Database
- **Joblib** - Model serialization

### Machine Learning
- **Scikit-learn** - ML models (Random Forest, Gradient Boosting)
- **XGBoost** - Gradient boosting framework (optional)
- **Pandas** - Data manipulation
- **NumPy** - Numerical computing
- **yfinance** - Stock data download
- **Matplotlib/Seaborn** - Training visualizations

## 📁 Project Structure

```
ESG-Stock-Prediction/
│
├── app.py                    # Flask web application (main entry point)
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
│
├── model/
│   ├── train_model.py        # ML training pipeline
│   ├── predict.py            # Prediction module
│   ├── model.pkl             # Trained ML model
│   ├── scaler.pkl            # Feature scaler
│   ├── label_encoder.pkl     # Label encoder
│   └── model_metadata.json   # Model performance data
│
├── data/
│   ├── esg_data.csv          # ESG scores dataset
│   └── stock_data.csv        # Stock historical data
│
├── templates/
│   ├── index.html            # Home page
│   ├── dashboard.html        # ESG Dashboard
│   ├── prediction.html       # Stock prediction page
│   ├── performance.html      # Model performance page
│   ├── about.html            # About page
│   └── sidebar.html          # Sidebar navigation (partial)
│
└── static/
    ├── css/
    │   └── style.css         # Custom CSS styles
    ├── js/
    │   └── main.js           # Custom JavaScript
    └── images/               # Screenshots and images
```

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git (optional)

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd ESG-Stock-Prediction
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Train the ML Model

```bash
cd model
python train_model.py
cd ..
```

This will:
1. Download historical stock data from Yahoo Finance
2. Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
3. Merge with ESG data
4. Train Random Forest, Gradient Boosting, and XGBoost models
5. Select the best performing model
6. Save the model and associated artifacts

> **Note:** Training may take 5-15 minutes depending on your internet connection and system. If yfinance fails to download data, the system will fall back to synthetic training data.

### Step 5: Run the Application

```bash
python app.py
```

### Step 6: Open in Browser

Navigate to: **http://127.0.0.1:5000**

## 💻 Usage

### Making Predictions

1. **Navigate** to the **Prediction** page from the sidebar
2. **Select a stock** from the dropdown or enter a ticker symbol
3. Click **Predict** to generate the recommendation
4. View:
   - Current stock price and daily change
   - Buy/Hold/Sell recommendation with confidence
   - ESG scores and risk assessment
   - Technical indicators
   - Historical price chart (6 months)

### Exploring the Dashboard

- View ESG score distribution across all stocks
- Search and filter stocks by ticker or company
- See environmental, social, and governance breakdowns
- Quick access to prediction page for any stock

### Model Performance

- Compare multiple ML models side by side
- View accuracy, precision, recall, and F1 scores
- Examine confusion matrix
- See all features used in training

## 🤖 Machine Learning Pipeline

### Data Collection
- Historical stock data downloaded via `yfinance` (2-year period)
- ESG scores loaded from curated CSV dataset
- Data merged by ticker symbol

### Feature Engineering
- **Technical Indicators:**
  - SMA (10 and 30 day)
  - EMA (10 and 30 day)
  - RSI (14 day)
  - MACD, Signal, Histogram
  - Bollinger Bands (Upper, Lower, Width, Position)
  - Price changes (1d, 5d, 20d)
  - Volume ratio
  - Volatility

- **ESG Features:**
  - ESG Score
  - Environmental Score
  - Social Score
  - Governance Score

### Model Training
- **Random Forest Classifier** (200 trees, max depth 15)
- **Gradient Boosting Classifier** (150 estimators, learning rate 0.1)
- **XGBoost Classifier** (150 estimators, optional)
- Models evaluated using 5-fold cross-validation
- Best model selected based on F1 score

### Target Labels
- **Buy**: Expected >5% gain over 20 trading days
- **Hold**: Expected between -3% and 5% change
- **Sell**: Expected <-3% loss over 20 trading days

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Home page |
| GET | `/dashboard` | ESG Dashboard |
| GET/POST | `/predict` | Stock prediction page |
| GET | `/performance` | Model performance page |
| GET | `/about` | About page |
| POST | `/api/predict` | Prediction API (JSON) |
| GET | `/api/stocks` | Get all stock data |
| GET | `/api/performance` | Get model metrics |
| GET | `/api/stock/<ticker>` | Get specific stock data |

### API Usage Example

```bash
curl -X POST http://127.0.0.1:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL"}'
```

Response:
```json
{
  "ticker": "AAPL",
  "company": "Apple Inc.",
  "recommendation": "Buy",
  "confidence": 85.3,
  "trend": "Bullish",
  "risk_level": "Low",
  "current_price": 185.50,
  "esg_data": {
    "esg_score": 78.5,
    "environmental_score": 72.3,
    "social_score": 82.1,
    "governance_score": 81.0
  }
}
```

## 📸 Screenshots

> *Screenshots will be added after deployment.*

## 👥 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

## ⚠️ Disclaimer

**This system is for educational and research purposes only.** The predictions generated by this system should not be considered as financial advice. Stock market investing involves risk, and past performance does not guarantee future results. Always consult with a qualified financial advisor before making investment decisions.

---

<p align="center">
  <i>Built with ❤️ for Sustainable Investing</i>
  <br>
  <i>Empowering decisions through AI and ESG insights</i>
</p>
