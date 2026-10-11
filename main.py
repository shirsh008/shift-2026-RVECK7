import math
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from mock_data import generate_network_state
from backend.routing_engine import calculate_route
from backend.state_manager import reserve_station, release_station, swap_reservation, clear_reservations
from backend.event_engine import simulate_inventory_event
from backend.simulation_engine import run_simulation

app = FastAPI(title="Micro-Mobility Rebalancing API")

network_state_cache = generate_network_state()
network_state_cache["metrics"] = {
    "incentive_capital_deployed": 0.0,
    "vans_displaced": 0
}

class RouteRequest(BaseModel):
    origin: List[float]
    destination: List[float]
    current_speed: float = 15.0
    station_id: str = None

class ReserveRequest(BaseModel):
    rider_id: str
    station_id: str
    incentive: float = 0.0

class SwapRequest(BaseModel):
    rider_id: str
    old_station_id: str
    new_station_id: str
    incentive_diff: float = 0.0

class EventRequest(BaseModel):
    rider_id: str
    current_station_id: str
    current_location: List[float]
    destination: List[float]

class SimulationRequest(BaseModel):
    num_riders: int = 80
    time_window_hours: float = 4.0
    random_seed: int = 42

def sanitize_payload(obj):
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return 999.0
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_payload(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_payload(v) for v in obj]
    return obj

@app.get("/api/network-state")
def get_network_state():
    return sanitize_payload(network_state_cache)

@app.post("/api/reset-network-state")
def reset_network_state():
    global network_state_cache
    clear_reservations()
    network_state_cache = generate_network_state()
    network_state_cache["metrics"] = {
        "incentive_capital_deployed": 0.0,
        "vans_displaced": 0
    }
    return sanitize_payload(network_state_cache)

@app.post("/api/route-request")
def route_request(req: RouteRequest):
    if "trip_request" in network_state_cache:
        network_state_cache["trip_request"]["origin"]["latitude"] = req.origin[0]
        network_state_cache["trip_request"]["origin"]["longitude"] = req.origin[1]
        network_state_cache["trip_request"]["destination"]["latitude"] = req.destination[0]
        network_state_cache["trip_request"]["destination"]["longitude"] = req.destination[1]
    res = calculate_route(req, network_state_cache)
    return sanitize_payload(res)

@app.post("/api/reserve-station")
def api_reserve_station(req: ReserveRequest):
    success, data = reserve_station(network_state_cache, req.rider_id, req.station_id)
    if success:
        network_state_cache["metrics"]["incentive_capital_deployed"] += req.incentive
        network_state_cache["metrics"]["vans_displaced"] += 1
        return {"status": "success", "station": data}
    return {"status": "error", "message": data}

@app.post("/api/release-station")
def api_release_station(req: ReserveRequest):
    success = release_station(network_state_cache, req.rider_id, req.station_id)
    return {"status": "success" if success else "error"}

@app.post("/api/swap-reservation")
def api_swap_reservation(req: SwapRequest):
    success, data = swap_reservation(network_state_cache, req.rider_id, req.old_station_id, req.new_station_id)
    if success:
        network_state_cache["metrics"]["incentive_capital_deployed"] += req.incentive_diff
        return {"status": "success", "station": data}
    return {"status": "error", "message": data}

@app.post("/api/simulate-inventory-event")
def api_simulate_event(req: EventRequest):
    res = simulate_inventory_event(
        network_state_cache, 
        req.rider_id,
        req.current_station_id, 
        req.current_location, 
        req.destination
    )
    return sanitize_payload(res)

@app.post("/api/run-simulation")
def api_run_simulation(req: SimulationRequest):
    res = run_simulation(req.num_riders, req.time_window_hours, req.random_seed, network_state_cache)
    return sanitize_payload(res)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(content=b"", media_type="image/x-icon")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
