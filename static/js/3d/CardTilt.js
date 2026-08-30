/**
 * CardTilt.js - Subtle 3D Perspective Card Tilt Interaction
 * ==========================================================
 * Provides professional, restrained 3D perspective tilt for key analytics cards:
 * - Max rotation strictly capped at 4–6 degrees
 * - Spring-damped return on mouse leave
 * - Respects reduced-motion and touch device constraints
 */

(function(window) {
    'use strict';

    var ESGCardTilt = {
        initialized: false,
        activeCards: [],

        init: function() {
            if (window.ESG3D && window.ESG3D.isReducedMotion()) return;
            if (window.ESG3D && window.ESG3D.isMobile()) return;

            // Target all cards across all pages
            var selector = '.glass-card, .stat-card-premium, .bento-card, .stock-price-card, .esg-feature-card, .metric-item, .card, .auth-card, .performance-stat, .portfolio-card';
            var cards = document.querySelectorAll(selector);

            cards.forEach(function(card) {
                if (card._hasTiltHandler || card.classList.contains('no-tilt')) return;
                card._hasTiltHandler = true;

                card.style.transformStyle = 'preserve-3d';
                card.style.transition = 'transform 0.15s ease-out, box-shadow 0.25s ease';

                card.addEventListener('mouseenter', function() {
                    card.style.transition = 'transform 0.08s ease-out, box-shadow 0.25s ease';
                });

                card.addEventListener('mousemove', function(e) {
                    var rect = card.getBoundingClientRect();
                    var x = e.clientX - rect.left; // x pos within card
                    var y = e.clientY - rect.top;  // y pos within card

                    var centerX = rect.width / 2;
                    var centerY = rect.height / 2;

                    // Normalized range: -1 to 1
                    var normX = (x - centerX) / (centerX || 1);
                    var normY = (y - centerY) / (centerY || 1);

                    // Subdued tilt limits: max 4.5 degrees
                    var rotX = -normY * 4.5;
                    var rotY = normX * 4.5;

                    card.style.transform = 'perspective(1000px) rotateX(' + rotX.toFixed(2) + 'deg) rotateY(' + rotY.toFixed(2) + 'deg) scale3d(1.012, 1.012, 1.012)';
                    card.style.boxShadow = '0 16px 36px rgba(0, 0, 0, 0.45), 0 0 20px rgba(0, 230, 118, 0.12)';
                });

                card.addEventListener('mouseleave', function() {
                    card.style.transition = 'transform 0.45s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.45s ease';
                    card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
                    card.style.boxShadow = '';
                });
            });
        }
    };

    window.ESGCardTilt = ESGCardTilt;

})(window);
