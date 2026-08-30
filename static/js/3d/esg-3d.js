/**
 * ESG Stock Prediction - 3D Visual Layer Orchestrator (ESG3D)
 * =============================================================
 * Manages Three.js WebGL scenes, lifecycle, device performance tiering,
 * and seamless coordination with Motion UI animations.
 *
 * Designed for institutional fintech: Data-driven, restrained, sophisticated.
 */

(function(window) {
    'use strict';

    var ESG3D = {
        version: '1.0.0',
        activeScenes: {},
        initialized: false,

        // Capability & Environment Detection
        isWebGLSupported: function() {
            try {
                var canvas = document.createElement('canvas');
                return !!(window.WebGLRenderingContext && 
                    (canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
            } catch (e) {
                return false;
            }
        },

        isReducedMotion: function() {
            return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        },

        isMobile: function() {
            return window.innerWidth <= 768 || /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        },

        getPixelDensity: function() {
            var dpr = window.devicePixelRatio || 1;
            // Cap at 2.0 for performance on retina displays, 1.5 on mobile
            return this.isMobile() ? Math.min(dpr, 1.5) : Math.min(dpr, 2.0);
        },

        // Color Palette conforming to existing ESG Fintech Design Tokens
        colors: {
            emerald: 0x00e676,     // Environmental / Bullish / Growth
            emeraldDim: 0x008f4c,
            cyan: 0x00d4ff,        // AI Data Intelligence / Processing
            cyanDim: 0x006680,
            gold: 0xffb300,        // Governance / Risk / Stability
            goldDim: 0x996b00,
            purple: 0x9c27b0,      // Social / Community metrics
            purpleDim: 0x5c1768,
            darkBlue: 0x0a192f,    // Deep Background Core
            nodeLine: 0x1e3a5f,    // Structural Connecting Paths
            ambient: 0x112233
        },

        // Scene Lifecycle Management
        registerScene: function(name, instance) {
            if (this.activeScenes[name]) {
                this.activeScenes[name].destroy();
            }
            this.activeScenes[name] = instance;
        },

        destroyScene: function(name) {
            if (this.activeScenes[name]) {
                try {
                    this.activeScenes[name].destroy();
                } catch (e) {
                    console.warn('[ESG3D] Error destroying scene:', name, e);
                }
                delete this.activeScenes[name];
            }
        },

        destroyAll: function() {
            var self = this;
            Object.keys(this.activeScenes).forEach(function(name) {
                self.destroyScene(name);
            });
        },

        // Main Initialization Hook (Called on page load and SPA navigation)
        init: function() {
            if (!this.isWebGLSupported()) {
                console.info('[ESG3D] WebGL not supported or disabled; using graceful 2D fallback.');
                return;
            }

            // Cleanup any stale WebGL scenes from previous route
            this.destroyAll();

            // 1. Initialize Hero 3D Centerpiece if container exists
            var heroContainer = document.getElementById('hero3dContainer');
            if (heroContainer && window.ESGDataSphere) {
                var heroSphere = new window.ESGDataSphere(heroContainer);
                heroSphere.init();
                this.registerScene('heroSphere', heroSphere);
            }

            // 2. Initialize 3D ESG Network if container exists
            var esgNetContainer = document.getElementById('esg3dNetworkContainer');
            if (esgNetContainer && window.ESGNetwork3D) {
                var esgNetwork = new window.ESGNetwork3D(esgNetContainer);
                esgNetwork.init();
                this.registerScene('esgNetwork', esgNetwork);
            }

            // 3. Initialize Ambient Background 3D Data Particles across all pages
            var particleContainer = document.getElementById('bg3dDataParticles');
            if (!particleContainer && !this.isReducedMotion()) {
                particleContainer = document.createElement('div');
                particleContainer.id = 'bg3dDataParticles';
                particleContainer.className = 'global-3d-bg-particles';
                document.body.appendChild(particleContainer);
            }
            if (particleContainer && window.DataParticles3D && !this.isReducedMotion()) {
                var bgParticles = new window.DataParticles3D(particleContainer);
                bgParticles.init();
                this.registerScene('bgParticles', bgParticles);
            }

            // 4. Initialize 3D Card Perspective Tilt across all pages
            if (window.ESGCardTilt) {
                window.ESGCardTilt.init();
            }
        }
    };

    // Auto-mount resize listener
    var _resizeDebounce = null;
    window.addEventListener('resize', function() {
        clearTimeout(_resizeDebounce);
        _resizeDebounce = setTimeout(function() {
            Object.keys(ESG3D.activeScenes).forEach(function(name) {
                var scene = ESG3D.activeScenes[name];
                if (scene && typeof scene.onResize === 'function') {
                    scene.onResize();
                }
            });
        }, 150);
    });

    window.ESG3D = ESG3D;

})(window);
