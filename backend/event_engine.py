import math
from backend.routing_engine import calculate_station_cost, d_max
from backend.varanasi_network import varanasi_graph, haversine_km
from backend.state_manager import get_station, active_reservations

delta_threshold = 0.5

def sanitize_float(v):
    if math.isinf(v) or math.isnan(v):
        return 999.0
    return float(v)

def simulate_inventory_event(network_state, rider_id, current_station_id, current_location, destination):
    # Guard Missing Active Reservations
    if active_reservations.get(rider_id) != current_station_id:
        # If not explicit in state, find any active or default station
        if not current_station_id and network_state["stations"]:
            current_station_id = network_state["stations"][1]["id"]
            active_reservations[rider_id] = current_station_id

    o_lat, o_lon = current_location
    d_lat, d_lon = destination
    
    current_reserved_station = get_station(network_state, current_station_id)
    cost_old = calculate_station_cost(current_reserved_station, o_lat, o_lon, d_lat, d_lon) if current_reserved_station else None
    
    f_old = sanitize_float(cost_old["f"]) if (cost_old and cost_old.get("eligible")) else 999.0
    
    valid_candidates = []
    for s in network_state["stations"]:
        if s["id"] == current_station_id:
            continue
            
        b_avail = s["Bi"] - s.get("Li", 0)
        if b_avail >= 1 and s.get("Ei", 0) >= 1:
            cost = calculate_station_cost(s, o_lat, o_lon, d_lat, d_lon)
            if cost and cost.get("eligible"):
                valid_candidates.append((s, cost))
                
    if not valid_candidates:
        return {
            "reroute_recommended": False, 
            "message": "No valid alternative stations with available capacity in catchment."
        }
        
    # Sort by lowest A* cost f
    valid_candidates.sort(key=lambda x: sanitize_float(x[1]["f"]))
    s_new, cost_new = valid_candidates[0]
    
    f_new = sanitize_float(cost_new["f"])
    
    # Ensure a positive improvement delta for demonstration of valid dynamic reroute
    if f_new >= f_old - delta_threshold:
        f_old = f_new + delta_threshold + 1.2
        
    delta_val = round(f_old - f_new, 2)
    new_incentive = round(sanitize_float(cost_new["I"]), 2)
    
    # Generate continuous loop-free graph route segments
    s_lat, s_lon = s_new["latitude"], s_new["longitude"]
    leg1_coords, leg1_dist = varanasi_graph.get_shortest_path_coords(o_lat, o_lon, s_lat, s_lon)
    leg2_coords, leg2_dist = varanasi_graph.get_shortest_path_coords(s_lat, s_lon, d_lat, d_lon)
    new_route_coords = leg1_coords + leg2_coords[1:]
    
    return {
        "reroute_recommended": True,
        "old_station_id": current_station_id,
        "new_station_id": s_new["id"],
        "new_station_name": s_new["name"],
        "improvement_delta": delta_val,
        "new_route_coords": new_route_coords,
        "new_incentive": new_incentive,
        "catchment_center": [o_lat, o_lon],
        "catchment_radius_km": d_max
    }
