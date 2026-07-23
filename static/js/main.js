'use strict';

document.addEventListener('DOMContentLoaded', function () {
    initializeSidebar();
    initializeLiveClock();
    initializeStockSearch();
    initializePredictionForm();
    initializeCharts();
    initializeTooltips();
    initializeAIChat();
    initializeAJAXPrediction();
    initializeTheme();
    initializeTicker();
    initializeParticles();
});

function initializeSidebar() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (!sidebarToggle || !sidebar) return;

    sidebarToggle.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('show');
    });

    if (overlay) {
        overlay.addEventListener('click', function () {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('show');
        }
    });

    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(function (item) {
        const href = item.getAttribute('href');
        if (href && currentPath.startsWith(href) && href !== '/') {
            item.classList.add('active');
        } else if (href === '/' && currentPath === '/') {
            item.classList.add('active');
        }
    });
}

function initializeLiveClock() {
    const clockElement = document.getElementById('liveClock');
    if (!clockElement) return;

    function updateClock() {
        const now = new Date();
        const options = {
            weekday: 'long', year: 'numeric', month: 'long',
            day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
        };
        clockElement.textContent = now.toLocaleDateString('en-US', options);
    }
    updateClock();
    setInterval(updateClock, 1000);
}

function initializeStockSearch() {
    const searchInput = document.getElementById('stockSearch');
    if (!searchInput) return;

    searchInput.addEventListener('input', function () {
        const query = this.value.toLowerCase().trim();
        document.querySelectorAll('.stock-item').forEach(function (item) {
            const ticker = item.getAttribute('data-ticker')?.toLowerCase() || '';
            const company = item.getAttribute('data-company')?.toLowerCase() || '';
            item.style.display = (ticker.includes(query) || company.includes(query)) ? '' : 'none';
        });
    });

    const clearBtn = document.getElementById('clearSearch');
    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            searchInput.value = '';
            searchInput.dispatchEvent(new Event('input'));
            searchInput.focus();
        });
    }
}

function initializePredictionForm() {
    const form = document.getElementById('predictionForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        const tickerSelect = document.getElementById('tickerSelect');
        const tickerText = form.querySelector('input[name="ticker_text"]');
        let ticker = '';
        if (tickerSelect && tickerSelect.value) ticker = tickerSelect.value;
        else if (tickerText && tickerText.value) ticker = tickerText.value.trim().toUpperCase();

        if (!ticker) {
            e.preventDefault();
            showToast('Please select or enter a stock ticker', 'warning');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span> Analyzing...';
        }

        if (e.type === 'submit') {
            e.preventDefault();
            fetchPredictionAJAX(ticker);
        }
    });

    const tickerSelect = document.getElementById('tickerSelect');
    if (tickerSelect) {
        tickerSelect.addEventListener('change', function () {
            if (this.value) {
                fetchPredictionAJAX(this.value);
            }
        });
    }
}

function initializeAJAXPrediction() {
    const urlParams = new URLSearchParams(window.location.search);
    const tickerParam = urlParams.get('ticker');
    if (tickerParam && window.location.pathname.includes('/predict')) {
        const select = document.getElementById('tickerSelect');
        if (select) {
            setTimeout(function() {
                select.value = tickerParam;
                fetchPredictionAJAX(tickerParam);
            }, 300);
        }
    }
}

function fetchPredictionAJAX(ticker) {
    if (!ticker) return;

    showLoading('Analyzing stock data with AI...');

    fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.error) {
            showToast('Error: ' + data.error, 'danger');
            hideLoading();
            return;
        }
        renderPredictionResult(data);
        if (data.ai_explanation) {
            renderAIExplanation(data.ai_explanation);
        }
        updateFormState(ticker);
    })
    .catch(function(err) {
        showToast('Network error: ' + err.message, 'danger');
        hideLoading();
    });
}

function renderPredictionResult(result) {
    const container = document.getElementById('predictionResult');
    if (!container) return;

    const isPositive = result.price_change_pct >= 0;
    const rec = result.recommendation;
    const recLower = rec.toLowerCase();
    const confidence = result.confidence;

    const confColor = confidence >= 80 ? '#4caf50' : confidence >= 60 ? '#ff9800' : '#f44336';
    const confIcon = rec === 'Buy' ? 'check-circle' : rec === 'Sell' ? 'x-circle' : 'dash-circle';
    const trendIcon = result.trend === 'Bullish' ? 'arrow-up' : result.trend === 'Bearish' ? 'arrow-down' : 'minus';
    const riskClass = result.risk_level.toLowerCase();

    const esg = result.esg_data || {};
    const ind = result.indicators || {};

    const html = `
    <div class="fade-in">
      <div class="row g-4 mb-4">
        <div class="col-lg-4">
          <div class="stock-price-card">
            <div class="stock-ticker">${result.ticker}</div>
            <div class="stock-company">${result.company}</div>
            <div class="stock-price"><span class="currency">$</span>${result.current_price.toFixed(2)}</div>
            <div class="stock-change ${isPositive ? 'positive' : 'negative'}">
              <i class="bi bi-${isPositive ? 'arrow-up' : 'arrow-down'}"></i> ${result.price_change_pct.toFixed(2)}%
            </div>
            <small class="text-secondary"><i class="bi bi-clock-history me-1"></i>${result.prediction_time}</small>
            <div class="mt-2"><small class="text-muted">Model: ${result.model_used || 'AI'} | Acc: ${result.model_accuracy || 85}%</small></div>
          </div>
        </div>
        <div class="col-lg-4">
          <div class="card h-100">
            <div class="card-body text-center d-flex flex-column align-items-center justify-content-center">
              <small class="text-secondary text-uppercase mb-2 fw-bold">AI Recommendation</small>
              <div class="recommendation-badge ${recLower} mb-3">
                <i class="bi bi-${confIcon}"></i> ${rec}
              </div>
              <div class="confidence-meter">
                <canvas id="confidenceGauge"></canvas>
                <div class="confidence-value">
                  <span class="number" style="color:${confColor};">${confidence.toFixed(0)}%</span>
                  <span class="label">Confidence</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-lg-4">
          <div class="card h-100">
            <div class="card-body">
              <small class="text-secondary text-uppercase fw-bold mb-3 d-block">AI Summary</small>
              <div class="d-flex justify-content-between align-items-center mb-3">
                <span class="text-secondary"><i class="bi bi-trending-up me-1"></i> Trend</span>
                <span class="trend-badge ${result.trend.toLowerCase()}"><i class="bi bi-${trendIcon}"></i> ${result.trend}</span>
              </div>
              <div class="d-flex justify-content-between align-items-center mb-3">
                <span class="text-secondary"><i class="bi bi-shield-exclamation me-1"></i> Risk</span>
                <span class="risk-badge ${riskClass}">${result.risk_level}</span>
              </div>
              ${result.industry ? `<div class="d-flex justify-content-between align-items-center mb-3"><span class="text-secondary"><i class="bi bi-building me-1"></i> Industry</span><span class="text-primary small">${result.industry}</span></div>` : ''}
              <div class="d-flex justify-content-between align-items-center">
                <span class="text-secondary"><i class="bi bi-robot me-1"></i> AI Engine</span>
                <span class="text-esg small fw-bold">${result.model_used || 'Ensemble AI'}</span>
              </div>
              ${result.is_simulated ? '<div class="alert alert-custom alert-esg-warning mt-3 mb-0 py-2 small"><i class="bi bi-info-circle me-1"></i> Demo prediction</div>' : ''}
            </div>
          </div>
        </div>
      </div>

      <div class="row g-4 mb-4">
        <div class="col-lg-6">
          <div class="card h-100 fade-in">
            <div class="card-header"><span><i class="bi bi-speedometer2"></i> Technical Indicators</span></div>
            <div class="card-body">
              <div class="row g-3">
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${ind.rsi || '--'}</div><div class="metric-label">RSI (14)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${(ind.macd || 0).toFixed(4)}</div><div class="metric-label">MACD</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">$${(ind.sma_10 || 0).toFixed(2)}</div><div class="metric-label">SMA (10)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">$${(ind.sma_30 || 0).toFixed(2)}</div><div class="metric-label">SMA (30)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${(ind.volume_ratio || 0).toFixed(2)}x</div><div class="metric-label">Volume Ratio</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${(ind.volatility || 0).toFixed(2)}%</div><div class="metric-label">Volatility</div></div></div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-lg-6">
          <div class="card h-100 fade-in">
            <div class="card-header">
              <span><i class="bi bi-flower1"></i> ESG Scores</span>
              <span class="badge bg-${esg.esg_risk === 'Low' ? 'success' : esg.esg_risk === 'Medium' ? 'warning' : 'danger'}">${esg.esg_risk || 'Medium'} Risk</span>
            </div>
            <div class="card-body">
              <div class="row g-3">
                <div class="col-4"><div class="esg-metric-card env text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-droplet"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--env-color);">${(esg.environmental_score || 0).toFixed(1)}</div><div class="esg-metric-label" style="font-size:0.7rem;">Environmental</div></div></div>
                <div class="col-4"><div class="esg-metric-card social text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-people-fill"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--social-color);">${(esg.social_score || 0).toFixed(1)}</div><div class="esg-metric-label" style="font-size:0.7rem;">Social</div></div></div>
                <div class="col-4"><div class="esg-metric-card gov text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-bank"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--gov-color);">${(esg.governance_score || 0).toFixed(1)}</div><div class="esg-metric-label" style="font-size:0.7rem;">Governance</div></div></div>
              </div>
              <hr class="border-secondary my-3">
              <div class="d-flex justify-content-between mb-2"><span class="text-secondary small">Overall ESG Score</span><span class="fw-bold text-esg">${(esg.esg_score || 0).toFixed(1)} / 100</span></div>
              <div class="progress-esg"><div class="progress-bar bg-success" style="width:${esg.esg_score || 0}%;"></div></div>
              <div class="d-flex justify-content-between mt-2"><span class="text-secondary small">Controversy</span><span class="badge bg-${esg.controversy === 'Low' ? 'success' : 'warning'}">${esg.controversy || 'Low'}</span></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card mb-4 fade-in">
        <div class="card-header">
          <span><i class="bi bi-graph-up"></i> ${result.ticker} - Historical Price</span>
          <div>
            <span class="trend-badge ${result.trend.toLowerCase()} me-2"><i class="bi bi-${trendIcon}"></i> ${result.trend}</span>
            <span class="recommendation-badge ${recLower}" style="font-size:0.75rem;padding:0.25rem 0.75rem;">${rec}</span>
          </div>
        </div>
        <div class="card-body">
          <div class="chart-container"><canvas id="stockPriceChart" data-prices='${JSON.stringify(result.historical_prices)}' data-dates='${JSON.stringify(result.historical_dates)}' data-rec="${rec}"></canvas></div>
        </div>
      </div>

      <div class="card mb-4 fade-in">
        <div class="card-header"><span><i class="bi bi-pie-chart-fill"></i> Confidence Breakdown</span></div>
        <div class="card-body">
          <div class="row g-4">
            ${['Buy','Hold','Sell'].map(function(a) {
              const s = result.confidence_scores && result.confidence_scores[a] ? result.confidence_scores[a] : 0;
              const c = a === 'Buy' ? '#4caf50' : a === 'Hold' ? '#ff9800' : '#f44336';
              return '<div class="col-md-4"><div class="text-center p-3" style="background:rgba(0,0,0,0.2);border-radius:12px;"><div class="recommendation-badge '+a.toLowerCase()+' mb-2" style="font-size:0.85rem;">'+a+'</div><div class="display-6 fw-bold" style="color:'+c+';">'+s.toFixed(1)+'%</div><div class="progress-esg mt-2" style="height:6px;"><div class="progress-bar" style="width:'+s+'%;background:'+c+';"></div></div></div></div>';
            }).join('')}
          </div>
        </div>
      </div>
    </div>`;

    container.innerHTML = html;

    setTimeout(function() {
        drawConfidenceGauge(confidence);
        const priceChart = document.getElementById('stockPriceChart');
        if (priceChart) initializeStockPriceChart();
    }, 50);
}

function renderAIExplanation(explanation) {
    const container = document.getElementById('aiExplanation');
    if (!container || !explanation) return;

    const reasons = explanation.reasons || [];
    const reasonsHtml = reasons.map(function(r) {
        return '<li class="list-group-item bg-transparent border-secondary text-light small py-2"><i class="bi bi-check-circle-fill text-esg me-2"></i>' + r + '</li>';
    }).join('');

    container.innerHTML = `
    <div class="card mb-4 fade-in">
      <div class="card-header">
        <span><i class="bi bi-robot"></i> AI Analysis</span>
        <span class="badge bg-${explanation.verdict === 'Buy' ? 'success' : explanation.verdict === 'Sell' ? 'danger' : 'warning'}">${explanation.verdict}</span>
      </div>
      <div class="card-body">
        <p class="mb-3">${explanation.summary || 'AI analysis complete.'}</p>
        ${reasonsHtml ? '<ul class="list-group list-group-flush mt-3">' + reasonsHtml + '</ul>' : ''}
      </div>
    </div>`;
}

function updateFormState(ticker) {
    const select = document.getElementById('tickerSelect');
    const submitBtn = document.querySelector('#predictionForm button[type="submit"]');
    if (select) select.value = ticker;
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-graph-up-arrow me-1"></i> Predict';
    }
}

function showLoading(message) {
    const container = document.getElementById('predictionResult');
    if (!container) return;
    message = message || 'Analyzing stock data with ML model...';
    container.innerHTML = `
      <div class="loading-spinner active">
        <div class="spinner"></div>
        <p>${message}</p>
        <p class="text-muted small">Processing technical indicators, ESG scores & AI analysis</p>
      </div>`;
}

function hideLoading() {
    const spinners = document.querySelectorAll('.loading-spinner');
    spinners.forEach(function(s) { s.classList.remove('active'); });
}

function initializeCharts() {
    initializeESGRadarChart();
    initializeStockPriceChart();
    initializePerformanceChart();
    initializeConfusionMatrix();
    initializeESGDistributionChart();
}

function drawConfidenceGauge(confidence) {
    const canvas = document.getElementById('confidenceGauge');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const size = 120;
    canvas.width = size;
    canvas.height = size;

    const percentage = confidence / 100;
    const startAngle = Math.PI * 0.75;
    const endAngle = startAngle + (Math.PI * 1.5 * percentage);
    const cx = size / 2, cy = size / 2, r = size / 2 - 10;

    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25);
    ctx.strokeStyle = 'rgba(30, 58, 95, 0.5)';
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();

    const color = confidence >= 80 ? '#4caf50' : confidence >= 60 ? '#ff9800' : '#f44336';
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI * 0.75, endAngle, false);
    ctx.strokeStyle = color;
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();
}

function initializeESGRadarChart() {
    const canvas = document.getElementById('esgRadarChart');
    if (!canvas) return;

    if (window._esgRadarChart) {
        window._esgRadarChart.destroy();
    }

    const ctx = canvas.getContext('2d');
    const envScore = parseFloat(canvas.getAttribute('data-env')) || 0;
    const socialScore = parseFloat(canvas.getAttribute('data-social')) || 0;
    const govScore = parseFloat(canvas.getAttribute('data-gov')) || 0;
    const overall = (envScore + socialScore + govScore) / 3;

    window._esgRadarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Environmental', 'Social', 'Governance', 'Overall ESG'],
            datasets: [{
                label: 'ESG Scores',
                data: [envScore, socialScore, govScore, overall],
                backgroundColor: 'rgba(76, 175, 80, 0.2)',
                borderColor: 'rgba(76, 175, 80, 0.8)',
                borderWidth: 2,
                pointBackgroundColor: ['#2196F3','#FF9800','#9C27B0','#4CAF50'],
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(76, 175, 80, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: { label: function(ctx) { return ctx.parsed.r.toFixed(1) + '/100'; } }
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { stepSize: 20, color: '#64748b', backdropColor: 'transparent' },
                    grid: { color: 'rgba(30, 58, 95, 0.5)' },
                    angleLines: { color: 'rgba(30, 58, 95, 0.5)' },
                    pointLabels: { color: '#90caf9', font: { size: 11 } }
                }
            }
        }
    });
}

function initializeStockPriceChart() {
    const canvas = document.getElementById('stockPriceChart');
    if (!canvas) return;

    if (window._stockPriceChart) {
        window._stockPriceChart.destroy();
    }

    const ctx = canvas.getContext('2d');
    let prices = [], labels = [], recommendation = 'Hold';

    try {
        prices = JSON.parse(canvas.getAttribute('data-prices') || '[]');
        labels = JSON.parse(canvas.getAttribute('data-dates') || '[]');
        recommendation = canvas.getAttribute('data-rec') || 'Hold';
    } catch (e) { return; }

    if (prices.length === 0) return;

    const sma10 = calculateSMA(prices, 10);
    const sma30 = calculateSMA(prices, 30);
    const isPositive = prices.length > 1 && prices[prices.length - 1] >= prices[0];
    const lineColor = isPositive ? '#4caf50' : '#f44336';

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, isPositive ? 'rgba(76, 175, 80, 0.3)' : 'rgba(244, 67, 54, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    window._stockPriceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Price', data: prices, borderColor: lineColor, backgroundColor: gradient, borderWidth: 2, fill: true, tension: 0.4, pointRadius: 0, pointHoverRadius: 6 },
                { label: 'SMA 10', data: sma10, borderColor: 'rgba(255, 193, 7, 0.6)', borderWidth: 1.5, fill: false, tension: 0.4, pointRadius: 0, borderDash: [5,5] },
                { label: 'SMA 30', data: sma30, borderColor: 'rgba(156, 39, 176, 0.6)', borderWidth: 1.5, fill: false, tension: 0.4, pointRadius: 0, borderDash: [8,4] }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { labels: { color: '#90caf9', font: { size: 11 }, boxWidth: 12, padding: 15 } },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.9)', titleColor: '#fff', bodyColor: '#90caf9',
                    borderColor: 'rgba(76, 175, 80, 0.3)', borderWidth: 1, padding: 12,
                    callbacks: { label: function(ctx) { return ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2); } }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(30, 58, 95, 0.3)', display: false }, ticks: { color: '#64748b', maxTicksLimit: 10, font: { size: 10 } } },
                y: { grid: { color: 'rgba(30, 58, 95, 0.3)' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return '$' + v.toFixed(0); } } }
            }
        }
    });
}

function initializePerformanceChart() {
    const canvas = document.getElementById('performanceChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let modelData = {};
    try { modelData = JSON.parse(canvas.getAttribute('data-metrics') || '{}'); } catch (e) { return; }
    if (Object.keys(modelData).length === 0) return;

    const modelNames = Object.keys(modelData);
    const metrics = ['accuracy','precision','recall','f1_score'];
    const colors = ['rgba(76, 175, 80, 0.8)','rgba(33, 150, 243, 0.8)','rgba(255, 152, 0, 0.8)','rgba(156, 39, 176, 0.8)'];

    const datasets = metrics.map(function(m, i) {
        return {
            label: m.replace('_',' ').toUpperCase(),
            data: modelNames.map(function(n) { return (modelData[n][m] * 100).toFixed(1); }),
            backgroundColor: colors[i],
            borderColor: colors[i].replace('0.8','1'),
            borderWidth: 1,
            borderRadius: 4
        };
    });

    new Chart(ctx, {
        type: 'bar',
        data: { labels: modelNames, datasets: datasets },
        options: {
            responsive: true, maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#90caf9', font: { size: 11 }, boxWidth: 12, padding: 15 } },
                tooltip: { backgroundColor: 'rgba(10, 25, 41, 0.9)', titleColor: '#fff', bodyColor: '#90caf9', borderColor: 'rgba(76, 175, 80, 0.3)', borderWidth: 1, padding: 12, callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.y + '%'; } } }
            },
            scales: {
                x: { grid: { color: 'rgba(30, 58, 95, 0.3)' }, ticks: { color: '#90caf9', font: { size: 11 } } },
                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(30, 58, 95, 0.3)' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return v + '%'; } } }
            }
        }
    });
}

function initializeConfusionMatrix() {
    const canvas = document.getElementById('confusionMatrixChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let matrix = [];
    const labels = ['Sell', 'Hold', 'Buy'];
    try { matrix = JSON.parse(canvas.getAttribute('data-matrix') || '[]'); } catch (e) { return; }
    if (matrix.length === 0) return;

    const data = [];
    const maxVal = Math.max(...matrix.flat());
    matrix.forEach(function(row, i) {
        row.forEach(function(val, j) {
            data.push({ x: labels[j], y: labels[i], v: val });
        });
    });

    new Chart(ctx, {
        type: 'matrix',
        data: {
            datasets: [{
                data: data,
                backgroundColor: function(ctx) {
                    const val = ctx.dataset.data[ctx.dataIndex].v;
                    return 'rgba(76, 175, 80, ' + (val / maxVal) + ')';
                },
                borderColor: 'rgba(30, 58, 95, 0.5)',
                borderWidth: 1,
                width: 60, height: 60
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.9)', titleColor: '#fff', bodyColor: '#90caf9',
                    borderColor: 'rgba(76, 175, 80, 0.3)', borderWidth: 1, padding: 12,
                    callbacks: {
                        title: function(ctx) { return 'Predicted: ' + ctx[0].raw.x + ' / Actual: ' + ctx[0].raw.y; },
                        label: function(ctx) { return 'Count: ' + ctx.raw.v; }
                    }
                }
            },
            scales: {
                x: { type: 'category', labels: labels, offset: true, grid: { display: false }, ticks: { color: '#90caf9', font: { size: 11 } }, title: { display: true, text: 'Predicted', color: '#64748b', font: { size: 12 } } },
                y: { type: 'category', labels: labels, offset: true, grid: { display: false }, ticks: { color: '#90caf9', font: { size: 11 } }, title: { display: true, text: 'Actual', color: '#64748b', font: { size: 12 } } }
            }
        }
    });
}

function initializeESGDistributionChart() {
    const canvas = document.getElementById('esgDistributionChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let esgData = [];
    try { esgData = JSON.parse(canvas.getAttribute('data-esg') || '[]'); } catch (e) { return; }
    if (esgData.length === 0) return;

    const tickers = esgData.map(function(d) { return d.ticker; });
    const envScores = esgData.map(function(d) { return d.env; });
    const socialScores = esgData.map(function(d) { return d.social; });
    const govScores = esgData.map(function(d) { return d.gov; });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tickers,
            datasets: [
                { label: 'Environmental', data: envScores, backgroundColor: 'rgba(33, 150, 243, 0.7)', borderColor: '#2196F3', borderWidth: 1, borderRadius: 2 },
                { label: 'Social', data: socialScores, backgroundColor: 'rgba(255, 152, 0, 0.7)', borderColor: '#FF9800', borderWidth: 1, borderRadius: 2 },
                { label: 'Governance', data: govScores, backgroundColor: 'rgba(156, 39, 176, 0.7)', borderColor: '#9C27B0', borderWidth: 1, borderRadius: 2 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: true,
            plugins: {
                legend: { labels: { color: '#90caf9', font: { size: 11 }, boxWidth: 12, padding: 15 } },
                tooltip: { backgroundColor: 'rgba(10, 25, 41, 0.9)', titleColor: '#fff', bodyColor: '#90caf9', borderColor: 'rgba(76, 175, 80, 0.3)', borderWidth: 1, padding: 12 }
            },
            scales: {
                x: { grid: { color: 'rgba(30, 58, 95, 0.3)' }, ticks: { color: '#90caf9', font: { size: 10 } } },
                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(30, 58, 95, 0.3)' }, ticks: { color: '#64748b', font: { size: 10 } } }
            }
        }
    });
}

function calculateSMA(data, period) {
    const sma = [];
    for (let i = 0; i < data.length; i++) {
        if (i < period - 1) { sma.push(null); }
        else {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += data[i - j];
            sma.push(sum / period);
        }
    }
    return sma;
}

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(value);
}

function formatPercent(value, decimals) {
    return value.toFixed(decimals || 2) + '%';
}

function initializeTooltips() {
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(el) {
            new bootstrap.Tooltip(el);
        });
    }
}

function initializeAIChat() {
    const chatToggle = document.getElementById('aiChatToggle');
    const chatWidget = document.getElementById('aiChatWidget');
    const chatClose = document.getElementById('aiChatClose');
    const chatInput = document.getElementById('aiChatInput');
    const chatSend = document.getElementById('aiChatSend');
    const chatMessages = document.getElementById('aiChatMessages');

    if (!chatToggle || !chatWidget) return;

    chatToggle.addEventListener('click', function() {
        chatWidget.classList.toggle('open');
        if (chatWidget.classList.contains('open') && chatMessages) {
            addBotMessage('Hello! I\'m your AI investing assistant. Ask me about any stock or get investment insights!');
        }
    });

    if (chatClose) {
        chatClose.addEventListener('click', function() {
            chatWidget.classList.remove('open');
        });
    }

    if (chatSend && chatInput) {
        chatSend.addEventListener('click', function() {
            sendChatMessage();
        });
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendChatMessage();
        });
    }
}

function sendChatMessage() {
    const input = document.getElementById('aiChatInput');
    const messages = document.getElementById('aiChatMessages');
    if (!input || !messages || !input.value.trim()) return;

    const text = input.value.trim();
    input.value = '';
    addUserMessage(text);

    addBotMessage('Analyzing ' + text + '...', true);
    fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: text })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        removeLoadingMessage();
        if (data.error) {
            addBotMessage('Sorry, I couldn\'t find data for "' + text + '". Try a ticker symbol (e.g., AAPL, MSFT) or company name.');
        } else {
            const rec = data.recommendation;
            const conf = data.confidence;
            const emoji = rec === 'Buy' ? '📈' : rec === 'Sell' ? '📉' : '📊';
            const aiMsg = data.ai_explanation;
            let response = emoji + ' **' + data.ticker + ' (' + data.company + ')** - ' + rec + ' @ ' + conf + '% confidence\n\n';
            if (aiMsg && aiMsg.summary) {
                response += aiMsg.summary;
            } else {
                response += 'Price: $' + data.current_price + ' | Trend: ' + data.trend + ' | Risk: ' + data.risk_level;
            }
            response += '\n\n_You can view full analysis on the Prediction page._';
            addBotMessage(response);
        }
    })
    .catch(function(err) {
        removeLoadingMessage();
        addBotMessage('Sorry, I encountered an error. Please try again.');
    });
}

function addUserMessage(text) {
    const messages = document.getElementById('aiChatMessages');
    if (!messages) return;
    const div = document.createElement('div');
    div.className = 'chat-message user';
    div.innerHTML = '<div class="chat-bubble user-bubble">' + escapeHtml(text) + '</div>';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function addBotMessage(text, isLoading) {
    const messages = document.getElementById('aiChatMessages');
    if (!messages) return;
    const div = document.createElement('div');
    div.className = 'chat-message bot' + (isLoading ? ' loading-msg' : '');
    div.innerHTML = '<div class="chat-bubble bot-bubble">' + (isLoading ? '<div class="spinner-border spinner-border-sm me-2" role="status"></div> Thinking...' : formatBotMessage(text)) + '</div>';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function removeLoadingMessage() {
    const loading = document.querySelector('.chat-message.loading-msg');
    if (loading) loading.remove();
}

function formatBotMessage(text) {
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>').replace(/_(.*?)_/g, '<em>$1</em>');
}

function escapeHtml(text) {
    var d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

/* ============================================================
   THEME TOGGLE (Dark / Light)
   ============================================================ */
function initializeTheme() {
    const saved = localStorage.getItem('esg-theme');
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        updateThemeUI(true);
    }
}

function toggleTheme() {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    if (isLight) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('esg-theme', 'dark');
        updateThemeUI(false);
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('esg-theme', 'light');
        updateThemeUI(true);
    }
    showToast('Switched to ' + (isLight ? 'Dark' : 'Light') + ' theme', 'info');
}

function updateThemeUI(isLight) {
    const icon = document.getElementById('themeIcon');
    const label = document.getElementById('themeLabel');
    if (!icon || !label) return;
    if (isLight) {
        icon.className = 'bi bi-sun-fill';
        label.textContent = 'Light Mode';
    } else {
        icon.className = 'bi bi-moon-stars-fill';
        label.textContent = 'Dark Mode';
    }
}

function showToast(message, type) {
    type = type || 'info';
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }
    const icons = { success: 'bi-check-circle-fill', error: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    const icon = icons[type] || icons.info;
    const toast = document.createElement('div');
    toast.className = 'toast-custom ' + type;
    toast.innerHTML = '<i class="bi ' + icon + '"></i> ' + escapeHtml(message);
    container.appendChild(toast);
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(function() { toast.remove(); }, 300);
    }, 3500);
}

/* ============================================================
   LIVE TICKER
   ============================================================ */
function initializeTicker() {
    const track = document.getElementById('tickerItems');
    if (!track) return;
    const tickers = ['AAPL','MSFT','GOOGL','AMZN','TSLA','NVDA','JPM','V','JNJ','WMT','PG','DIS','NFLX','ADBE','CRM','PYPL','NKE','KO','PEP','COST'];
    const html = tickers.map(function(t) {
        return '<span class="navbar-ticker-item" data-tkr="' + t + '">' +
            '<span class="tick-symbol">' + t + '</span>' +
            '<span class="tick-price" id="tp-' + t + '">--</span>' +
            '<span class="tick-change" id="tc-' + t + '"></span>' +
        '</span>';
    }).join('');
    track.innerHTML = html + html;

    fetch('/api/ticker/prices?tickers=' + tickers.join(','))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            tickers.forEach(function(t) {
                if (data[t]) {
                    var priceEl = document.getElementById('tp-' + t);
                    var changeEl = document.getElementById('tc-' + t);
                    if (priceEl) priceEl.textContent = '$' + data[t].price.toFixed(2);
                    if (changeEl) {
                        var chg = data[t].change;
                        changeEl.textContent = (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
                        changeEl.className = 'tick-change ' + (chg >= 0 ? 'pos' : 'neg');
                    }
                }
            });
        })
        .catch(function() {});

    setInterval(function() {
        fetch('/api/ticker/prices?tickers=' + tickers.join(','))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                tickers.forEach(function(t) {
                    if (data[t]) {
                        var priceEl = document.getElementById('tp-' + t);
                        var changeEl = document.getElementById('tc-' + t);
                        if (priceEl) {
                            var oldPrice = parseFloat(priceEl.textContent.replace('$',''));
                            var newPrice = data[t].price;
                            priceEl.textContent = '$' + newPrice.toFixed(2);
                            if (newPrice > oldPrice) priceEl.style.color = '#4caf50';
                            else if (newPrice < oldPrice) priceEl.style.color = '#f44336';
                            setTimeout(function() { if (priceEl) priceEl.style.color = ''; }, 1000);
                        }
                        if (changeEl) {
                            var chg = data[t].change;
                            changeEl.textContent = (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
                            changeEl.className = 'tick-change ' + (chg >= 0 ? 'pos' : 'neg');
                        }
                    }
                });
            })
            .catch(function() {});
    }, 30000);
}

/* ============================================================
   PARTICLE BACKGROUND
   ============================================================ */
function initializeParticles() {
    var canvas = document.getElementById('particle-canvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var particles = [];
    var w, h;

    function resize() {
        w = window.innerWidth;
        h = window.innerHeight;
        canvas.width = w;
        canvas.height = h;
    }
    resize();
    window.addEventListener('resize', resize);

    var count = Math.min(60, Math.floor(w * h / 20000));
    for (var i = 0; i < count; i++) {
        particles.push({
            x: Math.random() * w,
            y: Math.random() * h,
            vx: (Math.random() - 0.5) * 0.5,
            vy: (Math.random() - 0.5) * 0.5,
            r: Math.random() * 2.5 + 0.5,
            alpha: Math.random() * 0.5 + 0.1
        });
    }

    function animate() {
        ctx.clearRect(0, 0, w, h);
        particles.forEach(function(p) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0) p.x = w;
            if (p.x > w) p.x = 0;
            if (p.y < 0) p.y = h;
            if (p.y > h) p.y = 0;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(76, 175, 80, ' + p.alpha + ')';
            ctx.fill();
        });

        for (var i = 0; i < particles.length; i++) {
            for (var j = i + 1; j < particles.length; j++) {
                var dx = particles[i].x - particles[j].x;
                var dy = particles[i].y - particles[j].y;
                var dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = 'rgba(76, 175, 80, ' + (0.08 * (1 - dist / 150)) + ')';
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(animate);
    }
    animate();
}
