'use strict';

/* ============================================================
   SPA ROUTER STATE
   ============================================================ */
var _tickerInterval = null;
var _pageCache = {};
var _prefetchInFlight = {};

/* ============================================================
   INITIALIZATION
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {
    // Persistent (run once)
    initializeSidebar();
    initializeLiveClock();
    initializeAIChat();
    initializeTheme();
    initializeTicker();
    initializeParticles();
    initializeRouter();
    initializeMarketStatus();

    // Page-scoped (run on every navigation)
    initializePageContent();

    // Prefetch sidebar links after the initial page loads
    setTimeout(function() {
        prefetchPages();
    }, 1000);
});

function initializePageContent() {
    initializeStockSearch();
    initializePredictionForm();
    initializeCharts();
    initializeTooltips();
    initializeAJAXPrediction();
    initializeXAIToggle();
    initializeNewsAlerts();
    updateActiveNavItem();
    if (window.ESGMotion && window.ESGMotion.initMotionSystem) {
        window.ESGMotion.initMotionSystem();
    }
    if (window.ESG3D && window.ESG3D.init) {
        window.ESG3D.init();
    }
}

function safeGetContext(canvasId) {
    var el = document.getElementById(canvasId);
    if (!el || typeof el.getContext !== 'function') return null;
    try {
        return el.getContext('2d');
    } catch(e) {
        return null;
    }
}

function updateActiveNavItem() {
    var currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(function (item) {
        item.classList.remove('active');
        var href = item.getAttribute('href');
        if (href && currentPath.startsWith(href) && href !== '/') {
            item.classList.add('active');
        } else if (href === '/' && currentPath === '/') {
            item.classList.add('active');
        }
    });
}

function initializeSidebar() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const trigger = document.getElementById('sidebarEdgeTrigger');
    const overlay = document.getElementById('sidebarOverlay');

    if (!sidebar) return;

    let isPointerInTrigger = false;
    let isPointerInSidebar = false;
    let closeTimer = null;

    function openSidebar() {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        sidebar.classList.add('open');
        if (overlay && window.innerWidth < 992) {
            overlay.classList.add('show');
        }
    }

    function closeSidebar(force) {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        isPointerInTrigger = false;
        isPointerInSidebar = false;
        if (sidebar) {
            sidebar.classList.remove('open');
        }
        if (overlay) {
            overlay.classList.remove('show');
        }
        if (sidebar && sidebar.contains(document.activeElement)) {
            document.activeElement.blur();
        }
    }
    window.closeSidebar = closeSidebar;

    function scheduleClose() {
        if (closeTimer) clearTimeout(closeTimer);
        closeTimer = setTimeout(function () {
            // Close only if pointer is outside BOTH trigger and sidebar, and focus is not inside
            const hasFocusInside = sidebar.contains(document.activeElement);
            if (!isPointerInTrigger && !isPointerInSidebar && !hasFocusInside) {
                closeSidebar();
            }
        }, 150); // 150ms smooth transition window
    }

    // 1. Edge Trigger Zone Events
    if (trigger) {
        trigger.addEventListener('pointerenter', function (e) {
            if (e.pointerType === 'mouse' || window.innerWidth >= 992) {
                isPointerInTrigger = true;
                openSidebar();
            }
        });

        trigger.addEventListener('pointerleave', function (e) {
            if (e.pointerType === 'mouse' || window.innerWidth >= 992) {
                isPointerInTrigger = false;
                scheduleClose();
            }
        });
    }

    // 2. Sidebar Container Events
    sidebar.addEventListener('pointerenter', function (e) {
        if (e.pointerType === 'mouse' || window.innerWidth >= 992) {
            isPointerInSidebar = true;
            openSidebar();
        }
    });

    sidebar.addEventListener('pointerleave', function (e) {
        if (e.pointerType === 'mouse' || window.innerWidth >= 992) {
            isPointerInSidebar = false;
            scheduleClose();
        }
    });

    // Close immediately when clicking any navigation link
    sidebar.querySelectorAll('.nav-item').forEach(function(item) {
        item.addEventListener('click', function() {
            closeSidebar(true);
        });
    });

    // 3. Accessibility: Keyboard Focus within Sidebar
    sidebar.addEventListener('focusin', function () {
        openSidebar();
    });

    sidebar.addEventListener('focusout', function (e) {
        if (!sidebar.contains(e.relatedTarget)) {
            scheduleClose();
        }
    });

    // 4. Mobile Toggle Button
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (sidebar.classList.contains('open')) {
                closeSidebar(true);
            } else {
                openSidebar();
            }
        });
    }

    // 5. Overlay Click
    if (overlay) {
        overlay.addEventListener('click', function () {
            closeSidebar(true);
        });
    }

    // 6. Escape Key Dismissal
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            closeSidebar(true);
            if (sidebarToggle) {
                sidebarToggle.focus();
            }
        }
    });

    updateActiveNavItem();
}

function initializeMarketStatus() {
    const marketEl = document.getElementById('marketStatus');
    if (!marketEl) return;

    function updateMarketStatus() {
        fetch('/api/market/hours')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var markets = data.markets || {};
                var openMarkets = [];
                var closedMarkets = [];
                var total = 0;

                for (var name in markets) {
                    var m = markets[name];
                    total++;
                    if (m.is_open) {
                        openMarkets.push(name + ' (' + m.next_event + ')');
                    } else {
                        closedMarkets.push(name);
                    }
                }

                if (openMarkets.length > 0) {
                    marketEl.innerHTML = '<span class="status-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#4caf50;margin-right:6px;box-shadow:0 0 6px rgba(76,175,80,0.6);"></span> ' +
                        openMarkets[0].split(' (')[0] + ' Open - ' + data.server_time.split(' ')[1];
                    marketEl.style.color = '#4caf50';
                } else {
                    marketEl.innerHTML = '<span class="status-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#ffc107;margin-right:6px;"></span> Markets Closed - ' + data.server_time.split(' ')[1];
                    marketEl.style.color = '#ffc107';
                }
            })
            .catch(function() {
                marketEl.textContent = 'Market status unavailable';
                marketEl.style.color = 'var(--text-muted)';
            });
    }

    updateMarketStatus();
    setInterval(updateMarketStatus, 60000); // Refresh every minute
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
        const visibleItems = [];
        document.querySelectorAll('.stock-item').forEach(function (item) {
            const ticker = item.getAttribute('data-ticker')?.toLowerCase() || '';
            const company = item.getAttribute('data-company')?.toLowerCase() || '';
            const matches = (ticker.includes(query) || company.includes(query));
            if (matches) {
                item.style.display = '';
                visibleItems.push(item);
            } else {
                item.style.display = 'none';
            }
        });
        if (query && visibleItems.length > 0 && window.ESGMotion && window.ESGMotion.animateFadeIn) {
            window.ESGMotion.animateFadeIn(visibleItems.slice(0, 10), { duration: 0.22 });
        }
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
        e.preventDefault(); // Always prevent full POST - use AJAX instead
        const tickerSelect = document.getElementById('tickerSelect');
        const tickerText = form.querySelector('input[name="ticker_text"]');
        let ticker = '';
        if (tickerSelect && tickerSelect.value) ticker = tickerSelect.value;
        else if (tickerText && tickerText.value) ticker = tickerText.value.trim().toUpperCase();

        if (!ticker) {
            showToast('Please select or enter a stock ticker', 'warning');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span> Analyzing...';
        }

        fetchPredictionAJAX(ticker);
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
    if (!window.location.pathname.includes('/predict')) return;

    var select = document.getElementById('tickerSelect');
    if (!select) return;

    var urlParams = new URLSearchParams(window.location.search);
    var tickerParam = urlParams.get('ticker');

    // Determine which ticker to fetch: from URL param, or default to first stock
    var tickerToFetch = tickerParam || (select.options.length > 1 ? select.options[1].value : '');
    
    if (tickerToFetch) {
        setTimeout(function() {
            // Check if a prediction result already exists on the page (server-rendered)
            var existingResult = document.querySelector('#predictionResult .stock-price-card');
            if (!existingResult) {
                select.value = tickerToFetch;
                var evt = new Event('change', { bubbles: true });
                select.dispatchEvent(evt);
            }
        }, 100);
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

function safeFmt(val, decimals, fallback) {
    if (val === null || val === undefined || isNaN(val)) return (fallback !== undefined ? fallback : '--');
    return Number(val).toFixed(decimals !== undefined ? decimals : 2);
}

function renderPredictionResult(result) {
    const container = document.getElementById('predictionResult');
    if (!container) return;

    const rawPrice = result.current_price != null && !isNaN(result.current_price) ? Number(result.current_price) : 0;
    const rawChange = result.price_change_pct != null && !isNaN(result.price_change_pct) ? Number(result.price_change_pct) : 0;
    const isPositive = rawChange >= 0;
    const rec = result.recommendation || 'Hold';
    const recLower = rec.toLowerCase();
    const confidence = result.confidence != null && !isNaN(result.confidence) ? Number(result.confidence) : 50;

    const confColor = confidence >= 80 ? '#4caf50' : confidence >= 60 ? '#ff9800' : '#f44336';
    const confIcon = rec === 'Buy' ? 'check-circle' : rec === 'Sell' ? 'x-circle' : 'dash-circle';
    const trendIcon = result.trend === 'Bullish' ? 'arrow-up' : result.trend === 'Bearish' ? 'arrow-down' : 'minus';
    const riskClass = (result.risk_level || 'medium').toLowerCase();

    const esg = result.esg_data || {};
    const ind = result.indicators || {};
    const currSym = result.currency_symbol || '$';

    const html = `
    <div class="fade-in">
      <div class="row g-4 mb-4">
        <div class="col-lg-4">
          <div class="stock-price-card h-100 d-flex flex-column justify-content-between p-4">
            <div>
              <div class="d-flex justify-content-between align-items-start mb-2">
                <div>
                  <div class="stock-ticker">${escapeHtml(result.ticker || '')}</div>
                  <div class="stock-company text-truncate" style="max-width: 210px;">${escapeHtml(result.company || '')}</div>
                </div>
                <span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1 small">
                  <i class="bi bi-broadcast me-1"></i> Live
                </span>
              </div>
              <div class="stock-price my-2"><span class="currency">${currSym}</span>${safeFmt(result.current_price, 2, '0.00')}</div>
              <div class="stock-change ${isPositive ? 'positive' : 'negative'} mb-2">
                <i class="bi bi-${isPositive ? 'arrow-up' : 'arrow-down'}"></i> ${safeFmt(result.price_change_pct, 2, '0.00')}%
              </div>
            </div>
            <div class="pt-3 border-top border-secondary border-opacity-25 d-flex justify-content-between align-items-center">
              <small class="text-secondary"><i class="bi bi-clock-history me-1"></i> ${escapeHtml(result.prediction_time || '')}</small>
              <small class="text-muted">Acc: <strong class="text-esg">${safeFmt(result.model_accuracy, 1, '85')}%</strong></small>
            </div>
          </div>
        </div>

        <div class="col-lg-4">
          <div class="card glass-card h-100">
            <div class="card-body text-center d-flex flex-column align-items-center justify-content-center p-4">
              <small class="text-secondary text-uppercase mb-2 fw-bold" style="letter-spacing: 0.5px;">AI Recommendation</small>
              <div class="recommendation-badge ${recLower} mb-3">
                <i class="bi bi-${confIcon}"></i> ${rec}
              </div>
              <div class="confidence-meter mb-2">
                <canvas id="confidenceGauge" width="120" height="120"></canvas>
                <div class="confidence-value">
                  <span class="number" style="color:${confColor};">${confidence.toFixed(0)}%</span>
                  <span class="label">Confidence</span>
                </div>
              </div>
              <small class="text-muted"><i class="bi bi-shield-check me-1 text-esg"></i> Algorithmic Conviction</small>
            </div>
          </div>
        </div>

        <div class="col-lg-4">
          <div class="card glass-card h-100">
            <div class="card-body p-4 d-flex flex-column justify-content-between">
              <div>
                <div class="d-flex align-items-center justify-content-between mb-3">
                  <small class="text-secondary text-uppercase fw-bold" style="letter-spacing: 0.5px;">AI Summary</small>
                  <span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-0.5 small">Live ML</span>
                </div>
                <div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom border-secondary border-opacity-25">
                  <span class="text-secondary small"><i class="bi bi-trending-up me-1 text-esg"></i> Trend Direction</span>
                  <span class="trend-badge ${(result.trend || 'neutral').toLowerCase()}"><i class="bi bi-${trendIcon}"></i> ${result.trend || 'N/A'}</span>
                </div>
                <div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom border-secondary border-opacity-25">
                  <span class="text-secondary small"><i class="bi bi-shield-exclamation me-1 text-warning"></i> Risk Profile</span>
                  <span class="risk-badge ${riskClass}">${result.risk_level || 'N/A'}</span>
                </div>
                ${result.industry ? `<div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom border-secondary border-opacity-25"><span class="text-secondary small"><i class="bi bi-building me-1 text-info"></i> Sector / Industry</span><span class="text-light small fw-semibold">${escapeHtml(result.industry)}</span></div>` : ''}
              </div>
              <div class="d-flex justify-content-between align-items-center pt-2">
                <span class="text-secondary small"><i class="bi bi-robot me-1 text-esg"></i> Decision Engine</span>
                <span class="text-esg small fw-bold">${escapeHtml(result.model_used || 'Ensemble AI')}</span>
              </div>
              ${result.ml_unavailable ? '<div class="alert alert-custom alert-esg-warning mt-3 mb-0 py-2 small"><i class="bi bi-exclamation-triangle me-1"></i> <strong>ML model unavailable</strong> &mdash; showing real-time market data only</div>' : ''}
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
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${safeFmt(ind.rsi, 1, '--')}</div><div class="metric-label">RSI (14)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${safeFmt(ind.macd, 4, '0.0000')}</div><div class="metric-label">MACD</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${currSym}${safeFmt(ind.sma_10, 2, '0.00')}</div><div class="metric-label">SMA (10)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${currSym}${safeFmt(ind.sma_30, 2, '0.00')}</div><div class="metric-label">SMA (30)</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${safeFmt(ind.volume_ratio, 2, '1.00')}x</div><div class="metric-label">Volume Ratio</div></div></div>
                <div class="col-6"><div class="metric-item"><div class="metric-value" style="font-size:1.3rem;">${safeFmt(ind.volatility, 2, '0.00')}%</div><div class="metric-label">Volatility</div></div></div>
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
                <div class="col-4"><div class="esg-metric-card env text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-droplet"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--env-color);">${safeFmt(esg.environmental_score, 1, '0.0')}</div><div class="esg-metric-label" style="font-size:0.7rem;">Environmental</div></div></div>
                <div class="col-4"><div class="esg-metric-card social text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-people-fill"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--social-color);">${safeFmt(esg.social_score, 1, '0.0')}</div><div class="esg-metric-label" style="font-size:0.7rem;">Social</div></div></div>
                <div class="col-4"><div class="esg-metric-card gov text-center p-3" style="background:transparent;"><div class="esg-metric-icon mx-auto" style="width:40px;height:40px;font-size:1.2rem;"><i class="bi bi-bank"></i></div><div class="esg-metric-value" style="font-size:1.5rem;color:var(--gov-color);">${safeFmt(esg.governance_score, 1, '0.0')}</div><div class="esg-metric-label" style="font-size:0.7rem;">Governance</div></div></div>
              </div>
              <hr class="border-secondary my-3">
              <div class="d-flex justify-content-between mb-2"><span class="text-secondary small">Overall ESG Score</span><span class="fw-bold text-esg">${safeFmt(esg.esg_score, 1, '0.0')} / 100</span></div>
              <div class="progress-esg"><div class="progress-bar bg-success" style="width:${safeFmt(esg.esg_score, 0, '0')}%;"></div></div>
              <div class="d-flex justify-content-between mt-2"><span class="text-secondary small">Controversy</span><span class="badge bg-${esg.controversy === 'Low' ? 'success' : 'warning'}">${esg.controversy || 'Low'}</span></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card mb-4 fade-in chart-card-premium">
        <div class="card-header">
          <span><i class="bi bi-candlestick-chart-fill"></i> ${result.ticker} - Candlestick Chart</span>
          <div class="d-flex align-items-center gap-2">
            <small class="text-muted" id="candlePatternBadge"></small>
            <span class="trend-badge ${(result.trend || 'neutral').toLowerCase()} me-2"><i class="bi bi-${trendIcon}"></i> ${result.trend || 'N/A'}</span>
            <span class="recommendation-badge ${recLower}" style="font-size:0.75rem;padding:0.25rem 0.75rem;">${rec}</span>
          </div>
        </div>
        <div class="card-body">
          <div class="candle-chart-wrap">
            <div class="chart-toolbar d-flex justify-content-end gap-2 mb-2 chart-toolbar-premium">
              <button class="btn-outline-esg btn-sm candle-timeframe candle-timeframe-premium" data-tf="1mo">1M</button>
              <button class="btn-outline-esg btn-sm candle-timeframe candle-timeframe-premium active" data-tf="3mo">3M</button>
              <button class="btn-outline-esg btn-sm candle-timeframe candle-timeframe-premium" data-tf="6mo">6M</button>
              <button class="btn-outline-esg btn-sm candle-timeframe candle-timeframe-premium" data-tf="1y">1Y</button>
            </div>
            <div id="tvCandleChart" class="candle-chart-main" style="width:100%;height:380px;"></div>
            <div id="tvVolumeChart" class="candle-chart-volume" style="width:100%;height:80px;"></div>
            <div class="d-flex justify-content-between mt-2">
              <small class="text-muted" id="candlePriceInfo"></small>
              <small class="text-muted" id="candlePatternList"></small>
            </div>
          </div>
        </div>
      </div>

      <div class="card mb-4 fade-in">
        <div class="card-header"><span><i class="bi bi-pie-chart-fill"></i> Confidence Breakdown</span></div>
        <div class="card-body">
          <div class="row g-4">
            ${['Buy','Sell'].map(function(a) {
              const s = result.confidence_scores && result.confidence_scores[a] ? result.confidence_scores[a] : 0;
              const c = a === 'Buy' ? '#4caf50' : '#f44336';
              return '<div class="col-md-6"><div class="text-center p-3" style="background:rgba(0,0,0,0.2);border-radius:12px;"><div class="recommendation-badge '+a.toLowerCase()+' mb-2" style="font-size:0.85rem;">'+a+'</div><div class="display-6 fw-bold" style="color:'+c+';">'+s.toFixed(1)+'%</div><div class="progress-esg mt-2" style="height:6px;"><div class="progress-bar" style="width:'+s+'%;background:'+c+';"></div></div></div></div>';
            }).join('')}
          </div>
        </div>
      </div>

      <!-- News Sentiment Card -->
      ${renderNewsSentimentCard(result.ai_explanation ? result.ai_explanation.news_sentiment : null)}

      <!-- XAI Explainable AI Section -->
      <div class="card mb-4 fade-in" id="xaiCard" style="display:none;">
        <div class="card-header">
          <span>
            <i class="bi bi-lightbulb-fill text-warning me-2"></i>
            Explainable AI
            <span class="badge bg-info ms-2" style="font-size:0.6rem;vertical-align:middle;">XAI</span>
          </span>
          <div class="d-flex align-items-center gap-2">
            <div class="xai-method-toggle btn-group btn-group-sm" role="group" aria-label="XAI method">
              <button type="button" class="xai-toggle-btn active" data-method="auto" title="Auto-select best method">
                <i class="bi bi-robot"></i> Auto
              </button>
              <button type="button" class="xai-toggle-btn" data-method="shap" title="SHAP (Shapley Additive Explanations)">
                <i class="bi bi-graph-up"></i> SHAP
              </button>
              <button type="button" class="xai-toggle-btn" data-method="lime" title="LIME (Local Interpretable Model-agnostic Explanations)">
                <i class="bi bi-bar-chart-steps"></i> LIME
              </button>
            </div>
            <small class="text-muted" id="xaiMethod"></small>
          </div>
        </div>
        <div class="card-body">
          <div id="xaiSummary" class="mb-4 text-secondary small"></div>
          <div id="xaiContributions"></div>
          <div class="text-center mt-3">
            <small class="text-muted" id="xaiPriceImpact"></small>
          </div>
        </div>
      </div>
    </div>`;

    container.innerHTML = html;

    if (window.ESGMotion && window.ESGMotion.animatePredictionResult) {
        window.ESGMotion.animatePredictionResult(container);
    }
    if (window.ESGCardTilt && window.ESGCardTilt.init) {
        window.ESGCardTilt.init();
    }

    setTimeout(function() {
        drawConfidenceGauge(confidence);
        if (window.ESGMotion && window.ESGMotion.animateAllCounters) {
            window.ESGMotion.animateAllCounters();
        }
        // Reset candle render guard because previous chart containers were destroyed by innerHTML replacement
        _candleRendering = false;
        // Render TradingView candlestick chart
        if (typeof renderCandlestickChart === 'function' && result && result.ticker) {
            renderCandlestickChart(result.ticker, '3mo');
        }
        // Trigger XAI explanation fetch for this ticker
        if (result && result.ticker) {
            renderXAI(result.ticker);
        }
    }, 50);
}

function renderNewsSentimentCard(newsSentiment) {
    if (!newsSentiment || !newsSentiment.article_count || newsSentiment.article_count === 0) {
        return '';
    }
    
    var label = newsSentiment.sentiment_label || 'Neutral';
    var labelLower = label.toLowerCase();
    var breakdown = newsSentiment.sentiment_breakdown || {positive: 0, neutral: 0, negative: 0};
    var avgPol = newsSentiment.avg_polarity || 0;
    var avgColor = avgPol > 0.1 ? '#4caf50' : avgPol < -0.1 ? '#f44336' : '#ffc107';
    var labelIcon = label === 'Positive' ? 'emoji-sunglasses' : label === 'Negative' ? 'emoji-frown' : 'emoji-neutral';
    
    var headlinesHtml = '';
    var headlines = newsSentiment.headlines || [];
    for (var i = 0; i < headlines.length; i++) {
        var hl = headlines[i];
        var s = hl.sentiment || 'neutral';
        var sIcon = s === 'positive' ? 'hand-thumbs-up-fill' : s === 'negative' ? 'hand-thumbs-down-fill' : 'dash-circle-fill';
        var url = hl.url || '';
        var title = hl.title || 'No title';
        var source = hl.source || 'News';
        var date = hl.published_at || '';
        
        if (url) {
            headlinesHtml += '<a href="' + url + '" target="_blank" rel="noopener" class="news-headline-item ' + s + '">';
        } else {
            headlinesHtml += '<div class="news-headline-item ' + s + '">';
        }
        headlinesHtml += '<span class="news-sentiment-dot ' + s + '" title="' + s.charAt(0).toUpperCase() + s.slice(1) + '">' +
            '<i class="bi bi-' + sIcon + '"></i></span>' +
            '<span class="news-headline-text">' +
            '<span class="news-headline-title">' + escapeHtml(title) + '</span>' +
            '<span class="news-headline-meta">' +
            '<span class="news-source">' + escapeHtml(source) + '</span>' +
            (date ? '<span class="news-date">' + date + '</span>' : '') +
            '</span></span>' +
            '<span class="news-open-link"><i class="bi bi-box-arrow-up-right"></i></span>' +
            (url ? '</a>' : '</div>');
    }
    
    return '<div class="card mb-4 fade-in news-sentiment-card">' +
        '<div class="card-header">' +
        '<span><i class="bi bi-newspaper"></i> News Sentiment</span>' +
        '<div class="d-flex align-items-center gap-2">' +
        '<span class="sentiment-summary-badge ' + labelLower + '">' +
        '<i class="bi bi-' + labelIcon + '"></i> ' + label +
        '</span>' +
        '<span class="text-muted small">' + newsSentiment.article_count + ' articles</span>' +
        '</div></div>' +
        '<div class="card-body">' +
        '<div class="news-breakdown-row mb-3">' +
        '<div class="breakdown-item positive"><span class="breakdown-dot"></span><span class="breakdown-count">' + (breakdown.positive || 0) + '</span><span class="breakdown-label">Positive</span></div>' +
        '<div class="breakdown-item neutral"><span class="breakdown-dot"></span><span class="breakdown-count">' + (breakdown.neutral || 0) + '</span><span class="breakdown-label">Neutral</span></div>' +
        '<div class="breakdown-item negative"><span class="breakdown-dot"></span><span class="breakdown-count">' + (breakdown.negative || 0) + '</span><span class="breakdown-label">Negative</span></div>' +
        '<div class="breakdown-avg"><span class="text-muted small">Avg polarity: </span><span class="fw-bold" style="color:' + avgColor + ';">' + avgPol.toFixed(3) + '</span></div>' +
        '</div>' +
        '<div class="news-headlines-list">' + (headlinesHtml || '<div class="text-center py-3 text-muted small"><i class="bi bi-newspaper me-1"></i> No recent news headlines found</div>') + '</div>' +
        '<div class="news-footer"><small class="text-muted"><i class="bi bi-database me-1"></i>Powered by NewsAPI</small></div>' +
        '</div></div>';
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
    if (window.ESGMotion && window.ESGMotion.animateFadeUp) {
        window.ESGMotion.animateFadeUp(container.querySelector('.card'), { duration: 0.35, y: 10 });
    }
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
    if (window.ESGMotion && window.ESGMotion.animateFadeIn) {
        window.ESGMotion.animateFadeIn(container.querySelector('.loading-spinner'), { duration: 0.25 });
    }
}

function hideLoading() {
    const spinners = document.querySelectorAll('.loading-spinner');
    spinners.forEach(function(s) { s.classList.remove('active'); });
}

function initializeCharts() {
    if (typeof Chart !== 'undefined') {
        Chart.defaults.color = '#90caf9';
        Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.animation.duration = 750;
        Chart.defaults.animation.easing = 'easeOutQuart';
    }

    initializeESGRadarChart();
    initializeStockPriceChart();
    initializePerformanceChart();
    initializeConfusionMatrix();
    initializeESGDistributionChart();

    // Auto-mount Candlestick chart and XAI for prediction page if result is already in DOM
    var candleContainer = document.getElementById('tvCandleChart');
    var tickerEl = document.querySelector('.stock-ticker');
    var ticker = tickerEl ? tickerEl.textContent.trim() : null;
    if (!ticker) {
        var tickerInput = document.getElementById('ticker_text');
        var tickerSelect = document.getElementById('tickerSelect');
        if (tickerInput && tickerInput.value) ticker = tickerInput.value.trim();
        else if (tickerSelect && tickerSelect.value) ticker = tickerSelect.value.trim();
    }

    if (candleContainer && ticker) {
        _candleRendering = false;
        if (typeof renderCandlestickChart === 'function') {
            renderCandlestickChart(ticker, '3mo');
        }
    }
    if (ticker && document.getElementById('xaiCard')) {
        if (typeof renderXAI === 'function') {
            renderXAI(ticker);
        }
    }
    var gaugeCanvas = document.getElementById('confidenceGauge');
    if (gaugeCanvas) {
        var confValEl = document.querySelector('.confidence-value .number');
        var conf = confValEl ? parseFloat(confValEl.textContent) : 85;
        drawConfidenceGauge(isNaN(conf) ? 85 : conf);
    }
}

function drawConfidenceGauge(confidence) {
    const ctx = safeGetContext('confidenceGauge');
    if (!ctx) return;
    const size = 120;
    var canvas = document.getElementById('confidenceGauge');
    if (!canvas || typeof canvas.getContext !== 'function') return;
    canvas.width = size;
    canvas.height = size;
    const percentage = confidence / 100;
    const startAngle = Math.PI * 0.75;
    const endAngle = startAngle + (Math.PI * 1.5 * percentage);
    const cx = size / 2, cy = size / 2, r = size / 2 - 10;

    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();

    const color = confidence >= 80 ? '#00e676' : confidence >= 60 ? '#ffb300' : '#ff1744';
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI * 0.75, endAngle, false);
    ctx.strokeStyle = color;
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();
}

function initializeESGRadarChart() {
    var canvas = document.getElementById('esgRadarChart');
    if (!canvas) return;
    const envScore = parseFloat(canvas.getAttribute('data-env')) || 0;
    const socialScore = parseFloat(canvas.getAttribute('data-social')) || 0;
    const govScore = parseFloat(canvas.getAttribute('data-gov')) || 0;
    if (envScore === 0 && socialScore === 0 && govScore === 0) return;

    if (window._esgRadarChart) {
        window._esgRadarChart.destroy();
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const overall = (envScore + socialScore + govScore) / 3;

    window._esgRadarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Environmental', 'Social', 'Governance', 'Overall ESG'],
            datasets: [{
                label: 'ESG Dimensions',
                data: [envScore, socialScore, govScore, overall],
                backgroundColor: 'rgba(0, 230, 118, 0.18)',
                borderColor: '#00e676',
                borderWidth: 2,
                pointBackgroundColor: ['#2196F3', '#FF9800', '#9C27B0', '#00E676'],
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 8,
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                duration: 850,
                easing: 'easeOutCubic'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.r.toFixed(1) + ' / 100'; } }
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { stepSize: 20, color: '#64748b', backdropColor: 'transparent', font: { size: 9 } },
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    angleLines: { color: 'rgba(255, 255, 255, 0.08)' },
                    pointLabels: { color: '#e3f2fd', font: { size: 11, weight: '600' } }
                }
            }
        }
    });
}

function initializeStockPriceChart() {
    const ctx = safeGetContext('stockPriceChart');
    if (!ctx) return;

    if (window._stockPriceChart) {
        window._stockPriceChart.destroy();
    }

    var canvas = document.getElementById('stockPriceChart');
    if (!canvas) return;
    let prices = [], labels = [];
    const currency = canvas.getAttribute('data-currency') || '$';

    try {
        prices = JSON.parse(canvas.getAttribute('data-prices') || '[]');
        labels = JSON.parse(canvas.getAttribute('data-dates') || '[]');
    } catch (e) { return; }

    if (prices.length === 0) return;

    const sma10 = calculateSMA(prices, 10);
    const sma30 = calculateSMA(prices, 30);
    const isPositive = prices.length > 1 && prices[prices.length - 1] >= prices[0];
    const lineColor = isPositive ? '#00e676' : '#ff1744';

    var gradient;
    try {
        gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, isPositive ? 'rgba(0, 230, 118, 0.28)' : 'rgba(255, 23, 68, 0.28)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    } catch(e) { return; }

    window._stockPriceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Price',
                    data: prices,
                    borderColor: lineColor,
                    backgroundColor: gradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: lineColor,
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 2
                },
                {
                    label: 'SMA 10',
                    data: sma10,
                    borderColor: '#ffb300',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderDash: [5, 5]
                },
                {
                    label: 'SMA 30',
                    data: sma30,
                    borderColor: '#ab47bc',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderDash: [8, 4]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                duration: 850,
                easing: 'easeOutQuart'
            },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: '#90caf9', font: { size: 11, weight: '500' }, boxWidth: 12, padding: 15 }
                },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + currency + ctx.parsed.y.toFixed(2); } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)', display: false },
                    ticks: { color: '#64748b', maxTicksLimit: 10, font: { size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return currency + v.toFixed(0); } }
                }
            }
        }
    });
}

function initializePerformanceChart() {
    const ctx = safeGetContext('performanceChart');
    if (!ctx) return;

    var canvas = document.getElementById('performanceChart');
    if (!canvas) return;
    let modelData = {};
    try { modelData = JSON.parse(canvas.getAttribute('data-metrics') || '{}'); } catch (e) { return; }
    if (Object.keys(modelData).length === 0) return;

    const modelNames = Object.keys(modelData);
    const metrics = ['accuracy', 'precision', 'recall', 'f1_score'];
    const colors = ['rgba(0, 230, 118, 0.85)', 'rgba(33, 150, 243, 0.85)', 'rgba(255, 152, 0, 0.85)', 'rgba(156, 39, 176, 0.85)'];

    const datasets = metrics.map(function(m, i) {
        return {
            label: m.replace('_', ' ').toUpperCase(),
            data: modelNames.map(function(n) { return (modelData[n][m] * 100).toFixed(1); }),
            backgroundColor: colors[i],
            borderColor: colors[i].replace('0.85', '1'),
            borderWidth: 1.5,
            borderRadius: 6,
            hoverBorderColor: '#ffffff',
            hoverBorderWidth: 2
        };
    });

    new Chart(ctx, {
        type: 'bar',
        data: { labels: modelNames, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                duration: 800,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: { labels: { color: '#90caf9', font: { size: 11, weight: '500' }, boxWidth: 12, padding: 15 } },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.y + '%'; } }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#90caf9', font: { size: 11 } } },
                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return v + '%'; } } }
            }
        }
    });
}

function initializeConfusionMatrix() {
    const ctx = safeGetContext('confusionMatrixChart');
    if (!ctx) return;

    var canvas = document.getElementById('confusionMatrixChart');
    if (!canvas) return;
    let matrix = [];
    const labels = ['Sell', 'Buy'];
    try { matrix = JSON.parse(canvas.getAttribute('data-matrix') || '[]'); } catch (e) { return; }
    if (matrix.length === 0) return;

    const data = [];
    const maxVal = Math.max(...matrix.flat()) || 1;
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
                    return 'rgba(0, 230, 118, ' + (0.15 + 0.75 * (val / maxVal)) + ')';
                },
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1.5,
                borderRadius: 8,
                width: 65,
                height: 65
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                duration: 750,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        title: function(ctx) { return 'Predicted: ' + ctx[0].raw.x + ' | Actual: ' + ctx[0].raw.y; },
                        label: function(ctx) { return 'Instances: ' + ctx.raw.v; }
                    }
                }
            },
            scales: {
                x: { type: 'category', labels: labels, offset: true, grid: { display: false }, ticks: { color: '#90caf9', font: { size: 11, weight: '600' } }, title: { display: true, text: 'Predicted Signal', color: '#64748b', font: { size: 11 } } },
                y: { type: 'category', labels: labels, offset: true, grid: { display: false }, ticks: { color: '#90caf9', font: { size: 11, weight: '600' } }, title: { display: true, text: 'Actual Signal', color: '#64748b', font: { size: 11 } } }
            }
        }
    });
}

function initializeESGDistributionChart() {
    var canvas = document.getElementById('esgDistributionChart');
    if (!canvas) return;
    let esgData = [];
    try { esgData = JSON.parse(canvas.getAttribute('data-esg') || '[]'); } catch (e) { return; }
    if (!esgData || esgData.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const tickers = esgData.map(function(d) { return d.ticker; });
    const envScores = esgData.map(function(d) { return d.env; });
    const socialScores = esgData.map(function(d) { return d.social; });
    const govScores = esgData.map(function(d) { return d.gov; });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tickers,
            datasets: [
                { label: 'Environmental', data: envScores, backgroundColor: 'rgba(33, 150, 243, 0.85)', borderColor: '#2196F3', borderWidth: 1.5, borderRadius: 4, hoverBorderColor: '#ffffff' },
                { label: 'Social', data: socialScores, backgroundColor: 'rgba(255, 152, 0, 0.85)', borderColor: '#FF9800', borderWidth: 1.5, borderRadius: 4, hoverBorderColor: '#ffffff' },
                { label: 'Governance', data: govScores, backgroundColor: 'rgba(156, 39, 176, 0.85)', borderColor: '#9C27B0', borderWidth: 1.5, borderRadius: 4, hoverBorderColor: '#ffffff' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                duration: 800,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: { labels: { color: '#90caf9', font: { size: 11, weight: '500' }, boxWidth: 12, padding: 15 } },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12
                }
            },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#90caf9', font: { size: 10 } } },
                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748b', font: { size: 10 } } }
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

function formatCurrency(value, currency) {
    currency = currency || 'USD';
    if (currency === '₹') {
        return '₹' + value.toFixed(2);
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency, minimumFractionDigits: 2 }).format(value);
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
                response += 'Price: ' + (data.currency_symbol || '$') + data.current_price + ' | Trend: ' + data.trend + ' | Risk: ' + data.risk_level;
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
    if (window.ESGMotion && window.ESGMotion.animateFadeUp) {
        window.ESGMotion.animateFadeUp(div, { duration: 0.22, y: 8 });
    }
    messages.scrollTop = messages.scrollHeight;
}

function addBotMessage(text, isLoading) {
    const messages = document.getElementById('aiChatMessages');
    if (!messages) return;
    const div = document.createElement('div');
    div.className = 'chat-message bot' + (isLoading ? ' loading-msg' : '');
    div.innerHTML = '<div class="chat-bubble bot-bubble">' + (isLoading ? '<div class="spinner-border spinner-border-sm me-2" role="status"></div> Thinking...' : formatBotMessage(text)) + '</div>';
    messages.appendChild(div);
    if (window.ESGMotion && window.ESGMotion.animateFadeUp) {
        window.ESGMotion.animateFadeUp(div, { duration: 0.22, y: 8 });
    }
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

    if (window.ESGMotion && window.ESGMotion.animateFadeUp) {
        window.ESGMotion.animateFadeUp(toast, { duration: 0.28, y: 12 });
    }

    setTimeout(function() {
        var M = window.Motion;
        if (M && M.animate && !(window.ESGMotion && window.ESGMotion.isReducedMotion())) {
            var anim = M.animate(toast, { opacity: [1, 0], x: [0, 40] }, { duration: 0.25 });
            if (anim && anim.finished) {
                anim.finished.then(function() { toast.remove(); });
            } else {
                setTimeout(function() { toast.remove(); }, 260);
            }
        } else {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(function() { toast.remove(); }, 300);
        }
    }, 3500);
}

/* ============================================================
   REAL-TIME LIVE PRICE ENGINE (SINGLE SOURCE OF TRUTH)
   ============================================================ */
(function() {
    var stockState = {}; // { ticker: { basePrice, currentPrice, baseChange, currentChange, currencySymbol, history } }
    var activeTicker = null;
    var tickTimer = null;

    function detectCurrency(tkr, sym) {
        if (sym && sym !== '$') return sym;
        if (!tkr) return '$';
        tkr = tkr.toUpperCase();
        var indianList = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK',
            'LT', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'TITAN', 'BAJFINANCE', 'HCLTECH', 'SUNPHARMA', 'WIPRO', 'ULTRACEMCO',
            'TATAMOTORS', 'NTPC', 'POWERGRID', 'M&M', 'ONGC', 'NESTLEIND', 'JSWSTEEL', 'ADANIENT', 'GRASIM', 'COALINDIA',
            'TECHM', 'ADANIPORTS', 'TATASTEEL', 'DIVISLAB', 'BAJAJFINSV', 'DRREDDY', 'CIPLA', 'APOLLOHOSP', 'EICHERMOT', 'BRITANNIA',
            'BPCL', 'TATACONSUM', 'INDUSINDBK', 'HINDALCO', 'UPL', 'HEROMOTOCO', 'BAJAJ-AUTO', 'SHREECEM', 'ZOMATO', 'PAYTM'
        ];
        if (tkr.endsWith('.NS') || tkr.endsWith('.BO') || indianList.indexOf(tkr) >= 0) {
            return '₹';
        }
        return '$';
    }

    var ESGPriceEngine = {
        // Register or update baseline stock data
        registerStock: function(info) {
            if (!info || !info.ticker) return;
            var tkr = info.ticker.toUpperCase();
            var currP = parseFloat(info.currentPrice || info.price || info.basePrice || 100);
            var currChg = parseFloat(info.changePct != null ? info.changePct : (info.change != null ? info.change : 0));
            var sym = detectCurrency(tkr, info.currencySymbol || info.currency_symbol);

            if (!stockState[tkr]) {
                stockState[tkr] = {
                    ticker: tkr,
                    basePrice: currP,
                    currentPrice: currP,
                    baseChange: currChg,
                    currentChange: currChg,
                    currencySymbol: sym,
                    history: [currP]
                };
            } else {
                stockState[tkr].basePrice = currP;
                stockState[tkr].currentPrice = currP;
                stockState[tkr].baseChange = currChg;
                stockState[tkr].currentChange = currChg;
                stockState[tkr].currencySymbol = sym;
            }

            this.syncDOM(tkr, currP, currChg, null);
        },

        setActiveTicker: function(tkr) {
            if (tkr) {
                activeTicker = tkr.toUpperCase();
            }
        },

        getActiveTicker: function() {
            return activeTicker;
        },

        getPriceData: function(tkr) {
            return stockState[tkr ? tkr.toUpperCase() : ''] || null;
        },

        // Generate next realistic micro-fluctuation step (Brownian motion with mean-reverting drift)
        generateNextTick: function(tkr) {
            var s = stockState[tkr];
            if (!s || !s.currentPrice || s.currentPrice <= 0) return null;

            // Small realistic volatility (0.01% to 0.04% per tick)
            var volatility = 0.0004; 
            // Mean reversion pull if price drifts > 0.8% from basePrice
            var divergence = (s.currentPrice - s.basePrice) / s.basePrice;
            var meanReversion = -divergence * 0.20; 
            
            var randStep = (Math.random() - 0.495) * 2;
            var deltaPct = (randStep * volatility) + (meanReversion * 0.001);
            
            var oldPrice = s.currentPrice;
            var newPrice = Math.max(0.01, oldPrice * (1 + deltaPct));
            newPrice = Math.round(newPrice * 100) / 100;
            if (newPrice === oldPrice) {
                var microStep = (Math.random() > 0.5 ? 0.01 : -0.01);
                newPrice = Math.max(0.01, Math.round((oldPrice + microStep) * 100) / 100);
            }

            var tickDirection = newPrice >= oldPrice ? 'up' : 'down';
            
            // Calculate live percentage fluctuation cleanly relative to baseline
            var addChange = ((newPrice - s.basePrice) / s.basePrice) * 100;
            var newChange = s.baseChange + addChange;
            if (isNaN(newChange) || Math.abs(newChange) > 25) {
                newChange = s.baseChange;
            }
            newChange = Math.round(newChange * 100) / 100;

            s.currentPrice = newPrice;
            s.currentChange = newChange;
            s.history.push(newPrice);
            if (s.history.length > 50) s.history.shift();

            return {
                ticker: tkr,
                oldPrice: oldPrice,
                newPrice: newPrice,
                changePct: newChange,
                currencySymbol: s.currencySymbol,
                direction: tickDirection
            };
        },

        // Single dispatch that updates Top Bar, Predict Section, and Chart simultaneously
        syncDOM: function(tkr, price, changePct, direction) {
            var s = stockState[tkr];
            var sym = (s && s.currencySymbol) ? s.currencySymbol : detectCurrency(tkr, '$');
            var formattedPrice = sym + price.toFixed(2);
            var isPos = changePct >= 0;
            var arrow = isPos ? '\u25B2' : '\u25BC';
            var formattedChange = arrow + ' ' + (isPos ? '+' : '') + changePct.toFixed(2) + '%';

            // 1. UPDATE TOP BAR (All occurrences across duplicate tracks)
            var priceEls = document.querySelectorAll('#tp-' + tkr + ', .navbar-ticker-item[data-tkr="' + tkr + '"] .tick-price');
            var changeEls = document.querySelectorAll('#tc-' + tkr + ', .navbar-ticker-item[data-tkr="' + tkr + '"] .tick-change');
            
            priceEls.forEach(function(el) {
                el.textContent = formattedPrice;
                if (direction) {
                    el.classList.remove('flash-up', 'flash-down');
                    void el.offsetWidth;
                    el.classList.add(direction === 'up' ? 'flash-up' : 'flash-down');
                }
            });

            changeEls.forEach(function(el) {
                el.textContent = formattedChange;
                el.className = 'tick-change ' + (isPos ? 'pos' : 'neg');
            });

            // 2. UPDATE PREDICT SECTION (If this ticker is on display)
            var predictTickerEl = document.querySelector('.stock-price-card .stock-ticker, #predictTicker');
            var cardTkr = predictTickerEl ? predictTickerEl.textContent.trim().toUpperCase() : '';
            var isCardMatch = cardTkr === tkr || activeTicker === tkr;

            if (isCardMatch) {
                var predictPriceEls = document.querySelectorAll('[data-live-price="' + tkr + '"], #predictStockPrice, .stock-price-card .stock-price');
                var predictChangeEls = document.querySelectorAll('[data-live-change="' + tkr + '"], #predictStockChange, .stock-price-card .stock-change');

                predictPriceEls.forEach(function(el) {
                    var currSpan = el.querySelector('.currency');
                    if (currSpan) {
                        el.innerHTML = '<span class="currency">' + sym + '</span>' + price.toFixed(2);
                    } else {
                        el.textContent = formattedPrice;
                    }

                    if (direction) {
                        el.classList.remove('flash-up', 'flash-down');
                        void el.offsetWidth;
                        el.classList.add(direction === 'up' ? 'flash-up' : 'flash-down');
                    }
                });

                predictChangeEls.forEach(function(el) {
                    var biIcon = isPos ? 'arrow-up' : 'arrow-down';
                    el.innerHTML = '<i class="bi bi-' + biIcon + '"></i> ' + (isPos ? '+' : '') + changePct.toFixed(2) + '%';
                    el.className = 'stock-change ' + (isPos ? 'positive' : 'negative') + ' mb-2';
                });
            }

            // 3. UPDATE MODAL (If quick prediction modal is open for this ticker)
            var modalPriceEl = document.querySelector('#modalPrice[data-live-price="' + tkr + '"]');
            var modalChangeEl = document.querySelector('#modalChange[data-live-change="' + tkr + '"]');
            if (modalPriceEl) modalPriceEl.textContent = formattedPrice;
            if (modalChangeEl) {
                modalChangeEl.textContent = (isPos ? '+' : '') + changePct.toFixed(2) + '%';
                modalChangeEl.className = 'fs-6 ' + (isPos ? 'text-success' : 'text-danger');
            }

            // 4. UPDATE CHART (If chart is currently displaying this ticker)
            if (window._activeCandleSeries && window._activeCandleTicker === tkr && window._activeCandleData && window._activeCandleData.length > 0) {
                var lastBarIndex = window._activeCandleData.length - 1;
                var lastBar = window._activeCandleData[lastBarIndex];
                if (lastBar) {
                    var updatedHigh = Math.max(lastBar.h != null ? lastBar.h : (lastBar.high || price), price);
                    var updatedLow = Math.min(lastBar.l != null ? lastBar.l : (lastBar.low || price), price);
                    lastBar.h = updatedHigh;
                    lastBar.l = updatedLow;
                    lastBar.c = price;

                    var timeVal = typeof lastBar.t === 'number' ? Math.floor(lastBar.t) : (lastBar.time || lastBar.t);
                    
                    try {
                        window._activeCandleSeries.update({
                            time: timeVal,
                            open: lastBar.o != null ? lastBar.o : lastBar.open,
                            high: updatedHigh,
                            low: updatedLow,
                            close: price
                        });
                    } catch(e) {}

                    var priceInfoEl = document.getElementById('candlePriceInfo');
                    if (priceInfoEl && typeof window._formatPriceSummary === 'function') {
                        window._formatPriceSummary({
                            open: lastBar.o != null ? lastBar.o : lastBar.open,
                            high: updatedHigh,
                            low: updatedLow,
                            close: price,
                            volume: lastBar.v || lastBar.volume
                        });
                    }
                }
            }
        },

        // Trigger one tick for a stock
        tick: function(tkr) {
            var tickResult = this.generateNextTick(tkr);
            if (tickResult) {
                this.syncDOM(tickResult.ticker, tickResult.newPrice, tickResult.changePct, tickResult.direction);
            }
        },

        // Start the continuous realistic live fluctuation loop
        startLoop: function() {
            if (tickTimer) clearInterval(tickTimer);

            var self = this;
            tickTimer = setInterval(function() {
                var tickers = Object.keys(stockState);
                if (tickers.length === 0) return;

                // Priority 1: Always tick the active/predicted stock if set
                if (activeTicker && stockState[activeTicker]) {
                    self.tick(activeTicker);
                }

                // Priority 2: Stagger tick other tickers across Indian + US stocks
                var otherTickers = tickers.filter(function(t) { return t !== activeTicker; });
                if (otherTickers.length > 0) {
                    var randomCount = Math.min(3, otherTickers.length);
                    for (var i = 0; i < randomCount; i++) {
                        var randTkr = otherTickers[Math.floor(Math.random() * otherTickers.length)];
                        self.tick(randTkr);
                    }
                }
            }, 2200);
        }
    };

    window.ESGPriceEngine = ESGPriceEngine;
    ESGPriceEngine.startLoop();
})();

/* ============================================================
   LIVE TICKER
   ============================================================ */
function initializeTicker() {
    var track = document.getElementById('tickerItems');
    if (!track) return;
    var tickers = [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META',
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'WIPRO', 'TATAMOTORS', 'SBIN', 'BHARTIARTL', 'ITC', 'LT'
    ];

    var DEFAULT_PRICES = {
        'AAPL': { price: 315.20, change: 0.20, sym: '$' },
        'MSFT': { price: 510.61, change: 1.10, sym: '$' },
        'NVDA': { price: 219.28, change: -3.82, sym: '$' },
        'GOOGL': { price: 338.83, change: -0.53, sym: '$' },
        'AMZN': { price: 261.35, change: 1.99, sym: '$' },
        'TSLA': { price: 364.90, change: 2.84, sym: '$' },
        'META': { price: 572.45, change: 0.24, sym: '$' },
        'RELIANCE': { price: 1277.00, change: -0.78, sym: '₹' },
        'TCS': { price: 2399.30, change: 2.45, sym: '₹' },
        'HDFCBANK': { price: 709.00, change: -1.57, sym: '₹' },
        'INFY': { price: 1133.80, change: -0.89, sym: '₹' },
        'ICICIBANK': { price: 1454.00, change: 2.19, sym: '₹' },
        'WIPRO': { price: 184.50, change: 1.96, sym: '₹' },
        'TATAMOTORS': { price: 980.50, change: 1.80, sym: '₹' },
        'SBIN': { price: 1060.00, change: 1.19, sym: '₹' },
        'BHARTIARTL': { price: 1811.90, change: -3.75, sym: '₹' },
        'ITC': { price: 255.50, change: -3.95, sym: '₹' },
        'LT': { price: 4044.90, change: -0.02, sym: '₹' }
    };

    var lastPrices = {};

    // Try to restore cached prices from sessionStorage for instant display
    var cachedTickerData = null;
    try {
        var stored = sessionStorage.getItem('esg-ticker-prices');
        if (stored) {
            cachedTickerData = JSON.parse(stored);
        }
    } catch(e) {/* ignore */}

    // Pre-populate ESGPriceEngine with all baseline prices immediately
    tickers.forEach(function(t) {
        var cached = (cachedTickerData && cachedTickerData[t]) ? cachedTickerData[t] : null;
        var def = DEFAULT_PRICES[t] || { price: 150.0, change: 0.5, sym: '$' };
        var p = cached ? cached.price : def.price;
        var c = cached ? cached.change : def.change;
        var sym = cached ? (cached.currency_symbol || def.sym) : def.sym;
        
        lastPrices[t] = p;

        if (window.ESGPriceEngine) {
            window.ESGPriceEngine.registerStock({
                ticker: t,
                basePrice: p,
                currentPrice: p,
                changePct: c,
                currencySymbol: sym
            });
        }
    });

    var html = tickers.map(function(t) {
        var pData = (window.ESGPriceEngine && window.ESGPriceEngine.getPriceData(t)) || null;
        var def = DEFAULT_PRICES[t] || { price: 150.0, change: 0.5, sym: '$' };
        var priceVal = pData ? pData.currentPrice : def.price;
        var chgVal = pData ? pData.currentChange : def.change;
        var symVal = pData ? pData.currencySymbol : def.sym;

        var priceStr = symVal + priceVal.toFixed(2);
        var isPos = chgVal >= 0;
        var arrow = isPos ? '\u25B2' : '\u25BC';
        var changeStr = arrow + ' ' + (isPos ? '+' : '') + chgVal.toFixed(2) + '%';
        var changeClass = isPos ? 'pos' : 'neg';

        return '<span class="navbar-ticker-item" data-tkr="' + t + '">' +
            '<span class="tick-symbol">' + t + '</span>' +
            '<span class="tick-price">' + priceStr + '</span>' +
            '<span class="tick-change ' + changeClass + '">' + changeStr + '</span>' +
        '</span>';
    }).join('');

    // Duplicate content for smooth infinite seamless marquee scrolling
    track.innerHTML = html + html;

    function updateTickerPrices() {
        var url = '/api/ticker/prices?tickers=' + tickers.join(',');
        return fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                try {
                    sessionStorage.setItem('esg-ticker-prices', JSON.stringify(data));
                } catch(e) {/* ignore */}

                tickers.forEach(function(t) {
                    if (!data[t]) return;
                    if (window.ESGPriceEngine) {
                        window.ESGPriceEngine.registerStock({
                            ticker: t,
                            basePrice: data[t].price,
                            currentPrice: data[t].price,
                            changePct: data[t].change,
                            currencySymbol: data[t].currency_symbol || (t.indexOf('.NS') >= 0 || (DEFAULT_PRICES[t] && DEFAULT_PRICES[t].sym === '₹') ? '₹' : '$')
                        });
                    }
                });

                if (window._activePredictionTicker && window.ESGPriceEngine) {
                    window.ESGPriceEngine.setActiveTicker(window._activePredictionTicker);
                    window.ESGPriceEngine.registerStock({
                        ticker: window._activePredictionTicker,
                        basePrice: window._activePredictionPrice,
                        currentPrice: window._activePredictionPrice,
                        changePct: window._activePredictionChange,
                        currencySymbol: window._activePredictionCurrency
                    });
                }
            })
            .catch(function() {/* silent */});
    }

    if (window._activePredictionTicker && window.ESGPriceEngine) {
        window.ESGPriceEngine.setActiveTicker(window._activePredictionTicker);
        window.ESGPriceEngine.registerStock({
            ticker: window._activePredictionTicker,
            basePrice: window._activePredictionPrice,
            currentPrice: window._activePredictionPrice,
            changePct: window._activePredictionChange,
            currencySymbol: window._activePredictionCurrency
        });
    }

    updateTickerPrices();

    if (_tickerInterval) {
        clearInterval(_tickerInterval);
    }
    _tickerInterval = setInterval(updateTickerPrices, 30000);
}

/* ============================================================
   NEWS ALERTS / NOTIFICATIONS
   ============================================================ */
var _newsAlertInterval = null;
var _lastAlertState = '';  // JSON string to detect changes

function initializeNewsAlerts() {
    // Skip if not logged in (no client_id check)
    if (!document.querySelector('.sidebar-user')) return;
    
    // Inject notification bell into the navbar if the target exists
    var navbarRight = document.querySelector('.top-navbar-right');
    if (!navbarRight) return;
    
    // Only inject once
    if (document.getElementById('notificationBellWrap')) return;
    
    var bellHtml = '<div class="notification-bell-wrap" id="notificationBellWrap">' +
        '<button class="notification-bell" id="notificationBell" title="News Alerts">' +
        '<i class="bi bi-bell"></i>' +
        '<span class="notification-badge" id="notificationBadge" style="display:none;">0</span>' +
        '</button>' +
        '<div class="notification-dropdown" id="notificationDropdown">' +
        '<div class="notification-dropdown-header">' +
        '<span>News Alerts</span>' +
        '<button class="notification-mark-read" id="markAlertsRead">Mark all read</button>' +
        '</div>' +
        '<div class="notification-dropdown-body" id="notificationDropdownBody">' +
        '<div class="notification-empty">No alerts yet.</div>' +
        '</div></div></div>';
    
    // Insert before the datetime-display
    var dtDisplay = navbarRight.querySelector('.datetime-display');
    if (dtDisplay) {
        dtDisplay.insertAdjacentHTML('beforebegin', bellHtml);
    } else {
        navbarRight.insertAdjacentHTML('beforeend', bellHtml);
    }
    
    // Wire up bell click toggle
    var bellBtn = document.getElementById('notificationBell');
    var dropdown = document.getElementById('notificationDropdown');
    if (bellBtn && dropdown) {
        bellBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            dropdown.classList.toggle('show');
            if (dropdown.classList.contains('show')) {
                loadNotificationHistory();
            }
        });
        document.addEventListener('click', function() {
            dropdown.classList.remove('show');
        });
        dropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
    
    // Wire up "Mark all read"
    var markBtn = document.getElementById('markAlertsRead');
    if (markBtn) {
        markBtn.addEventListener('click', function() {
            fetch('/api/news/alerts/mark-read', { method: 'POST' })
                .then(function() {
                    updateNotificationBadge(0);
                    loadNotificationHistory();
                })
                .catch(function() {});
        });
    }
    
    // Initial check
    checkNewsAlerts();
    
    // Poll every 90 seconds
    if (_newsAlertInterval) clearInterval(_newsAlertInterval);
    _newsAlertInterval = setInterval(checkNewsAlerts, 90000);
}

function checkNewsAlerts() {
    // Skip if bell isn't on the page yet (e.g., API call during SPA navigation)
    if (!document.getElementById('notificationBell')) return;
    
    fetch('/api/news/alerts')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.unread_count !== undefined) {
                updateNotificationBadge(data.unread_count);
            }
            
            var newAlerts = data.alerts || [];
            if (newAlerts.length > 0) {
                // Compare with last state to avoid duplicate toast notifications
                var stateStr = JSON.stringify(newAlerts);
                if (stateStr !== _lastAlertState) {
                    _lastAlertState = stateStr;
                    newAlerts.forEach(function(a) {
                        var icon = a.alert_type === 'positive' ? '📈' : '📉';
                        var msg = icon + ' ' + a.ticker + ' news ' + a.sentiment_label.toLowerCase() + 
                            ' (' + (a.avg_polarity || 0).toFixed(2) + ') — ' + a.article_count + ' articles';
                        if (a.headlines && a.headlines.length > 0) {
                            msg += ' — ' + a.headlines[0].title;
                        }
                        showToast(msg, a.alert_type === 'positive' ? 'success' : 'error');
                    });
                }
            }
        })
        .catch(function() {});
}

function updateNotificationBadge(count) {
    var badge = document.getElementById('notificationBadge');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = 'flex';
        // Pulse animation
        badge.classList.remove('pulse');
        void badge.offsetWidth;
        badge.classList.add('pulse');
    } else {
        badge.style.display = 'none';
    }
}

function loadNotificationHistory() {
    var body = document.getElementById('notificationDropdownBody');
    if (!body) return;
    fetch('/api/news/alerts/history?limit=15')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var alerts = data.alerts || [];
            if (alerts.length === 0) {
                body.innerHTML = '<div class="notification-empty">No alerts yet. Enable alerts on watched stocks from the Dashboard.</div>';
                return;
            }
            var html = '';
            alerts.forEach(function(a) {
                var icon = a.sentiment_label === 'Positive' ? '📈' : '📉';
                var color = a.sentiment_label === 'Positive' ? '#4caf50' : '#f44336';
                html += '<div class="notification-item">' +
                    '<span class="notification-item-icon" style="color:' + color + ';">' + icon + '</span>' +
                    '<span class="notification-item-text">' +
                    '<strong>' + a.ticker + '</strong> news ' + a.sentiment_label.toLowerCase() +
                    ' <span class="text-muted small">(' + (a.avg_polarity || 0).toFixed(2) + ')</span>' +
                    '</span>' +
                    '<span class="notification-item-time">' + (a.created_at || '').split(' ')[0] + '</span>' +
                    '</div>';
            });
            body.innerHTML = html;
        })
        .catch(function() {
            body.innerHTML = '<div class="notification-empty">Could not load alerts.</div>';
        });
}

/* ============================================================
   SPA ROUTER
   ============================================================ */
function initializeRouter() {
    // Intercept all sidebar nav-item clicks for SPA navigation
    document.addEventListener('click', function(e) {
        var link = e.target.closest('.nav-item');
        if (!link) return;

        var href = link.getAttribute('href');
        // Skip external links, theme toggle, javascript: links, and links with target
        if (!href || href === '#' || href.startsWith('javascript:') || link.getAttribute('onclick') || link.getAttribute('target')) return;

        e.preventDefault();
        if (window.closeSidebar) window.closeSidebar(true);
        navigateTo(href);
    });

    // Handle browser back/forward buttons
    window.addEventListener('popstate', function(e) {
        if (window.closeSidebar) window.closeSidebar(true);
        if (e.state && e.state.path) {
            loadPage(e.state.path, false);
        }
    });
}

function navigateTo(path, addToHistory) {
    if (window.closeSidebar) window.closeSidebar(true);
    if (addToHistory !== false) {
        history.pushState({path: path}, '', path);
    }
    loadPage(path);
}

function prefetchPages() {
    // Collect unique nav links from the sidebar (skip theme toggle)
    var links = [];
    document.querySelectorAll('.nav-item').forEach(function(item) {
        var href = item.getAttribute('href');
        if (!href || href === '#' || href.startsWith('javascript:') || item.getAttribute('onclick')) return;
        if (href === window.location.pathname || href === window.location.href) return;  // skip current page
        if (_pageCache[href]) return;  // already cached
        if (links.indexOf(href) === -1) links.push(href);
    });
    // Prefetch each link in the background (with low priority)
    links.forEach(function(url) {
        // Don't cache dynamic pages with inline scripts - always fetch fresh
        if (url.indexOf('/dashboard') === 0 || url.indexOf('/predict') === 0 || url.indexOf('/profile') === 0 || url.indexOf('/portfolio') === 0 || url.indexOf('/admin/health') === 0 || url.indexOf('/alerts') === 0) {
            return;
        }
        if (_prefetchInFlight[url]) return;  // already being fetched
        _prefetchInFlight[url] = true;

        var doFetch = function() {
            fetch(url).then(function(r) {
                if (!r.ok) return;
                return r.text();
            }).then(function(html) {
                if (html) _pageCache[url] = html;
            }).catch(function() {/* silent */}).then(function() {
                delete _prefetchInFlight[url];
            });
        };

        if (window.requestIdleCallback) {
            window.requestIdleCallback(doFetch, {timeout: 3000});
        } else {
            setTimeout(doFetch, 500);
        }
    });
}

function showLoadingBar() {
    var bar = document.getElementById('loadingBar');
    if (!bar) return;
    bar.classList.remove('complete');
    bar.style.width = '0%';
    // Force reflow to restart animation
    void bar.offsetWidth;
    bar.classList.add('active');
    // Animate to 60% to indicate progress
    setTimeout(function() { bar.style.width = '60%'; }, 50);
}

function hideLoadingBar() {
    var bar = document.getElementById('loadingBar');
    if (!bar) return;
    // Snap to 100% then fade out
    bar.classList.add('complete');
    bar.style.width = '100%';
    setTimeout(function() {
        bar.classList.remove('active', 'complete');
        bar.style.width = '0%';
    }, 550);
}

function loadPage(path) {
    if (window.closeSidebar) window.closeSidebar(true);
    var container = document.querySelector('.main-content');
    if (!container) {
        // Fallback to full page load if no SPA container found
        window.location.href = path;
        return;
    }

    // Check if this page was already prefetched
    var cachedHtml = _pageCache[path];
    delete _pageCache[path];  // consume the cache

    // Start the leave animation (fade out) and show loading bar
    container.classList.remove('page-enter');
    container.classList.add('page-leave');
    showLoadingBar();

    // Use cached HTML immediately if available; otherwise fetch
    var fetchPromise;
    if (cachedHtml) {
        fetchPromise = Promise.resolve(cachedHtml);
    } else {
        fetchPromise = fetch(path).then(function(r) {
            if (!r.ok) throw new Error('Page load failed');
            return r.text();
        });
    }

    return fetchPromise.then(function(html) {
            // Parse the fetched HTML
            var parser = new DOMParser();
            var doc = parser.parseFromString(html, 'text/html');

            // Update page title
            var title = doc.querySelector('title');
            if (title && title.textContent) {
                document.title = title.textContent;
            }

            // Extract the main-content from the fetched page
            var newContent = doc.querySelector('.main-content');
            if (!newContent) {
                // Fallback: couldn't find main-content, do full reload
                window.location.href = path;
                return;
            }

            // Remove leave animation and replace content.
            // Add enter FIRST so there's no opacity flash between leave and enter.
            container.classList.add('page-enter');
            container.classList.remove('page-leave');
            container.innerHTML = newContent.innerHTML;

            // Re-execute any <script> tags sequentially (external scripts must finish before inline scripts run).
            var scripts = container.querySelectorAll('script');
            function executeScripts(index) {
                if (index >= scripts.length) {
                    // All scripts done
                    afterScripts();
                    return;
                }
                var oldScript = scripts[index];
                var newScript = document.createElement('script');
                if (oldScript.src) {
                    newScript.src = oldScript.src;
                    newScript.async = false;
                    newScript.onload = function() { executeScripts(index + 1); };
                    newScript.onerror = function() { executeScripts(index + 1); };
                    oldScript.parentNode.replaceChild(newScript, oldScript);
                } else {
                    var content = oldScript.textContent;
                    if (document.readyState !== 'loading' && content.indexOf('DOMContentLoaded') !== -1) {
                        content = '(function(){ var _origAdd = document.addEventListener.bind(document);' +
                            'document.addEventListener = function(e, fn) {' +
                            'if(e==="DOMContentLoaded"||e==="load"){fn()}' +
                            'else{_origAdd(e,fn)}};' +
                            content + ';' +
                            'document.addEventListener = _origAdd;' +
                            '})();';
                    }
                    newScript.textContent = content;
                    oldScript.parentNode.replaceChild(newScript, oldScript);
                    executeScripts(index + 1);
                }
            }
            function afterScripts() {
                hideLoadingBar();
                if (window.closeSidebar) window.closeSidebar(true);
                setTimeout(function() {
                    initializePageContent();
                    initializeTicker();
                    prefetchPages();
                    window.scrollTo({top: 0, behavior: 'smooth'});
                }, 0);
                setTimeout(function() {
                    container.classList.remove('page-enter');
                }, 400);
            }
            executeScripts(0);
        })
        .catch(function() {
            hideLoadingBar();
            container.classList.remove('page-leave');
            // Fallback to full page load on error
            window.location.href = path;
        });
}

/* ============================================================
   TRADINGVIEW LIGHTWEIGHT CANDLESTICK CHART
   ============================================================ */
var _candleResizeHandler = null;
var _candleRendering = false;
var _candleGen = 0;
function renderCandlestickChart(ticker, timeframe) {
    if (typeof LightweightCharts === 'undefined') {
        _candleRendering = false;
        return;
    }
    if (_candleRendering) return; // Guard against concurrent renders
    _candleRendering = true;
    _candleGen++; // Increment generation counter to invalidate stale callbacks
    var myGen = _candleGen;
    
    var container = document.getElementById('tvCandleChart');
    if (!container) { _candleRendering = false; return; }
    
    // Safety timeout: reset rendering guard after 30s regardless of what happens
    var _renderTimer = setTimeout(function() {
        if (myGen === _candleGen) {
            _candleRendering = false;
        }
    }, 30000);
    
    // Ensure container has a valid width before creating chart
    if (container.clientWidth <= 0) { container.style.width = '100%'; }
    // Also ensure height is set
    if (container.clientHeight <= 0) { container.style.minHeight = '350px'; }
    
    // Clean up old resize handler
    if (_candleResizeHandler) {
        window.removeEventListener('resize', _candleResizeHandler);
        _candleResizeHandler = null;
    }
    
    container.innerHTML = '';
    var volContainer = document.getElementById('tvVolumeChart');
    if (volContainer) volContainer.innerHTML = '';
    
    var isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    
    var candleChart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: isDark ? '#90caf9' : '#4a5568',
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            fontSize: 11
        },
        grid: {
            vertLines: { color: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)' },
            horzLines: { color: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {
                color: 'rgba(0, 230, 118, 0.5)',
                width: 1,
                style: LightweightCharts.LineStyle.Dashed,
                labelBackgroundColor: '#0e223d',
            },
            horzLine: {
                color: 'rgba(0, 230, 118, 0.5)',
                width: 1,
                style: LightweightCharts.LineStyle.Dashed,
                labelBackgroundColor: '#0e223d',
            },
        },
        rightPriceScale: {
            borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
            scaleMargins: { top: 0.08, bottom: 0.08 },
            alignLabels: true,
        },
        timeScale: {
            borderColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)',
            timeVisible: true,
            secondsVisible: false,
        },
        width: container.clientWidth,
        height: 380,
    });
    
    var volumeChart = null;
    if (volContainer) {
        volumeChart = LightweightCharts.createChart(volContainer, {
            layout: { background: { type: 'solid', color: 'transparent' }, textColor: 'transparent' },
            grid: { vertLines: { visible: false }, horzLines: { visible: false } },
            rightPriceScale: { visible: false },
            timeScale: { visible: false },
            handleScroll: false, handleScale: false,
            width: container.clientWidth, height: 80,
        });
        candleChart.timeScale().subscribeVisibleTimeRangeChange(function(range) {
            if (volumeChart) volumeChart.timeScale().setVisibleRange(range);
        });
    }
    
    var candleSeries = candleChart.addCandlestickSeries({
        upColor: '#00e676',
        downColor: '#ff1744',
        borderDownColor: '#ff1744',
        borderUpColor: '#00e676',
        wickDownColor: '#ff1744',
        wickUpColor: '#00e676',
    });
    
    var volumeSeries = null;
    if (volumeChart) {
        volumeSeries = volumeChart.addHistogramSeries({
            color: 'rgba(0, 230, 118, 0.45)',
            priceFormat: { type: 'volume' },
        });
    }
    
    var sma10Series = candleChart.addLineSeries({
        color: '#ffb300',
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
        title: 'SMA 10',
    });
    var sma30Series = candleChart.addLineSeries({
        color: '#ab47bc',
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
        title: 'SMA 30',
        lineStyle: LightweightCharts.LineStyle.Dashed,
    });
    
    var priceInfoEl = document.getElementById('candlePriceInfo');
    if (priceInfoEl) priceInfoEl.textContent = 'Loading historical series...';
    
    var period = timeframe || '1y';
    fetch('/api/candlestick/' + ticker + '?period=' + period, { credentials: 'same-origin', redirect: 'error' })
        .then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + r.statusText);
            return r.json();
        })
        .then(function(data) {
            if (_candleGen !== myGen) { _candleRendering = false; return; }
            var candleContainer = document.getElementById('tvCandleChart');
            if (!candleContainer || candleContainer.children.length === 0) {
                _candleRendering = false;
                return;
            }
            if (data.error) {
                _candleRendering = false;
                if (priceInfoEl) priceInfoEl.textContent = 'Chart unavailable';
                return;
            }
            var candleData = data.data || [];
            if (candleData.length === 0) return;
            
            var validData = candleData.filter(function(c) {
                var validTime = c && c.t != null && c.t !== '' && (typeof c.t === 'number' || typeof c.t === 'string');
                return validTime &&
                    typeof c.o === 'number' && isFinite(c.o) &&
                    typeof c.h === 'number' && isFinite(c.h) &&
                    typeof c.l === 'number' && isFinite(c.l) &&
                    typeof c.c === 'number' && isFinite(c.c) &&
                    typeof c.v === 'number' && isFinite(c.v);
            });
            if (validData.length === 0) {
                if (priceInfoEl) priceInfoEl.textContent = 'No valid data available';
                return;
            }
            
            var fmtCandles = validData.map(function(c) {
                var time = typeof c.t === 'number' ? Math.floor(c.t) : c.t;
                return { time: time, open: c.o, high: c.h, low: c.l, close: c.c };
            });
            var fmtVolume = validData.map(function(c, i) {
                var up = i === 0 || c.c >= validData[i-1].c;
                return {
                    time: typeof c.t === 'number' ? Math.floor(c.t) : c.t,
                    value: c.v,
                    color: up ? 'rgba(0,230,118,0.5)' : 'rgba(255,23,68,0.5)'
                };
            });
            
            function calcSMA(d, p) {
                var r = [];
                for (var i = 0; i < d.length; i++) {
                    if (i < p - 1) continue;
                    var s = 0;
                    for (var j = 0; j < p; j++) s += d[i-j].c;
                    r.push({ time: d[i].t, value: s / p });
                }
                return r;
            }
            
            try { candleSeries.setData(fmtCandles); } catch(e) { console.warn('Candle setData error:', e); }
            if (volumeSeries) {
                try { volumeSeries.setData(fmtVolume); } catch(e) { console.warn('Volume setData error:', e); }
            }
            try { sma10Series.setData(calcSMA(validData, 10)); } catch(e) { console.warn('SMA10 setData error:', e); }
            try { sma30Series.setData(calcSMA(validData, 30)); } catch(e) { console.warn('SMA30 setData error:', e); }
            
            if (data.patterns && data.patterns.length > 0) {
                var markers = data.patterns.slice(0,5).filter(function(p) {
                    return p && p.date && p.pattern && p.signal;
                }).map(function(p) {
                    var b = p.signal.indexOf('Bull') >= 0 || p.signal.indexOf('Up') >= 0;
                    return {
                        time: p.date, position: b ? 'belowBar' : 'aboveBar',
                        color: b ? '#00e676' : '#ff1744',
                        shape: b ? 'arrowUp' : 'arrowDown', text: p.pattern || ''
                    };
                });
                try { candleSeries.setMarkers(markers); } catch(e) { console.warn('Markers error:', e); }
                var pb = document.getElementById('candlePatternBadge');
                if (pb) pb.innerHTML = '<span class="badge bg-info" style="font-size:0.6rem;">Patterns: ' + data.patterns.length + '</span>';
                var pl = document.getElementById('candlePatternList');
                if (pl) pl.textContent = data.patterns.slice(-2).map(function(p) { return p.pattern; }).join(' | ');
            }
            
            // Format default summary
            var last = validData[validData.length-1];
            function formatPriceSummary(bar, timeLabel) {
                if (!priceInfoEl || !bar) return;
                var chg = ((bar.close - bar.open) / bar.open * 100).toFixed(2);
                var isPos = chg >= 0;
                var dateStr = timeLabel ? '<span class="text-secondary me-2">[' + timeLabel + ']</span>' : '';
                priceInfoEl.innerHTML = dateStr +
                    'O: <span class="text-white fw-bold">' + bar.open.toFixed(2) + '</span> ' +
                    'H: <span class="text-white fw-bold">' + bar.high.toFixed(2) + '</span> ' +
                    'L: <span class="text-white fw-bold">' + bar.low.toFixed(2) + '</span> ' +
                    'C: <span class="text-white fw-bold">' + bar.close.toFixed(2) + '</span> ' +
                    '<span class="badge ' + (isPos ? 'bg-success' : 'bg-danger') + ' ms-1">' + (isPos ? '+' : '') + chg + '%</span>' +
                    (bar.volume ? ' <span class="text-secondary ms-2">Vol: ' + (bar.volume/1000000).toFixed(1) + 'M</span>' : '');
            }

            // Expose active candlestick references to ESGPriceEngine for live continuous chart updates
            window._activeCandleSeries = candleSeries;
            window._activeCandleChart = candleChart;
            window._activeCandleData = validData;
            window._activeCandleTicker = ticker.toUpperCase();
            window._formatPriceSummary = formatPriceSummary;

            if (window.ESGPriceEngine) {
                window.ESGPriceEngine.setActiveTicker(ticker);
                var pData = window.ESGPriceEngine.getPriceData(ticker);
                if (pData && pData.currentPrice) {
                    window.ESGPriceEngine.syncDOM(ticker.toUpperCase(), pData.currentPrice, pData.currentChange, null);
                }
            }

            if (last) {
                formatPriceSummary({ open: last.o, high: last.h, low: last.l, close: last.c, volume: last.v });
            }

            // Real-Time Crosshair Subscription
            candleChart.subscribeCrosshairMove(function(param) {
                if (!param.point || !param.time) {
                    if (last) formatPriceSummary({ open: last.o, high: last.h, low: last.l, close: last.c, volume: last.v });
                    return;
                }
                var candleDataPoint = param.seriesData.get(candleSeries);
                if (candleDataPoint) {
                    var volVal = volumeSeries ? param.seriesData.get(volumeSeries) : null;
                    var timeStr = typeof param.time === 'object' ? (param.time.year + '-' + param.time.month + '-' + param.time.day) : String(param.time);
                    formatPriceSummary({
                        open: candleDataPoint.open,
                        high: candleDataPoint.high,
                        low: candleDataPoint.low,
                        close: candleDataPoint.close,
                        volume: volVal ? volVal.value : null
                    }, timeStr);
                }
            });
            
            try { candleChart.timeScale().fitContent(); } catch(e) { console.warn('fitContent error:', e); }
        })
        .catch(function(err) { 
            if (priceInfoEl) priceInfoEl.textContent = 'Chart unavailable';
            console.error('Candlestick fetch error:', err);
        })
        .finally(function() {
            _candleRendering = false;
        });
    
    _candleResizeHandler = function() {
        var w = container.clientWidth;
        candleChart.applyOptions({ width: w });
        if (volumeChart) volumeChart.applyOptions({ width: w });
    };
    window.addEventListener('resize', _candleResizeHandler);
}

// Timeframe switching with smooth transition
if (!window._candleTimeframeHandler) {
    window._candleTimeframeHandler = true;
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.candle-timeframe');
        if (!btn) return;
        document.querySelectorAll('.candle-timeframe').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var container = document.getElementById('tvCandleChart');
        if (container) {
            container.classList.add('chart-fade-swap');
            setTimeout(function() { container.classList.remove('chart-fade-swap'); }, 300);
        }
        var ticker = document.getElementById('tickerSelect');
        if (ticker && ticker.value) renderCandlestickChart(ticker.value, btn.getAttribute('data-tf'));
    });
}

/* ============================================================
   PARTICLE BACKGROUND
   ============================================================ */
function initializeParticles() {
    const ctx = safeGetContext('particle-canvas');
    if (!ctx) return;

    var canvas = document.getElementById('particle-canvas');
    if (!canvas) return;
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

/* ============================================================
   PORTFOLIO FUNCTIONS
   ============================================================ */
function showBuyModal() {
    var overlay = document.getElementById('buyModalOverlay');
    if (overlay) overlay.style.display = 'flex';
}
/* ============================================================
   PORTFOLIO - ADD HOLDING MODAL
   ============================================================ */
var _modalLivePrice = 0;
var _modalCurrency = '$';

function closeBuyModal() {
    var overlay = document.getElementById('buyModalOverlay');
    if (overlay) {
        if (window.ESGMotion && window.ESGMotion.animateModalClose) {
            window.ESGMotion.animateModalClose(overlay, resetModal);
        } else {
            overlay.style.display = 'none';
            resetModal();
        }
    } else {
        resetModal();
    }
}

function resetModal() {
    document.getElementById('buyPrice').value = '';
    document.getElementById('buyAmount').value = '';
    document.getElementById('calcShares').textContent = '--';
    document.getElementById('previewPrice').textContent = '$0.00';
    document.getElementById('previewTotal').textContent = '$0.00';
    document.getElementById('previewFees').textContent = '$0.00';
    document.getElementById('buyConfirmBtn').disabled = true;
    var preview = document.getElementById('investmentPreview');
    if (preview) preview.classList.remove('has-error');
    _modalLivePrice = 0;
}

function showBuyModal() {
    resetModal();
    var overlay = document.getElementById('buyModalOverlay');
    if (overlay) {
        if (window.ESGMotion && window.ESGMotion.animateModalOpen) {
            window.ESGMotion.animateModalOpen(overlay);
        } else {
            overlay.style.display = 'flex';
        }
    }
    // Auto-fetch live price badge
    var badge = document.getElementById('livePriceBadge');
    if (badge) {
        badge.innerHTML = '<i class="bi bi-arrow-repeat"></i> Select a stock';
        badge.className = 'live-price-badge';
    }
}

function onTickerChange() {
    var ticker = document.getElementById('buyTicker').value;
    var badge = document.getElementById('livePriceBadge');
    if (!ticker) {
        badge.innerHTML = '<i class="bi bi-arrow-repeat"></i> Select a stock';
        badge.className = 'live-price-badge';
        _modalLivePrice = 0;
        updatePreview();
        return;
    }
    badge.innerHTML = '<i class="bi bi-arrow-repeat"></i> Fetching...';
    badge.className = 'live-price-badge loading';

    // Get live price from the predict API
    fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.error && data.current_price) {
            _modalLivePrice = data.current_price;
            _modalCurrency = data.currency_symbol || '$';
            document.getElementById('buyPriceCurrency').textContent = _modalCurrency;
            document.getElementById('amountCurrency').textContent = _modalCurrency;
            badge.innerHTML = '<i class="bi bi-check-circle"></i> Live: ' + _modalCurrency + _modalLivePrice.toFixed(2);
            badge.className = 'live-price-badge';
            // Auto-fill buy price if empty
            var priceInput = document.getElementById('buyPrice');
            if (!priceInput.value || parseFloat(priceInput.value) <= 0) {
                priceInput.value = _modalLivePrice.toFixed(2);
            }
            updatePreview();
        } else {
            badge.innerHTML = '<i class="bi bi-exclamation-circle"></i> Price unavailable';
            badge.className = 'live-price-badge';
            badge.style.borderColor = 'rgba(244,67,54,0.2)';
            badge.style.color = '#f44336';
        }
    })
    .catch(function() {
        badge.innerHTML = '<i class="bi bi-exclamation-circle"></i> Failed to fetch';
        badge.className = 'live-price-badge';
        badge.style.borderColor = 'rgba(244,67,54,0.2)';
        badge.style.color = '#f44336';
    });
}

function onBuyPriceChange() {
    updatePreview();
}

function onAmountChange() {
    updatePreview();
}

function updatePreview() {
    var ticker = document.getElementById('buyTicker').value;
    var price = parseFloat(document.getElementById('buyPrice').value) || _modalLivePrice || 0;
    var amount = parseFloat(document.getElementById('buyAmount').value) || 0;
    var currency = _modalCurrency || '$';
    var preview = document.getElementById('investmentPreview');

    if (!ticker || price <= 0 || amount <= 0) {
        document.getElementById('calcShares').textContent = '--';
        document.getElementById('previewPrice').textContent = currency + '0.00';
        document.getElementById('previewTotal').textContent = currency + '0.00';
        document.getElementById('previewFees').textContent = '$0.00';
        document.getElementById('buyConfirmBtn').disabled = true;
        if (preview) preview.classList.add('has-error');
        return;
    }

    var shares = amount / price;
    var totalCost = shares * price;
    var fees = totalCost * 0.001; // 0.1% estimated transaction fee
    var totalWithFees = totalCost + fees;

    document.getElementById('calcShares').textContent = shares.toFixed(4);
    document.getElementById('previewPrice').textContent = currency + price.toFixed(2);
    document.getElementById('previewTotal').textContent = currency + totalCost.toFixed(2);
    document.getElementById('previewFees').textContent = '$' + fees.toFixed(2);
    document.getElementById('buyConfirmBtn').disabled = false;
    if (preview) preview.classList.remove('has-error');
}

function submitBuy(btn) {
    var ticker = document.getElementById('buyTicker').value;
    var price = parseFloat(document.getElementById('buyPrice').value) || _modalLivePrice || 0;
    var amount = parseFloat(document.getElementById('buyAmount').value) || 0;

    if (!ticker) { showToast('Please select a stock', 'warning'); return; }
    if (price <= 0) { showToast('Please enter a valid buy price', 'warning'); return; }
    if (amount <= 0) { showToast('Please enter an investment amount', 'warning'); return; }

    var shares = amount / price;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Processing...';

    fetch('/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ticker: ticker, shares: shares, price: price, action: 'buy'})
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        closeBuyModal();
        loadPortfolio();
        showToast('Invested ' + _modalCurrency + amount.toFixed(2) + ' in ' + ticker + ' (' + shares.toFixed(2) + ' shares)', 'success');
    }).catch(function() { showToast('Buy failed', 'error'); }).finally(function() {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-lg me-1"></i> Confirm Purchase';
    });
}

function quickBuy(ticker) {
    var shares = parseFloat(prompt('Shares of ' + ticker + ' to buy:')) || 1;
    fetch('/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ticker: ticker, shares: shares, price: 0, action: 'buy'})
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        loadPortfolio();
        showToast('Bought ' + shares + ' share(s) of ' + ticker, 'success');
    }).catch(function() { showToast('Buy failed', 'error'); });
}

function quickSell(ticker) {
    var shares = parseFloat(prompt('Shares of ' + ticker + ' to sell:')) || 1;
    fetch('/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ticker: ticker, shares: shares, action: 'sell'})
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        loadPortfolio();
        showToast('Sold ' + shares + ' share(s) of ' + ticker, 'success');
    }).catch(function() { showToast('Sell failed', 'error'); });
}
function loadPortfolio() {
    fetch('/api/portfolio')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var holdings = data.holdings;
        var tbody = document.getElementById('portfolioBody');
        var countBadge = document.getElementById('holdingsCountBadge');
        if (!tbody) return;
        tbody.innerHTML = '';
        if (countBadge) countBadge.textContent = (holdings ? holdings.length : 0) + ' Positions';

        if (!holdings || !holdings.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center py-5 text-muted">' +
                '<i class="bi bi-wallet2 text-esg" style="font-size: 2.5rem; opacity: 0.5;"></i>' +
                '<h6 class="mt-2 text-white">No active holdings recorded</h6>' +
                '<p class="small text-secondary mb-2">Build your sustainable portfolio by adding positions.</p>' +
                '<button class="btn btn-esg btn-sm px-3 py-1" onclick="openBuyModal()"><i class="bi bi-plus-lg me-1"></i> Add First Position</button>' +
                '</td></tr>';
            updatePortfolioStats(0, 0, 0);
            if (window.alloChart) { window.alloChart.destroy(); window.alloChart = null; }
            return;
        }
        var tickerStr = holdings.map(function(h) { return h.ticker; }).join(',');
        fetch('/api/ticker/prices?tickers=' + tickerStr)
        .then(function(r) { return r.json(); })
        .then(function(prices) {
            var totalValue = 0, totalCost = 0;
            var rowsHtml = '';
            holdings.forEach(function(h) {
                var isIndian = h.ticker.endsWith('.NS') || h.ticker.endsWith('.BO') || ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT'].indexOf(h.ticker) !== -1;
                var sym = isIndian ? '₹' : '$';
                var p = prices[h.ticker];
                var currentPrice = p ? p.price : h.buy_price;
                var value = currentPrice * h.shares;
                var cost = h.buy_price * h.shares;
                var pnl = value - cost;
                var ret = cost > 0 ? ((pnl / cost) * 100) : 0;
                totalValue += value;
                totalCost += cost;

                var pnlBadgeClass = pnl >= 0 ? 'bg-success-subtle text-success border border-success-subtle' : 'bg-danger-subtle text-danger border border-danger-subtle';
                var pnlSign = pnl >= 0 ? '+' : '-';

                rowsHtml += '<tr data-ticker="' + h.ticker + '">' +
                    '<td><strong class="text-white" style="font-size:0.95rem;">' + h.ticker + '</strong></td>' +
                    '<td><span class="badge bg-secondary-subtle text-light border border-secondary border-opacity-25">' + h.shares + '</span></td>' +
                    '<td>' + sym + h.buy_price.toFixed(2) + '</td>' +
                    '<td class="text-info fw-bold">' + sym + currentPrice.toFixed(2) + '</td>' +
                    '<td class="text-light fw-bold">' + sym + value.toFixed(2) + '</td>' +
                    '<td><span class="badge ' + pnlBadgeClass + ' px-2 py-1" style="font-size:0.75rem;">' + pnlSign + sym + Math.abs(pnl).toFixed(2) + '</span></td>' +
                    '<td><span class="fw-bold ' + (ret >= 0 ? 'text-success' : 'text-danger') + '">' + (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%</span></td>' +
                    '<td class="text-end">' +
                        '<div class="btn-group btn-group-sm">' +
                            '<button class="btn btn-outline-success py-0.5 px-2" onclick="quickBuy(\'' + h.ticker + '\')" title="Buy More"><i class="bi bi-plus-lg"></i></button>' +
                            '<button class="btn btn-outline-danger py-0.5 px-2" onclick="quickSell(\'' + h.ticker + '\')" title="Sell Position"><i class="bi bi-dash-lg"></i></button>' +
                        '</div>' +
                    '</td></tr>';
            });
            tbody.innerHTML = rowsHtml;
            updatePortfolioStats(totalCost, totalValue, totalValue - totalCost);
            drawAllocationChart(holdings, prices);
        })
        .catch(function() {
            showToast('Failed to load current prices', 'warning');
            var rowsHtml = '';
            holdings.forEach(function(h) {
                var isIndian = h.ticker.endsWith('.NS') || h.ticker.endsWith('.BO') || ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT'].indexOf(h.ticker) !== -1;
                var sym = isIndian ? '₹' : '$';
                rowsHtml += '<tr data-ticker="' + h.ticker + '">' +
                    '<td><strong class="text-white">' + h.ticker + '</strong></td>' +
                    '<td><span class="badge bg-secondary-subtle text-light">' + h.shares + '</span></td>' +
                    '<td>' + sym + h.buy_price.toFixed(2) + '</td>' +
                    '<td class="text-muted">--</td>' +
                    '<td class="text-muted">--</td>' +
                    '<td class="text-muted">--</td>' +
                    '<td class="text-muted">--</td>' +
                    '<td class="text-end">' +
                        '<div class="btn-group btn-group-sm">' +
                            '<button class="btn btn-outline-success py-0.5 px-2" onclick="quickBuy(\'' + h.ticker + '\')"><i class="bi bi-plus-lg"></i></button>' +
                            '<button class="btn btn-outline-danger py-0.5 px-2" onclick="quickSell(\'' + h.ticker + '\')"><i class="bi bi-dash-lg"></i></button>' +
                        '</div>' +
                    '</td></tr>';
            });
            tbody.innerHTML = rowsHtml;
            updatePortfolioStats(0, 0, 0);
        });
    })
    .catch(function() {
        showToast('Failed to load portfolio', 'error');
    });
}
function updatePortfolioStats(cost, value, pnl) {
    var investedEl = document.getElementById('totalInvested');
    var valueEl = document.getElementById('currentValue');
    var retEl = document.getElementById('totalReturn');
    if (investedEl) investedEl.textContent = '$' + cost.toFixed(2);
    if (valueEl) valueEl.textContent = '$' + value.toFixed(2);
    if (retEl) {
        var ret = cost > 0 ? (pnl / cost) * 100 : 0;
        retEl.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%';
        retEl.className = 'stat-value fw-bold h3 mb-1 counter-val ' + (ret >= 0 ? 'text-success' : 'text-danger');
    }
}
function drawAllocationChart(holdings, prices) {
    if (typeof Chart === 'undefined') return;
    var labels = holdings.map(function(h) { return h.ticker; });
    var data = holdings.map(function(h) {
        var p = prices[h.ticker];
        return p ? p.price * h.shares : h.buy_price * h.shares;
    });
    var totalPortfolioValue = data.reduce(function(acc, val) { return acc + val; }, 0) || 1;
    var colors = ['#00e676', '#2196f3', '#ff9800', '#9c27b0', '#00bcd4', '#e91e63', '#ff5722', '#ffeb3b', '#795548', '#607d8b'];
    var canvas = document.getElementById('allocationChart');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    if (window.alloChart) window.alloChart.destroy();
    window.alloChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 2,
                borderColor: 'rgba(8, 20, 36, 0.95)',
                hoverBorderColor: '#ffffff',
                hoverBorderWidth: 2,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            animation: {
                animateRotate: true,
                animateScale: true,
                duration: 900,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 12,
                        color: '#90caf9',
                        font: { size: 11, weight: '500' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(10, 25, 41, 0.95)',
                    titleColor: '#ffffff',
                    bodyColor: '#90caf9',
                    borderColor: 'rgba(0, 230, 118, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(ctx) {
                            var val = ctx.parsed;
                            var pct = ((val / totalPortfolioValue) * 100).toFixed(1);
                            return ' Value: $' + val.toFixed(2) + ' (' + pct + '%)';
                        }
                    }
                }
            }
        }
    });
}

// Auto-load portfolio data when on portfolio page
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname === '/portfolio') {
        loadPortfolio();
    }
});

// Event delegation for portfolio buttons (works even before main.js fully loads)
document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-portfolio-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-portfolio-action');
    if (action === 'add-holding') {
        e.preventDefault();
        showBuyModal();
    } else if (action === 'buy') {
        submitBuy(btn);
    } else if (action === 'quick-buy') {
        var ticker = btn.getAttribute('data-ticker');
        quickBuy(ticker);
    } else if (action === 'quick-sell') {
        var ticker = btn.getAttribute('data-ticker');
        quickSell(ticker);
    }
});


/* ============================================================
   XAI - Explainable AI Feature Contributions
   ============================================================ */
function renderXAI(ticker, method) {
    if (!ticker) return;
    var card = document.getElementById("xaiCard");
    if (!card) return;
    
    method = method || getActiveXAIMethod();
    
    card.style.display = "block";
    card.style.opacity = "0.5";
    var contribDiv = document.getElementById("xaiContributions");
    var summaryDiv = document.getElementById("xaiSummary");
    var methodEl = document.getElementById("xaiMethod");
    var impactEl = document.getElementById("xaiPriceImpact");
    
    var methodLabels = {"auto": "Auto", "shap": "SHAP", "lime": "LIME"};
    var methodLabel = methodLabels[method] || "";
    if (contribDiv) contribDiv.innerHTML = "<div class='text-center py-3'><div class='spinner-border spinner-border-sm text-esg'></div> Computing " + methodLabel + " explanations...</div>";
    if (summaryDiv) summaryDiv.textContent = "";
    if (methodEl) methodEl.textContent = "";
    if (impactEl) impactEl.textContent = "";
    
    var url = '/api/xai/' + ticker + '?method=' + (method || 'auto');
    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                card.style.display = "none";
                return;
            }
            card.style.opacity = "1";
            if (methodEl) methodEl.textContent = data.method || "";
            if (summaryDiv) {
                summaryDiv.innerHTML = data.summary || "";
            }
            if (impactEl && data.price_impact !== undefined) {
                var sign = data.price_impact >= 0 ? "+" : "";
                var color = data.price_impact >= 0 ? "#4caf50" : "#f44336";
                impactEl.innerHTML = "Estimated Price Impact: <span style='color:" + color + ";font-weight:bold;font-size:1.1rem;'>" + sign + data.price_impact + "%</span>";
            }
            if (!contribDiv) return;
            var contribs = data.contributions || [];
            if (contribs.length === 0) {
                contribDiv.innerHTML = "<p class='text-muted text-center'>No factor breakdown available</p>";
                return;
            }
            var maxImpact = Math.max.apply(null, contribs.map(function(c) { return c.impact; }));
            var html = "<div class='xai-contrib-list'>";
            contribs.forEach(function(c) {
                var barWidth = (c.impact / maxImpact) * 100;
                var barColor = c.direction === "positive" ? "#4caf50" : "#f44336";
                var iconMap = {"leaf": "bi bi-flower1", "trending-up": "bi bi-graph-up-arrow", "bar-chart": "bi bi-bar-chart-fill", "activity": "bi bi-activity", "dollar-sign": "bi bi-currency-dollar", "help-circle": "bi bi-question-circle"};
                var icon = iconMap[c.icon] || "bi bi-dot";
                var sign = c.direction === "positive" ? "+" : "-";
                html += "<div class='xai-contrib-item mb-3'>";
                html += "  <div class='d-flex align-items-center justify-content-between mb-1'>";
                html += "    <span class='small fw-bold'><i class='" + icon + " me-2 text-esg'></i>" + c.factor + "</span>";
                html += "    <span class='fw-bold' style='color:" + barColor + ";'>" + sign + c.impact.toFixed(1) + "%</span>";
                html += "  </div>";
                html += "  <div class='xai-bar-track' style='height:6px;background:rgba(30,58,95,0.3);border-radius:3px;overflow:hidden;'>";
                html += "    <div class='xai-bar-fill' style='width:" + barWidth + "%;height:100%;background:" + barColor + ";border-radius:3px;transition:width 0.8s ease;'></div>";
                html += "  </div>";
                html += "  <small class='text-muted'>" + c.description + "</small>";
                html += "</div>";
            });
            html += "</div>";
            contribDiv.innerHTML = html;
            setTimeout(function() {
                contribDiv.querySelectorAll(".xai-bar-fill").forEach(function(el) {
                    el.style.transition = "width 0.8s ease";
                });
            }, 100);
        })
        .catch(function(err) {
            card.style.display = "none";
        });
}

function getActiveXAIMethod() {
    var activeBtn = document.querySelector('.xai-toggle-btn.active');
    if (activeBtn) {
        return activeBtn.getAttribute('data-method') || 'auto';
    }
    return 'auto';
}

// Initialize XAI toggle button click handlers
// Uses document-level event delegation so handlers survive AJAX innerHTML replacements
function initializeXAIToggle() {
    // Only set up the document listener once (check if already initialized)
    if (document._xaiToggleInitialized) return;
    document._xaiToggleInitialized = true;
    
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.xai-toggle-btn');
        if (!btn) return;
        
        var toggleGroup = btn.closest('.xai-method-toggle');
        if (!toggleGroup) return;
        
        var method = btn.getAttribute('data-method');
        if (!method) return;
        
        // Deactivate all, activate the clicked one
        toggleGroup.querySelectorAll('.xai-toggle-btn').forEach(function(b) {
            b.classList.remove('active');
        });
        btn.classList.add('active');
        
        // Read ticker dynamically from the DOM (survives AJAX replacements)
        var ticker = null;
        var tickerEl = document.querySelector('.stock-ticker');
        if (tickerEl) {
            ticker = tickerEl.textContent.trim();
        }
        if (!ticker) {
            var tickerSelect = document.getElementById('tickerSelect');
            if (tickerSelect) ticker = tickerSelect.value;
        }
        if (ticker) {
            renderXAI(ticker, method);
        }
    });
}
