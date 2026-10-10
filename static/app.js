// VoltRide Varanasi Case Study - Graph Visualizer & Simulation Frontend

// Map & Layer Groups
let map;
let graphEdgesLayer;
let graphNodesLayer;
let catchmentLayer;
let stationsLayer;
let odMarkersLayer;
let trajectoryLayer;
let riderDotsLayer;

// State caches
let stationMarkers = {};
let currentOrigin = null;
let currentDest = null;
let allStations = [];
let roadNetworkData = null;
let catchmentRadiusKm = 2.5;
let chosenStationId = null;

// Rider Session State
const RIDER_ID = "r1";
let activeReservationId = null;
let optimalStationData = null;
let currentIncentive = 0.0;
let midRouteCandidateId = null;
let midRouteCoords = null;
let newIncentive = 0.0;
let enRouteLocation = null;
let progressInterval = null;

// Simulation State
let latestSimData = null;
let simInterval = null;
let currentSimTime = 0; // 0 to 239 minutes
let isPlaying = false;
let simRiderMarkers = {};

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Initialize Leaflet Map centered on Varanasi (25.3176° N, 82.9739° E)
    map = L.map('operator-map', { 
        zoomControl: false,
        attributionControl: false 
    }).setView([25.3176, 82.9739], 13);

    // Free, unwatermarked OpenStreetMap tile layer (No API key required)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    L.control.zoom({ position: 'topleft' }).addTo(map);

    // Initialize Layer Groups in proper z-index order
    graphEdgesLayer = L.layerGroup().addTo(map);
    graphNodesLayer = L.layerGroup().addTo(map);
    catchmentLayer = L.layerGroup().addTo(map);
    trajectoryLayer = L.layerGroup().addTo(map);
    stationsLayer = L.layerGroup().addTo(map);
    odMarkersLayer = L.layerGroup().addTo(map);
    riderDotsLayer = L.layerGroup().addTo(map);

    // Initial Poll
    await pollNetworkState(true);
    setInterval(pollNetworkState, 1500);

    // Setup Layer Toggle Checkboxes
    const layerGraph = document.getElementById('layer-graph');
    if (layerGraph) {
        layerGraph.addEventListener('change', (e) => {
            if (e.target.checked) {
                map.addLayer(graphEdgesLayer);
                map.addLayer(graphNodesLayer);
            } else {
                map.removeLayer(graphEdgesLayer);
                map.removeLayer(graphNodesLayer);
            }
        });
    }

    const layerCatchment = document.getElementById('layer-catchment');
    if (layerCatchment) {
        layerCatchment.addEventListener('change', (e) => {
            e.target.checked ? map.addLayer(catchmentLayer) : map.removeLayer(catchmentLayer);
        });
    }

    const layerPaths = document.getElementById('layer-paths');
    if (layerPaths) {
        layerPaths.addEventListener('change', (e) => {
            e.target.checked ? map.addLayer(trajectoryLayer) : map.removeLayer(trajectoryLayer);
        });
    }

    // Attach Event Listeners
    const mobileReqRoute = document.getElementById('mobile-request-route');
    if (mobileReqRoute) mobileReqRoute.addEventListener('click', handleMobileRequestRoute);

    const simEventBtn = document.getElementById('simulate-event-trigger');
    if (simEventBtn) simEventBtn.addEventListener('click', handleSimulateEventTrigger);

    const globalSimEvent = document.getElementById('global-simulate-event');
    if (globalSimEvent) globalSimEvent.addEventListener('click', handleSimulateEventTrigger);

    const toastAccept = document.getElementById('toast-accept');
    if (toastAccept) toastAccept.addEventListener('click', handleToastAccept);

    const toastReject = document.getElementById('toast-reject');
    if (toastReject) toastReject.addEventListener('click', () => {
        const toast = document.getElementById('mobile-toast');
        if (toast) toast.style.bottom = '-220px';
    });

    const resetBtn = document.getElementById('reset-state-btn');
    if (resetBtn) resetBtn.addEventListener('click', handleResetNetwork);

    const runSimBtn = document.getElementById('run-simulation-btn');
    // TEMPORARILY DISABLED: will upload the simulation in the next shift
    // if (runSimBtn) runSimBtn.addEventListener('click', runSimulation);

    const simPlayBtn = document.getElementById('sim-play-btn');
    if (simPlayBtn) simPlayBtn.addEventListener('click', toggleSimPlay);

    const simScrubber = document.getElementById('sim-scrubber');
    if (simScrubber) simScrubber.addEventListener('input', (e) => {
        currentSimTime = parseFloat(e.target.value);
        renderSimFrame(currentSimTime);
    });

    const closeModalBtn = document.getElementById('close-modal-btn');
    if (closeModalBtn) closeModalBtn.addEventListener('click', () => {
        const modal = document.getElementById('benchmark-modal');
        if (modal) modal.classList.add('hidden');
    });

    const downloadCsvBtn = document.getElementById('download-csv-btn');
    if (downloadCsvBtn) downloadCsvBtn.addEventListener('click', handleCsvDownload);
});

// Calculate distance in km
function calcDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Poll Network State from Backend
async function pollNetworkState(isInitial = false) {
    try {
        const res = await fetch('/api/network-state');
        if (!res.ok) return;
        const data = await res.json();

        allStations = data.stations || [];
        
        if (isInitial || !currentOrigin) {
            currentOrigin = data.trip_request?.origin;
        }
        if (isInitial || !currentDest) {
            currentDest = data.trip_request?.destination;
        }
        
        catchmentRadiusKm = data.catchment_radius_km || 2.5;

        // Render road network graph topology on initial load
        if (data.road_network && (isInitial || !roadNetworkData)) {
            roadNetworkData = data.road_network;
            renderGraphTopology(data.road_network);
        }

        updateOperatorMetrics(allStations, data.metrics);
        updateOperatorMap(allStations);
        renderODMarkers();
        renderCatchmentArea();

        // Update Rider Origin/Destination Labels
        const origText = document.getElementById('rider-origin-text');
        if (origText && currentOrigin) origText.innerText = currentOrigin.name || "Near Assi Ghat, Varanasi";

        const destText = document.getElementById('rider-dest-text');
        if (destText && currentDest) destText.innerText = currentDest.name || "Varanasi Cantt Station (Junction)";

    } catch (err) {
        console.error("Polling error:", err);
    }
}

// 1. Render Varanasi Street Network Graph Overlay
function renderGraphTopology(topology) {
    graphEdgesLayer.clearLayers();
    graphNodesLayer.clearLayers();

    // Render Road Segments (Edges)
    if (topology.edges) {
        topology.edges.forEach(edge => {
            const polyline = L.polyline(edge.coordinates, {
                color: '#334155',
                weight: 2.5,
                opacity: 0.7,
                className: 'transition-all duration-300'
            }).addTo(graphEdgesLayer);

            polyline.bindTooltip(`<strong>${edge.name}</strong><br>Distance: ${edge.distance_km} km`, {
                sticky: true,
                className: 'bg-slate-900 text-slate-100 text-[10px] border border-slate-700 px-2 py-1 rounded shadow-lg'
            });
        });
    }

    // Render Intersection Vertices (Nodes)
    if (topology.nodes) {
        topology.nodes.forEach(node => {
            L.circleMarker([node.latitude, node.longitude], {
                radius: 2,
                color: '#0284c7',
                fillColor: '#38bdf8',
                fillOpacity: 0.7,
                weight: 1
            }).addTo(graphNodesLayer);
        });
    }
}

// Marker instances & Dragging State
let originMarker = null;
let destMarker = null;
let isUserDragging = false;

// 2. Render Rider Origin (O_alert) & Final Destination (D_dest) as Draggable Markers
function renderODMarkers() {
    if (!currentOrigin || !currentDest) return;

    const riderLat = enRouteLocation ? enRouteLocation[0] : currentOrigin.latitude;
    const riderLon = enRouteLocation ? enRouteLocation[1] : currentOrigin.longitude;

    if (!originMarker) {
        const originHTML = `
            <div class="relative flex items-center justify-center cursor-grab active:cursor-grabbing">
                <div class="absolute w-8 h-8 rounded-full bg-cyan-500/30 animate-custom-ping"></div>
                <div class="relative w-7 h-7 bg-cyan-600 rounded-full border-2 border-white shadow-xl shadow-cyan-500/50 flex items-center justify-center text-white text-xs font-bold">
                    🛵
                </div>
                <div class="absolute -bottom-5 bg-cyan-950 text-cyan-300 font-extrabold text-[9px] px-1.5 py-0.2 rounded border border-cyan-500/40 shadow whitespace-nowrap">
                    O<sub>alert</sub>
                </div>
            </div>
        `;
        const originIcon = L.divIcon({ html: originHTML, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
        originMarker = L.marker([riderLat, riderLon], { icon: originIcon, draggable: true }).addTo(odMarkersLayer);
        originMarker.bindTooltip(`<strong>Alert Origin (O<sub>alert</sub>)</strong><br><span class="text-cyan-300 font-semibold">✋ Drag to reposition Origin</span>`, {
            direction: 'top',
            className: 'bg-slate-950 text-cyan-300 text-xs border border-cyan-500 px-2.5 py-1.5 rounded-lg shadow-xl'
        });

        originMarker.on('dragstart', () => {
            isUserDragging = true;
            // Reset routing & selection immediately upon drag start
            chosenStationId = null;
            optimalStationData = null;
            activeReservationId = null;
            midRouteCandidateId = null;
            trajectoryLayer.clearLayers();

            const rCard = document.getElementById('route-card');
            if (rCard) rCard.classList.add('hidden');
            const tPrompt = document.getElementById('trip-prompt-card');
            if (tPrompt) tPrompt.classList.remove('hidden');

            updateOperatorMap(allStations);
        });

        originMarker.on('drag', (e) => {
            const pos = e.target.getLatLng();
            currentOrigin.latitude = pos.lat;
            currentOrigin.longitude = pos.lng;
            renderCatchmentArea();
            updateOperatorMap(allStations);
        });

        originMarker.on('dragend', async (e) => {
            isUserDragging = false;
            const pos = e.target.getLatLng();
            currentOrigin.latitude = pos.lat;
            currentOrigin.longitude = pos.lng;
            currentOrigin.name = `Origin (${pos.lat.toFixed(4)}° N, ${pos.lng.toFixed(4)}° E)`;
            
            const origText = document.getElementById('rider-origin-text');
            if (origText) origText.innerText = currentOrigin.name;

            // Reset routing & selection state on drag & drop:
            // In-catchment stations are displayed at full opacity (100%), no auto-locking or fading
            chosenStationId = null;
            optimalStationData = null;
            activeReservationId = null;
            midRouteCandidateId = null;
            trajectoryLayer.clearLayers();

            const rCard = document.getElementById('route-card');
            if (rCard) rCard.classList.add('hidden');
            const tPrompt = document.getElementById('trip-prompt-card');
            if (tPrompt) tPrompt.classList.remove('hidden');

            renderCatchmentArea();
            updateOperatorMap(allStations);
        });
    } else if (!isUserDragging) {
        originMarker.setLatLng([riderLat, riderLon]);
    }

    if (!destMarker) {
        const destHTML = `
            <div class="relative flex items-center justify-center cursor-grab active:cursor-grabbing">
                <div class="absolute w-8 h-8 rounded-full bg-rose-500/25 animate-halo"></div>
                <div class="relative w-7 h-7 bg-rose-600 rounded-full border-2 border-white shadow-xl shadow-rose-500/50 flex items-center justify-center text-white text-xs font-bold">
                    🏁
                </div>
                <div class="absolute -bottom-5 bg-rose-950 text-rose-300 font-extrabold text-[9px] px-1.5 py-0.2 rounded border border-rose-500/40 shadow whitespace-nowrap">
                    D<sub>dest</sub>
                </div>
            </div>
        `;
        const destIcon = L.divIcon({ html: destHTML, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
        destMarker = L.marker([currentDest.latitude, currentDest.longitude], { icon: destIcon, draggable: true }).addTo(odMarkersLayer);
        destMarker.bindTooltip(`<strong>Destination (D<sub>dest</sub>)</strong><br><span class="text-rose-300 font-semibold">✋ Drag to reposition Destination</span>`, {
            direction: 'top',
            className: 'bg-slate-950 text-rose-300 text-xs border border-rose-500 px-2.5 py-1.5 rounded-lg shadow-xl'
        });

        destMarker.on('dragstart', () => {
            isUserDragging = true;
        });

        destMarker.on('dragend', async (e) => {
            isUserDragging = false;
            const pos = e.target.getLatLng();
            currentDest.latitude = pos.lat;
            currentDest.longitude = pos.lng;
            currentDest.name = `Destination (${pos.lat.toFixed(4)}° N, ${pos.lng.toFixed(4)}° E)`;
            
            const destText = document.getElementById('rider-dest-text');
            if (destText) destText.innerText = currentDest.name;

            if (chosenStationId) {
                await calculateRouteForStation(chosenStationId);
            } else {
                chosenStationId = null;
                optimalStationData = null;
                trajectoryLayer.clearLayers();
                updateOperatorMap(allStations);
            }
        });
    } else if (!isUserDragging) {
        destMarker.setLatLng([currentDest.latitude, currentDest.longitude]);
    }
}

// 3. Render 10-Minute Catchment Area (S_catchment) centered at O_alert
function renderCatchmentArea() {
    catchmentLayer.clearLayers();
    if (!currentOrigin) return;

    const centerLat = enRouteLocation ? enRouteLocation[0] : currentOrigin.latitude;
    const centerLon = enRouteLocation ? enRouteLocation[1] : currentOrigin.longitude;
    const radiusMeters = catchmentRadiusKm * 1000; // 2.5 km = 2500m

    // Radial Catchment Circle
    L.circle([centerLat, centerLon], {
        radius: radiusMeters,
        color: '#06b6d4',
        weight: 1.5,
        dashArray: '6, 8',
        fillColor: '#06b6d4',
        fillOpacity: 0.08,
        className: 'transition-all duration-500'
    }).addTo(catchmentLayer);

    // Catchment Label Tooltip
    L.circleMarker([centerLat + 0.015, centerLon], {
        radius: 0.1,
        opacity: 0
    }).addTo(catchmentLayer).bindTooltip(`<strong>10-Min Depletion Catchment (S<sub>catchment</sub>)</strong><br>Radius: ${catchmentRadiusKm} km | Speed: 15 km/h`, {
        permanent: false,
        direction: 'right',
        className: 'bg-slate-950 text-cyan-300 text-xs border border-cyan-500/50 px-2 py-1 rounded shadow-lg'
    });
}

// 4. Update Operator Metrics Bar
function updateOperatorMetrics(stations, metrics) {
    let totalLocks = 0;
    let operationalCount = 0;

    stations.forEach(s => {
        totalLocks += (s.Li || 0);
        const bAvail = s.Bi - (s.Li || 0);
        if (bAvail > 0 && (s.Ei || 0) > 0) operationalCount++;
    });

    const healthPct = stations.length > 0 ? Math.round((operationalCount / stations.length) * 100) : 100;

    const mHealth = document.getElementById('metric-health');
    if (mHealth) mHealth.innerText = `${healthPct}%`;

    const mLocks = document.getElementById('metric-locks');
    if (mLocks) mLocks.innerText = totalLocks;

    const mCap = document.getElementById('metric-capital');
    if (mCap && metrics && metrics.incentive_capital_deployed !== undefined) {
        mCap.innerText = `$${metrics.incentive_capital_deployed.toFixed(2)}`;
    }

    const mVans = document.getElementById('metric-vans');
    if (mVans && metrics && metrics.vans_displaced !== undefined) {
        mVans.innerText = `${metrics.vans_displaced} trips`;
    }
}

// 5. Render & Highlight 50 Stations (In-Catchment Spotlight vs Out-of-Catchment Faded)
function updateOperatorMap(stations) {
    const oLat = enRouteLocation ? enRouteLocation[0] : (currentOrigin ? currentOrigin.latitude : 25.2862);
    const oLon = enRouteLocation ? enRouteLocation[1] : (currentOrigin ? currentOrigin.longitude : 83.0035);

    // Check if a station has been recommended, reserved, or manually active in route
    const activeStationId = chosenStationId || midRouteCandidateId || activeReservationId || (optimalStationData ? optimalStationData.id : null);
    const hasActiveChoice = !!activeStationId;

    stations.forEach(station => {
        const baseStation = allStations.find(s => s.id === station.id) || station;
        const lat = station.latitude || baseStation.latitude;
        const lon = station.longitude || baseStation.longitude;
        if (!lat || !lon) return;

        const distFromOrigin = calcDistanceKm(oLat, oLon, lat, lon);
        const inCatchment = distFromOrigin <= catchmentRadiusKm;
        const isChosen = (activeStationId === station.id);
        const isLocked = (station.Li || 0) > 0;
        const bAvail = station.Bi - (station.Li || 0);

        let iconHTML = '';
        let iconSize = [28, 28];
        let iconAnchor = [14, 14];

        if (hasActiveChoice) {
            if (isChosen) {
                // CHOSEN / WAYPOINT STATION: Enlarged, Glowing, Visual Pulse, Full Opacity 1.0
                iconSize = [46, 46];
                iconAnchor = [23, 23];

                const lockBadgeHTML = isLocked ? 
                    `<div class="absolute -top-3.5 -right-3.5 bg-amber-400 text-slate-950 text-[11px] font-black w-5 h-5 flex items-center justify-center rounded-full border-2 border-slate-900 shadow-xl z-30">L${station.Li}</div>` 
                    : '';

                const badgeLabel = activeReservationId === station.id ? 'S* RESERVED' : 'S* WAYPOINT';
                const starBadgeHTML = `<div class="absolute -top-4 -left-4 bg-gradient-to-r from-cyan-400 via-teal-300 to-blue-500 text-slate-950 text-[9px] font-black px-2 py-0.5 rounded-full border-2 border-white shadow-2xl z-30 tracking-wider whitespace-nowrap">${badgeLabel}</div>`;

                iconHTML = `
                    <div class="relative w-12 h-12 flex items-center justify-center transition-all duration-500 z-50 cursor-pointer">
                        <!-- Pulsing Glow Ripple Waves -->
                        <div class="absolute inset-0 rounded-full border-4 border-cyan-400 animate-custom-ping opacity-75"></div>
                        <div class="absolute -inset-1.5 rounded-full border-2 border-cyan-300 animate-halo opacity-90"></div>
                        
                        <!-- Core High-Glow Circular Badge -->
                        <div class="relative w-10 h-10 bg-gradient-to-br from-cyan-950 via-slate-900 to-blue-950 rounded-full border-2 border-cyan-300 active-station-pulse ring-4 ring-cyan-400/60 shadow-2xl z-20 flex flex-col items-center justify-center text-white">
                            <span class="text-[13px] font-mono font-black text-cyan-200 leading-none">${station.Bi}</span>
                            <span class="text-[7px] uppercase font-extrabold text-cyan-400 tracking-tighter">BATS</span>
                        </div>
                        ${lockBadgeHTML}
                        ${starBadgeHTML}
                    </div>
                `;
            } else {
                // INACTIVE STATIONS (Out-of-catchment even dimmer)
                const inactiveOpacity = inCatchment ? 'opacity-25' : 'opacity-15';
                iconSize = [22, 22];
                iconAnchor = [11, 11];

                iconHTML = `
                    <div class="relative w-5 h-5 flex items-center justify-center ${inactiveOpacity} scale-75 transition-all duration-500 hover:opacity-100 hover:scale-110 cursor-pointer pointer-events-auto">
                        <div class="absolute inset-0 bg-slate-900/90 rounded-full border border-slate-600 shadow z-10 flex flex-col items-center justify-center text-slate-400">
                            <span class="text-[8px] font-mono font-bold leading-none">${station.Bi}</span>
                        </div>
                    </div>
                `;
            }
        } else {
            // DEFAULT EXPLORATION STATE (No active route chosen):
            if (inCatchment) {
                // IN-CATCHMENT: 100% Opacity, prominent color-coded rings, full size (28x28)
                let ringColor = 'border-emerald-400 ring-2 ring-emerald-400/30';
                let bgStyle = 'bg-slate-900';
                let pulsating = '';

                if (bAvail <= 2) {
                    ringColor = 'border-rose-500 ring-2 ring-rose-500/40';
                    pulsating = 'animate-custom-ping';
                } else if (bAvail < 6) {
                    ringColor = 'border-amber-400 ring-2 ring-amber-400/30';
                }

                const lockBadgeHTML = isLocked ? 
                    `<div class="absolute -top-3 -right-3 bg-amber-400 text-slate-950 text-[10px] font-extrabold w-5 h-5 flex items-center justify-center rounded-full border-2 border-slate-900 shadow-md z-30">L${station.Li}</div>` 
                    : '';

                iconHTML = `
                    <div class="relative w-7 h-7 flex items-center justify-center opacity-100 scale-100 transition-all duration-300 hover:scale-110 cursor-pointer">
                        ${pulsating ? `<div class="absolute inset-0 rounded-full border-4 ${ringColor} ${pulsating} opacity-70"></div>` : ''}
                        <div class="absolute inset-0 ${bgStyle} rounded-full border-2 ${ringColor} shadow-xl z-10 flex flex-col items-center justify-center text-white">
                            <span class="text-[10px] font-mono font-bold leading-none">${station.Bi}</span>
                        </div>
                        ${lockBadgeHTML}
                    </div>
                `;
            } else {
                // OUT-OF-CATCHMENT: Significantly lowered opacity (0.20) & scaled down (scale-75)
                iconSize = [20, 20];
                iconAnchor = [10, 10];

                iconHTML = `
                    <div class="relative w-5 h-5 flex items-center justify-center opacity-20 scale-75 transition-all duration-300 hover:opacity-90 hover:scale-105 cursor-pointer pointer-events-auto">
                        <div class="absolute inset-0 bg-slate-900/90 rounded-full border border-slate-700 shadow z-10 flex flex-col items-center justify-center text-slate-500">
                            <span class="text-[8px] font-mono font-medium leading-none">${station.Bi}</span>
                        </div>
                    </div>
                `;
            }
        }

        const customIcon = L.divIcon({ html: iconHTML, className: '', iconSize: iconSize, iconAnchor: iconAnchor });
        const zOffset = isChosen ? 1000 : (inCatchment ? 100 : 0);

        if (stationMarkers[station.id]) {
            stationMarkers[station.id].setIcon(customIcon);
            stationMarkers[station.id].setZIndexOffset(zOffset);
            stationMarkers[station.id].off('click');
            stationMarkers[station.id].on('click', async () => {
                await handleStationClick(baseStation);
            });
        } else {
            const marker = L.marker([lat, lon], { icon: customIcon }).addTo(stationsLayer);
            marker.setZIndexOffset(zOffset);
            marker.on('click', async () => {
                await handleStationClick(baseStation);
            });
            stationMarkers[station.id] = marker;
        }

        // Tooltip Content with Varanasi Sector and Catchment status
        const catchmentBadge = inCatchment ? 
            `<span class="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[9px] font-bold px-1.5 py-0.5 rounded">In Catchment (${distFromOrigin.toFixed(2)} km)</span>` :
            `<span class="bg-slate-800 text-slate-400 text-[9px] px-1.5 py-0.5 rounded">Out of Catchment (${distFromOrigin.toFixed(2)} km)</span>`;

        const chosenBadge = isChosen ? 
            `<div class="bg-cyan-500/20 text-cyan-300 border border-cyan-400 text-[10px] font-extrabold px-2 py-0.5 rounded text-center mb-1 shadow">★ ACTIVE DETOUR WAYPOINT (S*)</div>` : '';

        stationMarkers[station.id].bindTooltip(`
            <div class="space-y-1 text-xs">
                ${chosenBadge}
                <div class="flex items-center justify-between space-x-2">
                    <strong class="text-white font-bold">${station.name || baseStation.name}</strong>
                </div>
                <div class="text-[10px] text-slate-400">Sector: <span class="text-cyan-300 font-semibold">${station.sector || baseStation.sector || 'Varanasi'}</span></div>
                <div class="flex items-center space-x-2 pt-1">
                    <span class="text-emerald-400 font-mono font-bold">Avail: ${bAvail}</span>
                    <span class="text-amber-400 font-mono">Locked: ${station.Li || 0}</span>
                    <span class="text-slate-400 font-mono">Empty: ${station.Ei}</span>
                </div>
                <div class="pt-1">${catchmentBadge}</div>
                <div class="pt-1 border-t border-slate-800 text-[10px] text-cyan-400 font-semibold">👆 Click to select as route detour</div>
            </div>
        `, {
            direction: 'top',
            className: 'bg-slate-950 text-slate-200 border border-slate-700 px-3 py-2 rounded-xl shadow-2xl'
        });
    });
}

// 6. Draw Trajectory Paths (Direct Trajectory & A* Detour Trajectory)
function drawActiveRiderPaths(routeData) {
    trajectoryLayer.clearLayers();
    if (!routeData) return;

    // 1. Direct Trajectory: O_alert -> D_dest (Dotted gray line along graph)
    if (routeData.direct_route_coords) {
        L.polyline(routeData.direct_route_coords, {
            color: '#475569',
            weight: 3,
            dashArray: '6, 8',
            opacity: 0.8
        }).addTo(trajectoryLayer).bindTooltip(`Direct Trajectory (O<sub>alert</sub> → D<sub>dest</sub>): ${routeData.direct_route_distance} km`, {
            sticky: true,
            className: 'bg-slate-950 text-slate-300 text-xs border border-slate-700 px-2 py-1 rounded'
        });
    }

    // 2. Detour Trajectory: O_alert -> S_recommended -> D_dest (Vivid neon cyan line along graph)
    if (routeData.detour_route_coords) {
        // Outer glow
        L.polyline(routeData.detour_route_coords, {
            color: '#06b6d4',
            weight: 6,
            opacity: 0.4
        }).addTo(trajectoryLayer);

        // Core solid line
        L.polyline(routeData.detour_route_coords, {
            color: '#0284c7',
            weight: 3.5,
            opacity: 1.0
        }).addTo(trajectoryLayer).bindTooltip(`A* Rebalanced Route via ${routeData.optimal_station.name}: ${routeData.detour_route_distance} km`, {
            sticky: true,
            className: 'bg-slate-950 text-cyan-300 text-xs border border-cyan-500 px-2 py-1 rounded shadow-xl'
        });
    }
}

// Manual Station Selection & Override Handler
async function handleStationClick(station) {
    if (!currentOrigin || !currentDest) return;

    // Activate mobile low-battery banner UI if not already active
    const hdr = document.getElementById('app-header');
    if (hdr) hdr.classList.replace('bg-indigo-600', 'bg-rose-600');
    const bTxt = document.getElementById('battery-text');
    if (bTxt) bTxt.innerText = '15%';
    const bFill = document.getElementById('battery-fill');
    if (bFill) {
        bFill.style.width = '15%';
        bFill.classList.replace('bg-white', 'bg-rose-300');
    }
    const alertBan = document.getElementById('alert-banner');
    if (alertBan) alertBan.classList.remove('hidden');
    const tPrompt = document.getElementById('trip-prompt-card');
    if (tPrompt) tPrompt.classList.add('hidden');

    // Update chosenStationId & immediate visual spotlight
    chosenStationId = station.id;
    optimalStationData = station;
    midRouteCandidateId = null;

    // Trigger visual highlight/fade immediately
    updateOperatorMap(allStations);

    // Calculate route passing through clicked station
    await calculateRouteForStation(station.id);
}

// Route Recalculation Engine (accepts optional stationId for manual override)
async function calculateRouteForStation(stationId = null) {
    if (!currentOrigin || !currentDest) return;

    try {
        const payload = {
            origin: [currentOrigin.latitude, currentOrigin.longitude],
            destination: [currentDest.latitude, currentDest.longitude],
            current_speed: 15.0
        };
        if (stationId) {
            payload.station_id = stationId;
        }

        const res = await fetch('/api/route-request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) return;
        const data = await res.json();
        if (!data || !data.optimal_station) {
            console.warn("No optimal station found");
            return;
        }

        optimalStationData = data.optimal_station;
        chosenStationId = optimalStationData.id;
        currentIncentive = data.incentive_payout;

        // Render recommended / user-selected swap card on mobile simulator
        const rCard = document.getElementById('route-card');
        if (rCard) {
            const sName = document.getElementById('route-station-name');
            if (sName) sName.innerText = optimalStationData.name;

            const sSector = document.getElementById('route-station-sector');
            if (sSector) {
                const manualTag = stationId ? ' (Manual Selection)' : '';
                sSector.innerText = `Sector: ${optimalStationData.sector || 'Varanasi'}${manualTag}`;
            }

            const rInc = document.getElementById('route-incentive');
            if (rInc) rInc.innerText = `Earn $${currentIncentive.toFixed(2)}`;

            const detourMeters = Math.max(0, ((data.detour_route_distance - data.direct_route_distance) * 1000)).toFixed(0);
            const rDetour = document.getElementById('route-detour');
            if (rDetour) rDetour.innerText = `+${detourMeters} m`;

            const rTime = document.getElementById('route-time');
            if (rTime) {
                const mins = Math.max(2, Math.round((data.detour_route_distance / 15.0) * 60));
                rTime.innerText = `~${mins} min`;
            }

            rCard.classList.remove('hidden');

            const lockBtn = document.getElementById('lock-reroute-btn');
            if (lockBtn && !activeReservationId) {
                lockBtn.disabled = false;
                lockBtn.className = "w-full py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold rounded-lg text-center text-xs shadow-lg transition-all cursor-pointer";
                lockBtn.innerText = "Lock Battery & Reroute Path";
                lockBtn.onclick = handleLockReservation;
            }
        }

        // Draw graph paths and highlight optimal station
        drawActiveRiderPaths(data);
        updateOperatorMap(allStations);
        renderCatchmentArea();

    } catch (err) {
        console.error("Route calculation error:", err);
    }
}

// 7. Mobile App Handlers
async function handleMobileRequestRoute() {
    const hdr = document.getElementById('app-header');
    if (hdr) hdr.classList.replace('bg-indigo-600', 'bg-rose-600');

    const bTxt = document.getElementById('battery-text');
    if (bTxt) bTxt.innerText = '15%';

    const bFill = document.getElementById('battery-fill');
    if (bFill) {
        bFill.style.width = '15%';
        bFill.classList.replace('bg-white', 'bg-rose-300');
    }

    const alertBan = document.getElementById('alert-banner');
    if (alertBan) alertBan.classList.remove('hidden');

    const tPrompt = document.getElementById('trip-prompt-card');
    if (tPrompt) tPrompt.classList.add('hidden');

    await calculateRouteForStation(null);
}

async function handleLockReservation() {
    const lockBtn = document.getElementById('lock-reroute-btn');
    if (lockBtn) {
        lockBtn.disabled = true;
        lockBtn.innerText = "Reserving Battery in Rack...";
    }

    try {
        const res = await fetch('/api/reserve-station', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rider_id: RIDER_ID,
                station_id: optimalStationData.id,
                incentive: currentIncentive
            })
        });

        const data = await res.json();
        if (data.status !== "success") throw new Error(data.message || "Reservation failed");

        activeReservationId = optimalStationData.id;

        if (lockBtn) {
            lockBtn.className = "w-full py-2.5 bg-emerald-600 text-white font-bold rounded-lg text-center text-xs shadow-lg";
            lockBtn.innerText = "✓ Battery Reserved — Navigation Active";
        }

        setTimeout(() => {
            const rCard = document.getElementById('route-card');
            if (rCard) rCard.classList.add('hidden');

            const pCard = document.getElementById('progress-card');
            if (pCard) pCard.classList.remove('hidden');

            const pDest = document.getElementById('progress-dest');
            if (pDest) pDest.innerText = `En-route via Varanasi road graph to ${optimalStationData.name}...`;

            let p = 0;
            if (progressInterval) clearInterval(progressInterval);
            progressInterval = setInterval(() => {
                p += 3;
                if (p > 100) p = 100;
                const pFill = document.getElementById('progress-bar-fill');
                if (pFill) pFill.style.width = `${p}%`;
            }, 600);
        }, 800);

        pollNetworkState();

    } catch (err) {
        alert("Lock failed: " + err.message);
        if (lockBtn) {
            lockBtn.disabled = false;
            lockBtn.innerText = "Lock Battery & Reroute Path";
        }
    }
}

// 8. Simulate Mid-Route Congestion / Inventory Event
async function handleSimulateEventTrigger() {
    // Rider has progressed halfway along Varanasi road network
    enRouteLocation = [
        currentOrigin.latitude + 0.015,
        currentOrigin.longitude - 0.008
    ];

    renderODMarkers();
    renderCatchmentArea();

    try {
        const res = await fetch('/api/simulate-inventory-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rider_id: RIDER_ID,
                current_station_id: activeReservationId || (allStations[1] ? allStations[1].id : "S2"),
                current_location: enRouteLocation,
                destination: [currentDest.latitude, currentDest.longitude]
            })
        });

        const data = await res.json();
        if (!data.reroute_recommended) {
            alert(data.message || "No better route met the cost threshold.");
            return;
        }

        midRouteCandidateId = data.new_station_id;
        midRouteCoords = data.new_route_coords;
        newIncentive = data.new_incentive;

        const newStation = allStations.find(s => s.id === midRouteCandidateId);

        const tDesc = document.getElementById('toast-desc');
        if (tDesc) {
            tDesc.innerHTML = `Traffic/demand spike ahead! Reroute to <strong>${newStation ? newStation.name : 'Station'}</strong> to earn updated <span class="text-emerald-400 font-bold font-mono">$${newIncentive.toFixed(2)}</span> incentive.`;
        }

        const toast = document.getElementById('mobile-toast');
        if (toast) toast.style.bottom = '20px';

        // Render alternative green path on graph
        trajectoryLayer.clearLayers();
        L.polyline(midRouteCoords, {
            color: '#10b981',
            weight: 4,
            dashArray: '6, 10'
        }).addTo(trajectoryLayer).bindTooltip(`Alternative Reroute to ${newStation ? newStation.name : 'Station'}`, {
            sticky: true,
            className: 'bg-slate-950 text-emerald-300 text-xs border border-emerald-500 px-2 py-1 rounded'
        });

    } catch (err) {
        console.error("Event simulation error:", err);
    }
}

// 9. Accept Reroute Swap
async function handleToastAccept() {
    try {
        const res = await fetch('/api/swap-reservation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rider_id: RIDER_ID,
                old_station_id: activeReservationId,
                new_station_id: midRouteCandidateId,
                incentive_diff: Math.max(0, newIncentive - currentIncentive)
            })
        });

        const data = await res.json();
        if (data.status === "success") {
            activeReservationId = midRouteCandidateId;
            optimalStationData = allStations.find(s => s.id === activeReservationId);
            currentIncentive = newIncentive;

            const pDest = document.getElementById('progress-dest');
            if (pDest) pDest.innerHTML = `Rerouted to <span class="font-bold text-amber-400">${optimalStationData.name}</span>!`;

            const toast = document.getElementById('mobile-toast');
            if (toast) toast.style.bottom = '-220px';

            trajectoryLayer.clearLayers();
            L.polyline(midRouteCoords, {
                color: '#0284c7',
                weight: 4
            }).addTo(trajectoryLayer);

            pollNetworkState();
        }
    } catch (err) {
        console.error("Swap error:", err);
    }
}

// 10. Reset Network Pilot State
async function handleResetNetwork() {
    try {
        const res = await fetch('/api/reset-network-state', { method: 'POST' });
        if (res.ok) {
            enRouteLocation = null;
            activeReservationId = null;
            optimalStationData = null;
            currentOrigin = null;
            currentDest = null;
            if (progressInterval) clearInterval(progressInterval);

            // Reset Mobile UI
            const hdr = document.getElementById('app-header');
            if (hdr) hdr.classList.replace('bg-rose-600', 'bg-indigo-600');

            const bTxt = document.getElementById('battery-text');
            if (bTxt) bTxt.innerText = '80%';

            const bFill = document.getElementById('battery-fill');
            if (bFill) {
                bFill.style.width = '80%';
                bFill.classList.replace('bg-rose-300', 'bg-white');
            }

            const alertBan = document.getElementById('alert-banner');
            if (alertBan) alertBan.classList.add('hidden');

            const tPrompt = document.getElementById('trip-prompt-card');
            if (tPrompt) tPrompt.classList.remove('hidden');

            const rCard = document.getElementById('route-card');
            if (rCard) rCard.classList.add('hidden');

            const pCard = document.getElementById('progress-card');
            if (pCard) pCard.classList.add('hidden');

            trajectoryLayer.clearLayers();
            chosenStationId = null;
            if (originMarker) { odMarkersLayer.removeLayer(originMarker); originMarker = null; }
            if (destMarker) { odMarkersLayer.removeLayer(destMarker); destMarker = null; }
            isUserDragging = false;
            await pollNetworkState(true);
        }
    } catch (err) {
        console.error("Reset failed:", err);
    }
}

// 11. Run Peak-Hour 4-Hour Simulation
function formatSimTime(min) {
    let totalMins = 7 * 60 + Math.floor(min);
    let h = Math.floor(totalMins / 60);
    let m = totalMins % 60;
    let ampm = h >= 12 ? 'PM' : 'AM';
    if (h > 12) h -= 12;
    if (h === 0) h = 12;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')} ${ampm} (${(min/60).toFixed(1)}h)`;
}

async function runSimulation() {
    const simBtn = document.getElementById('run-simulation-btn');
    if (simBtn) {
        simBtn.disabled = true;
        simBtn.innerText = "Simulating Varanasi Commute...";
    }

    try {
        const response = await fetch('/api/run-simulation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                num_riders: 80,
                time_window_hours: 4.0,
                random_seed: Math.floor(Math.random() * 1000)
            })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        latestSimData = data;

        const wrapper = document.getElementById('sim-trigger-wrapper');
        const controller = document.getElementById('sim-controller');
        if (wrapper) wrapper.classList.add('hidden');
        if (controller) controller.classList.remove('hidden');

        currentSimTime = 0;
        if (!isPlaying) toggleSimPlay();

    } catch (err) {
        alert("Simulation failed: " + err.message);
    } finally {
        if (simBtn) {
            simBtn.disabled = false;
            simBtn.innerText = "▶ Peak-Hour Commute Simulation (4hr)";
        }
    }
}

function toggleSimPlay() {
    isPlaying = !isPlaying;
    const btn = document.getElementById('sim-play-btn');
    if (isPlaying) {
        if (currentSimTime >= 239) {
            currentSimTime = 0;
            const scrub = document.getElementById('sim-scrubber');
            if (scrub) scrub.value = 0;
        }
        if (btn) btn.innerHTML = `<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>`;
        simInterval = setInterval(playbackTick, 50);
    } else {
        if (btn) btn.innerHTML = `<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4l12 6-12 6z"></path></svg>`;
        clearInterval(simInterval);
    }
}

function playbackTick() {
    const spdElem = document.getElementById('sim-speed');
    const speed = spdElem ? parseInt(spdElem.value) : 30;
    const advance = speed / 20;
    let oldTime = currentSimTime;
    currentSimTime += advance;

    if (currentSimTime >= 239) {
        currentSimTime = 239;
        if (isPlaying) toggleSimPlay();
        renderSimFrame(currentSimTime);
        displayBenchmarkResults(latestSimData);
        return;
    }

    const scrub = document.getElementById('sim-scrubber');
    if (scrub) scrub.value = currentSimTime;
    renderSimFrame(currentSimTime, oldTime);
}

function renderSimFrame(time, oldTime = null) {
    const sClock = document.getElementById('sim-clock');
    if (sClock) sClock.innerText = formatSimTime(time);

    const frameIndex = Math.floor(time);
    if (!latestSimData || !latestSimData.time_series_frames || !latestSimData.time_series_frames[frameIndex]) return;

    const frame = latestSimData.time_series_frames[frameIndex];

    updateOperatorMap(frame.stations_snap);

    const metricsObj = {
        incentive_capital_deployed: frame.cumulative_incentives,
        vans_displaced: Math.max(0, frame.baseline_vans - frame.proposed_vans)
    };
    updateOperatorMetrics(frame.stations_snap, metricsObj);

    // Van alert trigger
    if (oldTime !== null && latestSimData.van_logs) {
        const vans = latestSimData.van_logs.filter(v => v.time >= oldTime && v.time < time);
        if (vans.length > 0) {
            const station = allStations.find(s => s.id === vans[0].station_id);
            const alertDiv = document.getElementById('van-alert');
            if (alertDiv) {
                alertDiv.innerText = `⚠️ Rebalancing Van Dispatched to ${station ? station.name : 'Station'} ($35 OPEX)`;
                alertDiv.classList.remove('hidden');
                setTimeout(() => alertDiv.classList.add('hidden'), 2200);
            }
        }
    }

    // Commuter dot positions along Varanasi roads
    if (latestSimData.trip_logs && riderDotsLayer) {
        const activeTrips = latestSimData.trip_logs.filter(tr => time >= tr.t_start && time <= tr.t_arrival);

        Object.keys(simRiderMarkers).forEach(id => {
            if (!activeTrips.find(tr => tr.trip_id == id)) {
                riderDotsLayer.removeLayer(simRiderMarkers[id]);
                delete simRiderMarkers[id];
            }
        });

        activeTrips.forEach(tr => {
            let p = (time - tr.t_start) / Math.max(1, (tr.t_arrival - tr.t_start));
            p = Math.max(0, Math.min(1, p));
            let curLat = tr.o_lat + (tr.s_lat - tr.o_lat) * p;
            let curLon = tr.o_lon + (tr.s_lon - tr.o_lon) * p;

            if (simRiderMarkers[tr.trip_id]) {
                simRiderMarkers[tr.trip_id].setLatLng([curLat, curLon]);
            } else {
                simRiderMarkers[tr.trip_id] = L.circleMarker([curLat, curLon], {
                    radius: 4.5,
                    color: '#facc15',
                    fillColor: '#eab308',
                    fillOpacity: 0.95,
                    weight: 1.5
                }).addTo(riderDotsLayer);
            }
        });
    }
}

// 12. Display Benchmark Results Modal
function displayBenchmarkResults(data) {
    if (!data) return;

    function setTxt(id, txt) {
        const el = document.getElementById(id);
        if (el) el.innerText = txt;
    }

    const costSav = Math.max(0, data.comparison.cost_savings_pct);
    setTxt('sim-cost-reduction', `${costSav.toFixed(1)}%`);
    setTxt('sim-vans-saved', data.comparison.vans_saved);
    setTxt('sim-success-gain', `+${data.comparison.success_rate_gain_pct.toFixed(1)}%`);

    setTxt('tbl-base-succ', `${data.baseline.success_rate.toFixed(1)}%`);
    setTxt('tbl-prop-succ', `${data.proposed.success_rate.toFixed(1)}%`);
    setTxt('tbl-base-fail', data.baseline.failed_swaps);
    setTxt('tbl-prop-fail', data.proposed.failed_swaps);
    setTxt('tbl-base-vans', data.baseline.vans_dispatched);
    setTxt('tbl-prop-vans', data.proposed.vans_dispatched);
    setTxt('tbl-prop-inc', `$${data.proposed.incentives_paid.toFixed(2)}`);
    setTxt('tbl-base-opex', `$${data.baseline.total_opex.toFixed(2)}`);
    setTxt('tbl-prop-opex', `$${data.proposed.total_opex.toFixed(2)}`);

    setTxt('chart-base-opex', `$${data.baseline.total_opex.toFixed(2)}`);
    setTxt('chart-prop-opex', `$${data.proposed.total_opex.toFixed(2)}`);

    const barBase = document.getElementById('bar-base-opex');
    const barProp = document.getElementById('bar-prop-opex');
    const maxVal = Math.max(data.baseline.total_opex, data.proposed.total_opex, 1);

    if (barBase) {
        barBase.style.width = `100%`;
    }
    if (barProp) {
        const dynamicWidth = Math.min(100, Math.max(10, (data.proposed.total_opex / maxVal) * 100));
        barProp.style.width = `${dynamicWidth}%`;
    }

    setTxt('sim-detour-mins', data.proposed.avg_detour_mins.toFixed(1));
    setTxt('sim-detour-meters', `${(data.proposed.avg_detour_mins * 250).toFixed(0)} meters`);

    const modal = document.getElementById('benchmark-modal');
    if (modal) modal.classList.remove('hidden');
}

// 13. Download CSV Export
function handleCsvDownload() {
    if (!latestSimData) return;
    let csvContent = "data:text/csv;charset=utf-8,Varanasi Micro-Mobility Case Study Benchmark\n";
    csvContent += "Metric,Baseline (Status Quo),Dynamic A* (Proposed)\n";
    csvContent += `Swap Success Rate,${latestSimData.baseline.success_rate.toFixed(1)}%,${latestSimData.proposed.success_rate.toFixed(1)}%\n`;
    csvContent += `Failed Swaps,${latestSimData.baseline.failed_swaps},${latestSimData.proposed.failed_swaps}\n`;
    csvContent += `Rebalancing Vans,${latestSimData.baseline.vans_dispatched},${latestSimData.proposed.vans_dispatched}\n`;
    csvContent += `Incentives Paid,$0.00,$${latestSimData.proposed.incentives_paid.toFixed(2)}\n`;
    csvContent += `Total OPEX,$${latestSimData.baseline.total_opex.toFixed(2)},$${latestSimData.proposed.total_opex.toFixed(2)}\n`;
    csvContent += `Avg Detour Added,N/A,${latestSimData.proposed.avg_detour_mins.toFixed(1)} mins\n\n`;

    csvContent += "Hour,Baseline Stockouts,Proposed Stockouts,Baseline Active Commuters,Proposed Active Commuters\n";
    if (latestSimData.time_series_frames) {
        latestSimData.time_series_frames.forEach(row => {
            csvContent += `${row.hour},${row.baseline_stockout_incidents},${row.proposed_stockout_incidents},${row.baseline_active},${row.proposed_active}\n`;
        });
    }

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "varanasi_micromobility_benchmark.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
