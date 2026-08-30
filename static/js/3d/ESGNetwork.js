/**
 * ESGNetwork.js - 3D Environmental, Social, and Governance Network Topology
 * =========================================================================
 * Interactive 3D visualization representing the three pillars of ESG:
 * - Top Node: Environmental (E - Emerald Green)
 * - Bottom Left: Social (S - Modern Purple/Violet)
 * - Bottom Right: Governance (G - Amber Gold)
 * - Connected via glowing 3D Catmull-Rom spline curves with pulsing data pulses
 * - Interactive raycaster: Hovering or clicking a node highlights metrics
 */

(function(window) {
    'use strict';

    function ESGNetwork3D(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.animFrameId = null;
        this.isDisposed = false;

        this.nodes = [];
        this.splineCurves = [];
        this.pulseParticles = [];
        this.clock = null;

        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2(-999, -999);
        this.hoveredNode = null;

        this._onMouseMove = this.onMouseMove.bind(this);
        this._onResize = this.onResize.bind(this);
    }

    ESGNetwork3D.prototype.init = function() {
        if (!this.container || typeof THREE === 'undefined') return;

        var width = this.container.clientWidth || 380;
        var height = this.container.clientHeight || 280;

        this.scene = new THREE.Scene();
        this.clock = new THREE.Clock();

        this.camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
        this.camera.position.set(0, 0, 4.5);

        this.renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: true,
            powerPreference: 'high-performance'
        });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.ESG3D ? window.ESG3D.getPixelDensity() : 1.5);
        this.renderer.setClearColor(0x000000, 0);

        this.container.innerHTML = '';
        this.container.appendChild(this.renderer.domElement);

        // Ambient & Directional Lighting
        var amb = new THREE.AmbientLight(0xffffff, 0.8);
        this.scene.add(amb);

        var dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
        dirLight.position.set(2, 4, 3);
        this.scene.add(dirLight);

        // Build E-S-G Nodes
        this.buildPillars();
        this.buildConnectors();

        this.container.addEventListener('mousemove', this._onMouseMove, { passive: true });
        this.animate();
    };

    ESGNetwork3D.prototype.buildPillars = function() {
        var self = this;
        var pillarDefs = [
            { id: 'env', label: 'E', title: 'Environmental', color: 0x00e676, emissive: 0x00e676, pos: new THREE.Vector3(0, 1.1, 0) },
            { id: 'social', label: 'S', title: 'Social', color: 0x9c27b0, emissive: 0x9c27b0, pos: new THREE.Vector3(-1.25, -0.9, 0) },
            { id: 'gov', label: 'G', title: 'Governance', color: 0xffb300, emissive: 0xffb300, pos: new THREE.Vector3(1.25, -0.9, 0) }
        ];

        pillarDefs.forEach(function(p) {
            var group = new THREE.Group();
            group.position.copy(p.pos);

            // Core Node Sphere
            var geo = new THREE.IcosahedronGeometry(0.32, 2);
            var mat = new THREE.MeshStandardMaterial({
                color: p.color,
                emissive: p.emissive,
                emissiveIntensity: 0.5,
                roughness: 0.2,
                metalness: 0.8,
                wireframe: false
            });
            var mesh = new THREE.Mesh(geo, mat);
            mesh.userData = { pillar: p };
            group.add(mesh);

            // Outer Wireframe Cage
            var cageGeo = new THREE.IcosahedronGeometry(0.42, 1);
            var cageMat = new THREE.MeshBasicMaterial({
                color: p.color,
                wireframe: true,
                transparent: true,
                opacity: 0.4
            });
            var cage = new THREE.Mesh(cageGeo, cageMat);
            group.add(cage);

            self.scene.add(group);
            self.nodes.push({
                group: group,
                mesh: mesh,
                cage: cage,
                pillar: p,
                basePos: p.pos.clone(),
                scaleTarget: 1.0,
                currentScale: 1.0
            });
        });
    };

    ESGNetwork3D.prototype.buildConnectors = function() {
        var nodePairs = [
            [this.nodes[0], this.nodes[1]], // E -> S
            [this.nodes[1], this.nodes[2]], // S -> G
            [this.nodes[2], this.nodes[0]]  // G -> E
        ];

        var self = this;
        nodePairs.forEach(function(pair, idx) {
            var p1 = pair[0].basePos;
            var p2 = pair[1].basePos;
            var mid = p1.clone().add(p2).multiplyScalar(0.5);
            mid.z += 0.35; // Curve slightly forward

            var curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
            var points = curve.getPoints(32);
            var geo = new THREE.BufferGeometry().setFromPoints(points);

            var mat = new THREE.LineBasicMaterial({
                color: 0x1e3a5f,
                transparent: true,
                opacity: 0.6,
                linewidth: 2
            });
            var line = new THREE.Line(geo, mat);
            self.scene.add(line);

            // Traveling Energy Pulse Particle along curve
            var pulseGeo = new THREE.SphereGeometry(0.045, 8, 8);
            var pulseMat = new THREE.MeshBasicMaterial({
                color: idx === 0 ? 0x00e676 : (idx === 1 ? 0x9c27b0 : 0xffb300),
                transparent: true,
                opacity: 0.9
            });
            var pulseMesh = new THREE.Mesh(pulseGeo, pulseMat);
            self.scene.add(pulseMesh);

            self.pulseParticles.push({
                mesh: pulseMesh,
                curve: curve,
                progress: (idx * 0.33) % 1.0,
                speed: 0.35
            });
        });
    };

    ESGNetwork3D.prototype.onMouseMove = function(e) {
        var rect = this.container.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    };

    ESGNetwork3D.prototype.onResize = function() {
        if (!this.container || !this.renderer || !this.camera) return;
        var width = this.container.clientWidth || 380;
        var height = this.container.clientHeight || 280;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    };

    ESGNetwork3D.prototype.animate = function() {
        if (this.isDisposed) return;
        this.animFrameId = requestAnimationFrame(this.animate.bind(this));

        var delta = this.clock ? this.clock.getDelta() : 0.016;
        var elapsedTime = this.clock ? this.clock.getElapsedTime() : 0;
        var reducedMotion = window.ESG3D && window.ESG3D.isReducedMotion();

        // 1. Raycast for Node Hover Interaction
        this.raycaster.setFromCamera(this.mouse, this.camera);
        var intersects = this.raycaster.intersectObjects(this.nodes.map(function(n) { return n.mesh; }));

        var activeHovered = intersects.length > 0 ? intersects[0].object : null;

        // 2. Animate Nodes
        this.nodes.forEach(function(n) {
            var isTarget = activeHovered === n.mesh;
            n.scaleTarget = isTarget ? 1.22 : 1.0;
            n.currentScale += (n.scaleTarget - n.currentScale) * 0.1;
            n.group.scale.set(n.currentScale, n.currentScale, n.currentScale);

            // Rotate outer wireframe cage
            if (!reducedMotion) {
                n.cage.rotation.y += 0.01;
                n.cage.rotation.x += 0.005;
                // Subtle floating harmonic bobbing
                n.group.position.y = n.basePos.y + (Math.sin(elapsedTime * 1.5 + n.basePos.x) * 0.035);
            }

            if (isTarget) {
                n.mesh.material.emissiveIntensity = 0.9;
            } else {
                n.mesh.material.emissiveIntensity = 0.45;
            }
        });

        // 3. Animate Pulse Particles along Curves
        if (!reducedMotion) {
            this.pulseParticles.forEach(function(p) {
                p.progress += p.speed * delta;
                if (p.progress > 1.0) p.progress = 0.0;
                var pt = p.curve.getPoint(p.progress);
                p.mesh.position.copy(pt);
            });
        }

        this.renderer.render(this.scene, this.camera);
    };

    ESGNetwork3D.prototype.destroy = function() {
        this.isDisposed = true;
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
        if (this.container) {
            this.container.removeEventListener('mousemove', this._onMouseMove);
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

    window.ESGNetwork3D = ESGNetwork3D;

})(window);
