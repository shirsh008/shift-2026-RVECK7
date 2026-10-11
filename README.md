# VoltRide - Varanasi Micro-Mobility Rebalancing

A full-stack dashboard and routing engine designed to optimize battery-swapping networks for micro-mobility fleets during peak commute hours. Built for the Varanasi case study, this platform simulates dynamic A* rerouting to prevent station stockouts.

## 🚀 Features
* **Split-Screen Dashboard:** Operator command center (65% width) alongside a simulated rider mobile interface (35% width).
* **Live Network Topology:** Real OpenStreetMap road network graph for Varanasi, centered at 25.3176° N, 82.9739° E[cite: 3, 9].
* **Draggable Trip Markers:** Interactive Origin ($O_{alert}$) and Destination ($D_{dest}$) waypoints that auto-recalculate optimal detour paths.
* **Dynamic Catchment:** Live 10-minute depletion radius (2.5 km) rendering.
* **Peak-Hour Simulation:** 4-hour simulation generating 80 commuters to benchmark operational cost savings against baseline van dispatches[cite: 3, 7].

## 🛠️ Tech Stack
* **Backend:** Python, FastAPI, NetworkX, OSMnx[cite: 1, 9].
* **Frontend:** Vanilla JavaScript, TailwindCSS, Leaflet.js.

## ⚙️ Local Setup Instructions
1. Clone the repository.
2. Install Python dependencies:
   `pip install -r requirements.txt`
3. Start the FastAPI server:
   `uvicorn main:app --reload`
4. Open `http://localhost:8000` in your browser.
