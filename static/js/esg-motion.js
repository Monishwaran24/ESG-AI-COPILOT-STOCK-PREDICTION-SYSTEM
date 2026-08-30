/**
 * ESG Stock Prediction - Motion Animation System
 * Powered by Motion
 */

(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        define(['exports'], factory);
    } else if (typeof exports === 'object' && typeof exports.nodeName !== 'string') {
        factory(exports);
    } else {
        root.ESGMotion = factory({});
    }
}(typeof self !== 'undefined' ? self : this, function (exports) {
    'use strict';

    // 1. Reduced motion check
    function isReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    // 2. Global Motion Reference
    function getMotion() {
        return window.Motion || (typeof Motion !== 'undefined' ? Motion : null);
    }

    // Standard durations & easing curves (0.25s - 0.5s)
    var EASING = {
        easeOut: [0.16, 1, 0.3, 1], // Smooth custom cubic-bezier
        easeInOut: [0.42, 0, 0.58, 1],
        spring: { type: 'spring', stiffness: 400, damping: 28 }
    };

    var DURATIONS = {
        fast: 0.25,
        normal: 0.38,
        slow: 0.55
    };

    /**
     * Animate an element or list of elements with fadeUp
     */
    function animateFadeUp(target, options) {
        var M = getMotion();
        if (!target) return Promise.resolve();
        options = options || {};
        var duration = options.duration || DURATIONS.normal;
        var delay = options.delay || 0;
        var yOffset = options.y !== undefined ? options.y : 16;

        if (isReducedMotion() || !M || !M.animate) {
            if (target instanceof NodeList || Array.isArray(target)) {
                target.forEach(function(el) { if (el) { el.style.opacity = '1'; el.style.transform = 'none'; } });
            } else if (target) {
                target.style.opacity = '1';
                target.style.transform = 'none';
            }
            return Promise.resolve();
        }

        try {
            return M.animate(
                target,
                { opacity: [0, 1], y: [yOffset, 0] },
                { duration: duration, delay: delay, ease: EASING.easeOut }
            );
        } catch (e) {
            console.warn('ESGMotion.fadeUp warning:', e);
            return Promise.resolve();
        }
    }

    /**
     * Animate an element with fadeIn
     */
    function animateFadeIn(target, options) {
        var M = getMotion();
        if (!target) return Promise.resolve();
        options = options || {};
        var duration = options.duration || DURATIONS.normal;
        var delay = options.delay || 0;

        if (isReducedMotion() || !M || !M.animate) {
            if (target instanceof NodeList || Array.isArray(target)) {
                target.forEach(function(el) { if (el) el.style.opacity = '1'; });
            } else if (target) {
                target.style.opacity = '1';
            }
            return Promise.resolve();
        }

        try {
            return M.animate(
                target,
                { opacity: [0, 1] },
                { duration: duration, delay: delay, ease: EASING.easeOut }
            );
        } catch (e) {
            return Promise.resolve();
        }
    }

    /**
     * Animate with scaleIn (subtle 0.96 -> 1)
     */
    function animateScaleIn(target, options) {
        var M = getMotion();
        if (!target) return Promise.resolve();
        options = options || {};
        var duration = options.duration || DURATIONS.normal;
        var delay = options.delay || 0;
        var fromScale = options.scale !== undefined ? options.scale : 0.96;

        if (isReducedMotion() || !M || !M.animate) {
            if (target) { target.style.opacity = '1'; target.style.transform = 'none'; }
            return Promise.resolve();
        }

        try {
            return M.animate(
                target,
                { opacity: [0, 1], scale: [fromScale, 1], y: [10, 0] },
                { duration: duration, delay: delay, ease: EASING.easeOut }
            );
        } catch (e) {
            return Promise.resolve();
        }
    }

    /**
     * Stagger animate a collection of elements
     */
    function animateStagger(elements, options) {
        var M = getMotion();
        if (!elements || elements.length === 0) return Promise.resolve();
        options = options || {};
        var staggerDelay = options.stagger !== undefined ? options.stagger : 0.05;
        var startDelay = options.delay || 0;
        var duration = options.duration || DURATIONS.normal;
        var yOffset = options.y !== undefined ? options.y : 15;

        if (isReducedMotion() || !M || !M.animate) {
            Array.prototype.forEach.call(elements, function(el) {
                if (el) { el.style.opacity = '1'; el.style.transform = 'none'; }
            });
            return Promise.resolve();
        }

        try {
            var staggerFn = M.stagger ? M.stagger(staggerDelay, { startDelay: startDelay }) : function(i) { return startDelay + i * staggerDelay; };
            return M.animate(
                elements,
                { opacity: [0, 1], y: [yOffset, 0] },
                { delay: staggerFn, duration: duration, ease: EASING.easeOut }
            );
        } catch (e) {
            console.warn('ESGMotion.animateStagger warning:', e);
            return Promise.resolve();
        }
    }

    /**
     * Animate prediction result entrance
     */
    function animatePredictionResult(container) {
        var M = getMotion();
        if (!container) return;

        if (isReducedMotion() || !M || !M.animate) {
            container.style.opacity = '1';
            return;
        }

        // Animate the main result container
        animateScaleIn(container, { duration: 0.45, scale: 0.97 });

        // Animate cards inside result with stagger
        var cards = container.querySelectorAll('.stock-price-card, .glass-card, .card, .esg-metric-card');
        if (cards && cards.length > 0) {
            animateStagger(cards, { stagger: 0.06, startDelay: 0.05, duration: 0.35, y: 14 });
        }

        // Animate recommendation badge with subtle scale + fade
        var badges = container.querySelectorAll('.recommendation-badge');
        badges.forEach(function(badge) {
            animateRecommendation(badge);
        });

        // Animate progress bars smoothly to target width
        var progressBars = container.querySelectorAll('.progress-esg .progress-bar, .progress .progress-bar');
        progressBars.forEach(function(bar) {
            var targetWidth = bar.style.width || bar.getAttribute('data-width') || '0%';
            bar.style.width = '0%';
            bar.style.transition = 'none';
            setTimeout(function() {
                try {
                    M.animate(bar, { width: ['0%', targetWidth] }, { duration: 0.6, ease: EASING.easeOut });
                } catch(e) {
                    bar.style.width = targetWidth;
                }
            }, 120);
        });
    }

    /**
     * Animate Buy / Hold / Sell Recommendation Badge
     */
    function animateRecommendation(badgeEl) {
        var M = getMotion();
        if (!badgeEl || isReducedMotion() || !M || !M.animate) return;

        try {
            M.animate(
                badgeEl,
                { opacity: [0, 1], scale: [0.9, 1], y: [6, 0] },
                { duration: 0.4, delay: 0.15, ease: EASING.easeOut }
            );
        } catch (e) {}
    }

    /**
     * Animate Numbers smoothly ending at exact backend value
     */
    function animateNumber(element, startVal, endVal, duration, decimals, prefix, suffix) {
        if (!element) return;
        decimals = decimals !== undefined ? decimals : 0;
        prefix = prefix || '';
        suffix = suffix || '';
        duration = duration || 500;

        if (isReducedMotion()) {
            element.textContent = prefix + Number(endVal).toFixed(decimals) + suffix;
            return;
        }

        var startTime = null;
        startVal = parseFloat(startVal) || 0;
        endVal = parseFloat(endVal) || 0;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / duration, 1);
            // easeOutQuad
            var easedProgress = 1 - (1 - progress) * (1 - progress);
            var current = startVal + (endVal - startVal) * easedProgress;
            element.textContent = prefix + current.toFixed(decimals) + suffix;
            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                element.textContent = prefix + endVal.toFixed(decimals) + suffix;
            }
        }
        window.requestAnimationFrame(step);
    }

    /**
     * Modal entrance animation
     */
    function animateModalOpen(modalEl) {
        var M = getMotion();
        if (!modalEl) return;
        modalEl.style.display = modalEl.id === 'buyModalOverlay' ? 'flex' : 'block';

        if (isReducedMotion() || !M || !M.animate) {
            modalEl.style.opacity = '1';
            return;
        }

        var dialog = modalEl.querySelector('.modal-dialog, .modal-content, .bento-dialog') || modalEl;
        
        try {
            // Backdrop opacity
            M.animate(modalEl, { opacity: [0, 1] }, { duration: 0.25, ease: EASING.easeOut });
            // Modal dialog scale + y
            if (dialog && dialog !== modalEl) {
                M.animate(dialog, { opacity: [0, 1], scale: [0.95, 1], y: [12, 0] }, { duration: 0.3, ease: EASING.easeOut });
            }
        } catch (e) {}
    }

    /**
     * Modal exit animation
     */
    function animateModalClose(modalEl, onComplete) {
        var M = getMotion();
        if (!modalEl) {
            if (onComplete) onComplete();
            return;
        }

        if (isReducedMotion() || !M || !M.animate) {
            modalEl.style.display = 'none';
            if (onComplete) onComplete();
            return;
        }

        var dialog = modalEl.querySelector('.modal-dialog, .modal-content, .bento-dialog') || modalEl;

        try {
            var anim = M.animate(modalEl, { opacity: [1, 0] }, { duration: 0.2, ease: EASING.easeOut });
            if (dialog && dialog !== modalEl) {
                M.animate(dialog, { opacity: [1, 0], scale: [1, 0.95], y: [0, 10] }, { duration: 0.2, ease: EASING.easeOut });
            }
            if (anim && anim.finished) {
                anim.finished.then(function() {
                    modalEl.style.display = 'none';
                    if (onComplete) onComplete();
                });
            } else {
                setTimeout(function() {
                    modalEl.style.display = 'none';
                    if (onComplete) onComplete();
                }, 200);
            }
        } catch (e) {
            modalEl.style.display = 'none';
            if (onComplete) onComplete();
        }
    }

    /**
     * Dropdown / Collapsible animation
     */
    function animateDropdown(element, isOpen) {
        var M = getMotion();
        if (!element || isReducedMotion() || !M || !M.animate) return;

        try {
            if (isOpen) {
                element.style.display = 'block';
                M.animate(element, { opacity: [0, 1], scale: [0.96, 1], y: [-8, 0] }, { duration: 0.25, ease: EASING.easeOut });
            } else {
                var anim = M.animate(element, { opacity: [1, 0], scale: [1, 0.96], y: [0, -6] }, { duration: 0.2, ease: EASING.easeOut });
                if (anim && anim.finished) {
                    anim.finished.then(function() { element.style.display = 'none'; });
                } else {
                    setTimeout(function() { element.style.display = 'none'; }, 200);
                }
            }
        } catch (e) {}
    }

    /**
     * Button micro-interactions (whileHover: 1.02, whileTap: 0.98)
     */
    function applyButtonInteractions(btn) {
        if (!btn || btn.hasAttribute('data-motion-bound') || isReducedMotion()) return;
        btn.setAttribute('data-motion-bound', 'true');

        btn.addEventListener('mouseenter', function () {
            if (btn.disabled) return;
            var M = getMotion();
            if (M && M.animate) {
                M.animate(btn, { scale: 1.02 }, { duration: 0.15, ease: EASING.easeOut });
            } else {
                btn.style.transform = 'scale(1.02)';
            }
        });

        btn.addEventListener('mouseleave', function () {
            var M = getMotion();
            if (M && M.animate) {
                M.animate(btn, { scale: 1 }, { duration: 0.15, ease: EASING.easeOut });
            } else {
                btn.style.transform = 'none';
            }
        });

        btn.addEventListener('mousedown', function () {
            if (btn.disabled) return;
            var M = getMotion();
            if (M && M.animate) {
                M.animate(btn, { scale: 0.97 }, { duration: 0.1, ease: EASING.easeOut });
            } else {
                btn.style.transform = 'scale(0.97)';
            }
        });

        btn.addEventListener('mouseup', function () {
            var M = getMotion();
            if (M && M.animate) {
                M.animate(btn, { scale: 1.02 }, { duration: 0.12, ease: EASING.easeOut });
            }
        });
    }

    /**
     * Card micro-interactions (whileHover: y: -3, scale: 1.008)
     */
    function applyCardInteractions(card) {
        if (!card || card.hasAttribute('data-motion-card-bound') || isReducedMotion()) return;
        // Skip sticky or interactive container cards where hover could disorient
        if (card.classList.contains('no-hover-anim')) return;
        card.setAttribute('data-motion-card-bound', 'true');

        card.addEventListener('mouseenter', function () {
            var M = getMotion();
            if (M && M.animate) {
                M.animate(card, { y: -3, scale: 1.008 }, { duration: 0.22, ease: EASING.easeOut });
            }
        });

        card.addEventListener('mouseleave', function () {
            var M = getMotion();
            if (M && M.animate) {
                M.animate(card, { y: 0, scale: 1 }, { duration: 0.22, ease: EASING.easeOut });
            }
        });
    }

    /**
     * Scroll animations using inView / IntersectionObserver
     */
    function initScrollAnimations() {
        var M = getMotion();
        if (isReducedMotion()) return;

        var scrollTargets = document.querySelectorAll('.animate-on-scroll, .bento-card, .esg-feature-card, .stat-card-premium');
        if (scrollTargets.length === 0) return;

        if (M && M.inView) {
            try {
                M.inView(scrollTargets, function (info) {
                    var el = info.target || info;
                    animateFadeUp(el, { duration: 0.4, y: 16 });
                }, { amount: 0.15 });
                return;
            } catch(e) {}
        }

        // Fallback using IntersectionObserver
        if ('IntersectionObserver' in window) {
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        animateFadeUp(entry.target, { duration: 0.4, y: 16 });
                        observer.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.15 });

            scrollTargets.forEach(function (el) {
                observer.observe(el);
            });
        }
    }

    /**
     * Hero Section Initial Animation
     */
    function animateHeroSection() {
        var heroTitle = document.querySelector('.hero-title');
        var heroSubtitle = document.querySelector('.hero-subtitle');
        var heroButtons = document.querySelectorAll('.hero-section .btn-esg, .hero-section .btn-outline-esg');
        var floatingCard = document.querySelector('.glass-floating-card');
        var statsCards = document.querySelectorAll('.stat-card-premium, .hero-section + .row .card');

        if (heroTitle) animateFadeUp(heroTitle, { duration: 0.45, y: 20 });
        if (heroSubtitle) animateFadeUp(heroSubtitle, { duration: 0.45, delay: 0.1, y: 16 });
        if (heroButtons && heroButtons.length > 0) animateStagger(heroButtons, { stagger: 0.08, delay: 0.2, y: 12 });
        if (floatingCard) animateScaleIn(floatingCard, { duration: 0.5, delay: 0.15, scale: 0.94 });
        if (statsCards && statsCards.length > 0) animateStagger(statsCards, { stagger: 0.07, delay: 0.25, y: 16 });
    }

    /**
     * Dashboard Initial Animation
     */
    function animateDashboard() {
        var bentoCards = document.querySelectorAll('.bento-card');
        var dashboardCards = document.querySelectorAll('.main-content .glass-card');
        var modelInfoAlert = document.querySelector('.alert-esg-info');
        var stockItems = document.querySelectorAll('.stock-item');

        if (modelInfoAlert) animateFadeIn(modelInfoAlert, { duration: 0.35, delay: 0.05 });
        if (bentoCards && bentoCards.length > 0) animateStagger(bentoCards, { stagger: 0.07, delay: 0.1, y: 16 });
        if (dashboardCards && dashboardCards.length > 0) animateStagger(dashboardCards, { stagger: 0.08, delay: 0.15, y: 16 });
        if (stockItems && stockItems.length > 0) {
            // Animate first 12 stock items for fast initial load
            var topStocks = Array.prototype.slice.call(stockItems, 0, 12);
            animateStagger(topStocks, { stagger: 0.03, delay: 0.2, y: 10 });
        }
    }

    /**
     * Animate all numeric counters found on the active page
     */
    function animateAllCounters() {
        if (isReducedMotion()) return;
        var counterElements = document.querySelectorAll('.display-3, .display-4, .display-5, .stat-val, .metric-value, .counter-val, [data-counter]');
        counterElements.forEach(function(el) {
            if (el._hasCounterAnimated) return;
            var text = el.textContent.trim();
            // Match numbers like 82.5%, $1,287.50, 185, +12.4%
            var match = text.match(/^([^\d\-\+]*)([\+\-]?\d+(?:[\.,]\d+)?)(.*)$/);
            if (match) {
                var prefix = match[1];
                var rawNumStr = match[2].replace(',', '');
                var suffix = match[3];
                var num = parseFloat(rawNumStr);
                if (!isNaN(num) && Math.abs(num) > 0) {
                    el._hasCounterAnimated = true;
                    var decimals = (rawNumStr.indexOf('.') !== -1) ? rawNumStr.split('.')[1].length : 0;
                    animateNumber(el, 0, num, 600, decimals, prefix, suffix);
                }
            }
        });
    }

    /**
     * Animate all progress bars on the page from 0% to target
     */
    function animateAllProgressBars() {
        var M = getMotion();
        if (isReducedMotion() || !M || !M.animate) return;
        var bars = document.querySelectorAll('.progress-bar');
        bars.forEach(function(bar) {
            var targetWidth = bar.style.width || bar.getAttribute('aria-valuenow') + '%' || bar.getAttribute('data-width');
            if (targetWidth && targetWidth !== '0%') {
                bar.style.width = '0%';
                setTimeout(function() {
                    try {
                        M.animate(bar, { width: ['0%', targetWidth] }, { duration: 0.65, ease: EASING.easeOut });
                    } catch(e) {
                        bar.style.width = targetWidth;
                    }
                }, 100);
            }
        });
    }

    /**
     * Performance Page Animation
     */
    function animatePerformancePage() {
        var statCards = document.querySelectorAll('.performance-stat, .glass-card');
        var charts = document.querySelectorAll('.chart-container, canvas');
        var tables = document.querySelectorAll('.table-responsive');

        if (statCards && statCards.length > 0) animateStagger(statCards, { stagger: 0.06, delay: 0.05, y: 16 });
        if (charts && charts.length > 0) animateStagger(charts, { stagger: 0.08, delay: 0.15, y: 16 });
        if (tables && tables.length > 0) animateFadeUp(tables, { duration: 0.4, delay: 0.2, y: 14 });
    }

    /**
     * History & Portfolio Page Animation
     */
    function animateDataPages() {
        var summaryCards = document.querySelectorAll('.portfolio-summary, .stat-card-premium, .glass-card');
        var rows = document.querySelectorAll('.table-esg-premium tbody tr');

        if (summaryCards && summaryCards.length > 0) animateStagger(summaryCards, { stagger: 0.05, delay: 0.05, y: 14 });
        if (rows && rows.length > 0) {
            var topRows = Array.prototype.slice.call(rows, 0, 15);
            animateStagger(topRows, { stagger: 0.025, delay: 0.15, y: 8 });
        }
    }

    /**
     * Global Motion Initialization for all pages
     */
    function initMotionSystem() {
        var path = window.location.pathname;

        // 1. Hero / Landing animations
        if (document.querySelector('.hero-section')) {
            animateHeroSection();
        }

        // 2. Dashboard animations
        if (path.indexOf('/dashboard') !== -1 || document.querySelector('.bento-card')) {
            animateDashboard();
        }

        // 3. Performance / Backtest page
        if (path.indexOf('/performance') !== -1) {
            animatePerformancePage();
        }

        // 4. History, Portfolio, Alerts, About, Profile
        if (path.indexOf('/history') !== -1 || path.indexOf('/portfolio') !== -1 || path.indexOf('/alerts') !== -1 || path.indexOf('/about') !== -1 || path.indexOf('/profile') !== -1) {
            animateDataPages();
        }

        // 5. Universal cards and fade containers
        var allCards = document.querySelectorAll('.glass-card, .card, .fade-in:not(.hero-section)');
        if (allCards && allCards.length > 0) {
            animateStagger(allCards, { stagger: 0.05, delay: 0.05, y: 14 });
        }

        // 6. Universal number counter rollups & progress bar glide
        animateAllCounters();
        animateAllProgressBars();

        // 7. Attach button interactions
        var buttons = document.querySelectorAll(
            '.btn-esg, .btn-outline-esg, .btn-predict, .auth-btn, .sidebar-toggle, .ai-chat-toggle, .candle-timeframe, .xai-toggle-btn, .btn'
        );
        buttons.forEach(function (btn) {
            applyButtonInteractions(btn);
        });

        // 8. Attach card hover interactions
        var cards = document.querySelectorAll(
            '.glass-card:not(.no-hover), .bento-card, .stock-price-card, .esg-feature-card, .stat-card-premium, .auth-card'
        );
        cards.forEach(function (card) {
            applyCardInteractions(card);
        });

        // 9. Init scroll animations
        initScrollAnimations();
    }

    // Export API
    exports.isReducedMotion = isReducedMotion;
    exports.animateFadeIn = animateFadeIn;
    exports.animateFadeUp = animateFadeUp;
    exports.animateScaleIn = animateScaleIn;
    exports.animateStagger = animateStagger;
    exports.animatePredictionResult = animatePredictionResult;
    exports.animateRecommendation = animateRecommendation;
    exports.animateNumber = animateNumber;
    exports.animateAllCounters = animateAllCounters;
    exports.animateAllProgressBars = animateAllProgressBars;
    exports.animateModalOpen = animateModalOpen;
    exports.animateModalClose = animateModalClose;
    exports.animateDropdown = animateDropdown;
    exports.applyButtonInteractions = applyButtonInteractions;
    exports.applyCardInteractions = applyCardInteractions;
    exports.initScrollAnimations = initScrollAnimations;
    exports.initMotionSystem = initMotionSystem;

    // Run automatically on DOMContentLoaded
    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initMotionSystem);
        } else {
            initMotionSystem();
        }
    }

    return exports;
}));
