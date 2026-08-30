/**
 * ESGDataSphere.js - Hero Section 3D AI & ESG Financial Intelligence Visualization
 * =================================================================================
 * Abstract geometric node sphere featuring:
 * - Geodesic icosahedral wireframe mesh with vertex data nodes
 * - Rotating dual orbital data rings
 * - 3 interconnected ESG primary nodes (Environmental, Social, Governance)
 * - Restrained particle stream representing live financial analytics
 * - Smooth cursor parallax interaction with spring damping
 */

(function(window) {
    'use strict';

    function ESGDataSphere(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.animFrameId = null;
        this.isDisposed = false;

        // Visual group references
        this.mainGroup = null;
        this.coreMesh = null;
        this.nodesGroup = null;
        this.ringsGroup = null;
        this.particleSystem = null;
        this.esgHubs = [];

        // Interaction state
        this.targetRotationX = 0;
        this.targetRotationY = 0;
        this.currentRotationX = 0;
        this.currentRotationY = 0;
        this.mouseX = 0;
        this.mouseY = 0;
        this.clock = null;

        // Bound event handlers
        this._onMouseMove = this.onMouseMove.bind(this);
        this._onResize = this.onResize.bind(this);
    }

    ESGDataSphere.prototype.init = function() {
        if (!this.container || typeof THREE === 'undefined') return;

        var width = this.container.clientWidth || 480;
        var height = this.container.clientHeight || 420;

        // 1. Scene & Clock
        this.scene = new THREE.Scene();
        this.clock = new THREE.Clock();

        // 2. Camera
        this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
        this.camera.position.z = 4.2;

        // 3. WebGL Renderer with Alpha & Antialiasing
        this.renderer = new THREE.WebGLRenderer({
            alpha: true,
            antialias: true,
            powerPreference: 'high-performance'
        });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.ESG3D ? window.ESG3D.getPixelDensity() : Math.min(window.devicePixelRatio, 2));
        this.renderer.setClearColor(0x000000, 0);

        this.container.innerHTML = '';
        this.container.appendChild(this.renderer.domElement);

        // 4. Lighting
        var ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
        this.scene.add(ambientLight);

        var pointLight1 = new THREE.PointLight(0x00e676, 2.5, 12);
        pointLight1.position.set(3, 2, 3);
        this.scene.add(pointLight1);

        var pointLight2 = new THREE.PointLight(0x00d4ff, 2.0, 12);
        pointLight2.position.set(-3, -2, 2);
        this.scene.add(pointLight2);

        // 5. Main Transform Group
        this.mainGroup = new THREE.Group();
        this.scene.add(this.mainGroup);

        // 6. Build Geometry Layers
        this.buildGeodesicCore();
        this.buildOrbitalRings();
        this.buildESGHubs();
        this.buildDataParticles();

        // 7. Event Listeners
        window.addEventListener('mousemove', this._onMouseMove, { passive: true });

        // 8. Start Animation Loop
        this.animate();
    };

    ESGDataSphere.prototype.buildGeodesicCore = function() {
        // Outer Wireframe Geodesic Icosahedron
        var icosaGeometry = new THREE.IcosahedronGeometry(1.25, 2);
        var wireframeGeometry = new THREE.WireframeGeometry(icosaGeometry);

        var wireMaterial = new THREE.LineBasicMaterial({
            color: 0x1e3a5f,
            transparent: true,
            opacity: 0.55,
            linewidth: 1
        });
        var wireMesh = new THREE.LineSegments(wireframeGeometry, wireMaterial);
        this.mainGroup.add(wireMesh);

        // Inner Glowing Data Core
        var innerGeo = new THREE.IcosahedronGeometry(0.85, 1);
        var innerMat = new THREE.MeshStandardMaterial({
            color: 0x0a192f,
            emissive: 0x00e676,
            emissiveIntensity: 0.18,
            roughness: 0.25,
            metalness: 0.85,
            wireframe: true,
            transparent: true,
            opacity: 0.65
        });
        this.coreMesh = new THREE.Mesh(innerGeo, innerMat);
        this.mainGroup.add(this.coreMesh);

        // Geodesic Vertices as Data Nodes
        var posAttr = icosaGeometry.attributes.position;
        var nodeCount = posAttr.count;
        var nodeGeo = new THREE.BufferGeometry();
        var nodePositions = new Float32Array(nodeCount * 3);

        for (var i = 0; i < nodeCount * 3; i++) {
            nodePositions[i] = posAttr.array[i];
        }
        nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));

        var nodeMat = new THREE.PointsMaterial({
            color: 0x00d4ff,
            size: 0.045,
            transparent: true,
            opacity: 0.85
        });
        var pointNodes = new THREE.Points(nodeGeo, nodeMat);
        this.mainGroup.add(pointNodes);
    };

    ESGDataSphere.prototype.buildOrbitalRings = function() {
        this.ringsGroup = new THREE.Group();

        // Ring 1: Equatorial Latitude
        var ring1Geo = new THREE.TorusGeometry(1.6, 0.008, 16, 100);
        var ring1Mat = new THREE.MeshBasicMaterial({
            color: 0x00e676,
            transparent: true,
            opacity: 0.45
        });
        var ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
        ring1.rotation.x = Math.PI / 3;
        ring1.rotation.y = Math.PI / 6;
        this.ringsGroup.add(ring1);

        // Ring 2: Polar Orbital Path
        var ring2Geo = new THREE.TorusGeometry(1.85, 0.006, 16, 100);
        var ring2Mat = new THREE.MeshBasicMaterial({
            color: 0x00d4ff,
            transparent: true,
            opacity: 0.35
        });
        var ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
        ring2.rotation.x = -Math.PI / 4;
        ring2.rotation.z = Math.PI / 5;
        this.ringsGroup.add(ring2);

        this.mainGroup.add(this.ringsGroup);
    };

    ESGDataSphere.prototype.buildESGHubs = function() {
        var hubConfigs = [
            { name: 'E', color: 0x00e676, emissive: 0x00e676, radius: 1.6, speed: 0.75, offset: 0 },
            { name: 'S', color: 0x9c27b0, emissive: 0x9c27b0, radius: 1.6, speed: 0.75, offset: (Math.PI * 2) / 3 },
            { name: 'G', color: 0xffb300, emissive: 0xffb300, radius: 1.6, speed: 0.75, offset: (Math.PI * 4) / 3 }
        ];

        var self = this;
        hubConfigs.forEach(function(cfg) {
            var group = new THREE.Group();

            // Glowing Node Sphere
            var sphereGeo = new THREE.SphereGeometry(0.08, 16, 16);
            var sphereMat = new THREE.MeshStandardMaterial({
                color: cfg.color,
                emissive: cfg.emissive,
                emissiveIntensity: 0.8,
                roughness: 0.2,
                metalness: 0.5
            });
            var nodeMesh = new THREE.Mesh(sphereGeo, sphereMat);
            group.add(nodeMesh);

            // Pulsing Halo Ring
            var haloGeo = new THREE.RingGeometry(0.1, 0.12, 24);
            var haloMat = new THREE.MeshBasicMaterial({
                color: cfg.color,
                side: THREE.DoubleSide,
                transparent: true,
                opacity: 0.6
            });
            var haloMesh = new THREE.Mesh(haloGeo, haloMat);
            group.add(haloMesh);

            self.mainGroup.add(group);
            self.esgHubs.push({
                group: group,
                halo: haloMesh,
                config: cfg
            });
        });
    };

    ESGDataSphere.prototype.buildDataParticles = function() {
        var isMobile = window.ESG3D && window.ESG3D.isMobile();
        var particleCount = isMobile ? 60 : 150;
        var geometry = new THREE.BufferGeometry();
        var positions = new Float32Array(particleCount * 3);
        var colors = new Float32Array(particleCount * 3);

        var color1 = new THREE.Color(0x00e676);
        var color2 = new THREE.Color(0x00d4ff);

        for (var i = 0; i < particleCount; i++) {
            // Spherical distribution around core
            var radius = 1.3 + Math.random() * 1.2;
            var theta = Math.random() * Math.PI * 2;
            var phi = Math.acos((Math.random() * 2) - 1);

            positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
            positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
            positions[i * 3 + 2] = radius * Math.cos(phi);

            var mixedColor = color1.clone().lerp(color2, Math.random());
            colors[i * 3] = mixedColor.r;
            colors[i * 3 + 1] = mixedColor.g;
            colors[i * 3 + 2] = mixedColor.b;
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        var material = new THREE.PointsMaterial({
            size: 0.035,
            vertexColors: true,
            transparent: true,
            opacity: 0.75
        });

        this.particleSystem = new THREE.Points(geometry, material);
        this.mainGroup.add(this.particleSystem);
    };

    ESGDataSphere.prototype.onMouseMove = function(e) {
        // Normalized cursor coordinates (-1 to 1)
        var normX = (e.clientX / window.innerWidth) * 2 - 1;
        var normY = (e.clientY / window.innerHeight) * 2 - 1;

        // Subtle amplitude: max ~8 degrees
        this.targetRotationY = normX * 0.25;
        this.targetRotationX = normY * 0.18;
    };

    ESGDataSphere.prototype.onResize = function() {
        if (!this.container || !this.renderer || !this.camera) return;
        var width = this.container.clientWidth || 480;
        var height = this.container.clientHeight || 420;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    };

    ESGDataSphere.prototype.animate = function() {
        if (this.isDisposed) return;
        this.animFrameId = requestAnimationFrame(this.animate.bind(this));

        var elapsedTime = this.clock ? this.clock.getElapsedTime() : 0;
        var reducedMotion = window.ESG3D && window.ESG3D.isReducedMotion();

        // 1. Smooth Cursor Parallax Interpolation (Spring Physics)
        if (!reducedMotion) {
            this.currentRotationX += (this.targetRotationX - this.currentRotationX) * 0.04;
            this.currentRotationY += (this.targetRotationY - this.currentRotationY) * 0.04;
        }

        // 2. Base Orbital Rotation
        var baseRotationSpeed = reducedMotion ? 0.0005 : 0.003;
        this.mainGroup.rotation.y += baseRotationSpeed;
        this.mainGroup.rotation.x = this.currentRotationX + (Math.sin(elapsedTime * 0.3) * 0.04);
        this.mainGroup.rotation.z = this.currentRotationY * 0.5;

        // 3. Counter-rotate Inner Core
        if (this.coreMesh) {
            this.coreMesh.rotation.y -= 0.004;
            this.coreMesh.rotation.x += 0.002;
        }

        // 4. Rotate Orbital Rings
        if (this.ringsGroup) {
            this.ringsGroup.rotation.z += 0.002;
        }

        // 5. Orbit ESG Hubs
        var self = this;
        this.esgHubs.forEach(function(hub) {
            var angle = (elapsedTime * hub.config.speed * 0.5) + hub.config.offset;
            var r = hub.config.radius;
            // Equatorial-inclined orbital trajectory
            hub.group.position.x = Math.cos(angle) * r;
            hub.group.position.z = Math.sin(angle) * r;
            hub.group.position.y = Math.sin(angle * 2) * 0.28;

            // Face camera & pulse halo
            hub.halo.lookAt(self.camera.position);
            var pulse = 1 + (Math.sin(elapsedTime * 3 + hub.config.offset) * 0.15);
            hub.halo.scale.set(pulse, pulse, pulse);
        });

        // 6. Slowly drift data particles
        if (this.particleSystem && !reducedMotion) {
            this.particleSystem.rotation.y += 0.001;
            this.particleSystem.rotation.x -= 0.0005;
        }

        this.renderer.render(this.scene, this.camera);
    };

    ESGDataSphere.prototype.destroy = function() {
        this.isDisposed = true;
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
        window.removeEventListener('mousemove', this._onMouseMove);

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

    window.ESGDataSphere = ESGDataSphere;

})(window);
