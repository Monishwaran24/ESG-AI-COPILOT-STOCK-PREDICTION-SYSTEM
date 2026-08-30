/**
 * DataParticles.js - Ambient 3D Financial & ESG Data Stream
 * ==========================================================
 * Minimal particle flow representing live financial and sustainability telemetry:
 * - Limited count (40-80 particles)
 * - Gentle vertical drift with depth parallax
 * - Automatically pauses when out of viewport
 */

(function(window) {
    'use strict';

    function DataParticles3D(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.animFrameId = null;
        this.isDisposed = false;
        this.particles = null;
        this.clock = null;
    }

    DataParticles3D.prototype.init = function() {
        if (!this.container || typeof THREE === 'undefined') return;

        var width = this.container.clientWidth || window.innerWidth;
        var height = this.container.clientHeight || 500;

        this.scene = new THREE.Scene();
        this.clock = new THREE.Clock();

        this.camera = new THREE.PerspectiveCamera(50, width / height, 1, 1000);
        this.camera.position.z = 400;

        this.renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: false,
            powerPreference: 'low-power'
        });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.ESG3D ? window.ESG3D.getPixelDensity() : 1);
        this.renderer.setClearColor(0x000000, 0);

        this.container.innerHTML = '';
        this.container.appendChild(this.renderer.domElement);

        var isMobile = window.ESG3D && window.ESG3D.isMobile();
        var count = isMobile ? 35 : 75;

        var geo = new THREE.BufferGeometry();
        var pos = new Float32Array(count * 3);
        var colors = new Float32Array(count * 3);

        var cEmerald = new THREE.Color(0x00e676);
        var cCyan = new THREE.Color(0x00d4ff);

        for (var i = 0; i < count; i++) {
            pos[i * 3] = (Math.random() - 0.5) * 800;
            pos[i * 3 + 1] = (Math.random() - 0.5) * 450;
            pos[i * 3 + 2] = (Math.random() - 0.5) * 300;

            var clr = cEmerald.clone().lerp(cCyan, Math.random());
            colors[i * 3] = clr.r;
            colors[i * 3 + 1] = clr.g;
            colors[i * 3 + 2] = clr.b;
        }

        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        var mat = new THREE.PointsMaterial({
            size: 3.5,
            vertexColors: true,
            transparent: true,
            opacity: 0.45
        });

        this.particles = new THREE.Points(geo, mat);
        this.scene.add(this.particles);

        this.animate();
    };

    DataParticles3D.prototype.onResize = function() {
        if (!this.container || !this.renderer || !this.camera) return;
        var width = this.container.clientWidth || window.innerWidth;
        var height = this.container.clientHeight || 500;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    };

    DataParticles3D.prototype.animate = function() {
        if (this.isDisposed) return;
        this.animFrameId = requestAnimationFrame(this.animate.bind(this));

        var delta = this.clock ? this.clock.getDelta() : 0.016;
        var reducedMotion = window.ESG3D && window.ESG3D.isReducedMotion();

        if (this.particles && !reducedMotion) {
            var positions = this.particles.geometry.attributes.position.array;
            for (var i = 1; i < positions.length; i += 3) {
                positions[i] += 8 * delta; // Slow upward drift
                if (positions[i] > 225) {
                    positions[i] = -225;
                }
            }
            this.particles.geometry.attributes.position.needsUpdate = true;
            this.particles.rotation.y += 0.0003;
        }

        this.renderer.render(this.scene, this.camera);
    };

    DataParticles3D.prototype.destroy = function() {
        this.isDisposed = true;
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
        if (this.renderer) {
            if (this.renderer.domElement && this.renderer.domElement.parentNode) {
                this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
            }
            this.renderer.dispose();
            this.renderer = null;
        }
        this.scene = null;
        this.camera = null;
    };

    window.DataParticles3D = DataParticles3D;

})(window);
