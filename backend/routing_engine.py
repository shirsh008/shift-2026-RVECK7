import math
from backend.varanasi_network import varanasi_graph, haversine_km

# A* Routing & Rebalancing Parameters (10-minute depletion radius at 15 km/h = 2.5 km)
v_avg = 15.0      # Average speed km/h
d_max = 2.5       # Max 10-minute catchment radius km
alpha = 1.0       # Distance weight
beta = 0.35        # Wait time weight
gamma = 1.25       # Incentive attraction weight
I_max = 5.0       # Max incentive payout ($)
epsilon = 0.001

def haversine(lat1, lon1, lat2, lon2):
    return haversine_km(lat1, lon1, lat2, lon2)

def calculate_station_cost(station, o_lat, o_lon, d_lat, d_lon):
    """Calculates directional A* cost and catchment eligibility for a single station."""
    s_lat = station["latitude"]
    s_lon = station["longitude"]
    
    dist_o_s = haversine_km(o_lat, o_lon, s_lat, s_lon)
    in_catchment = (dist_o_s <= d_max)
    
    b_avail = station["Bi"] - station.get("Li", 0)
    e_i = station.get("Ei", 0)
    
    # Catchment Filter
    if not in_catchment:
        return {
            "station": station,
            "in_catchment": False,
            "dist_o_s": dist_o_s,
            "dist_s_d": haversine_km(s_lat, s_lon, d_lat, d_lon),
            "eligible": False,
            "reason": "Outside 10-min catchment radius"
        }
        
    # Dual-Factor Operational Readiness
    if b_avail <= 0 or e_i <= 0:
        return {
            "station": station,
            "in_catchment": True,
            "dist_o_s": dist_o_s,
            "dist_s_d": haversine_km(s_lat, s_lon, d_lat, d_lon),
            "eligible": False,
            "reason": "Station stockout (insufficient batteries or bays)"
        }
        
    # Estimated Wait Time (hours)
    t_arrival = dist_o_s / v_avg
    t_ready = 0.0
    W = max(0.0, t_ready - t_arrival)
    
    # Dynamic Rebalancing Incentive Calculation (Rewards routing to surplus inventory stations)
    total_slots = max(1, b_avail + e_i)
    supply_ratio = b_avail / total_slots
    incentive = min(I_max, I_max * supply_ratio)
    
    # Directional A* Cost Metric (penalizes draining critically low stations <= 2)
    crit_penalty = 8.0 if b_avail <= 2 else 0.0
    g = alpha * dist_o_s + beta * W - gamma * incentive + crit_penalty
    h = alpha * haversine_km(s_lat, s_lon, d_lat, d_lon)
    f = g + h
    
    return {
        "station": station,
        "in_catchment": True,
        "eligible": True,
        "dist_o_s": dist_o_s,
        "dist_s_d": h / alpha,
        "W": W,
        "I": incentive,
        "g": g,
        "h": h,
        "f": f
    }

def calculate_route(request_data, network_state):
    o_lat, o_lon = request_data.origin
    d_lat, d_lon = request_data.destination
    target_station_id = getattr(request_data, 'station_id', None)
    
    # Snap origin and destination coordinates to nearest road network nodes
    orig_node, orig_snap_dist = varanasi_graph.find_nearest_node(o_lat, o_lon)
    dest_node, dest_snap_dist = varanasi_graph.find_nearest_node(d_lat, d_lon)
    
    all_station_evals = []
    candidates = []
    optimal_station = None
    min_f = float('inf')
    
    for station in network_state["stations"]:
        eval_res = calculate_station_cost(station, o_lat, o_lon, d_lat, d_lon)
        all_station_evals.append(eval_res)
        
        if eval_res.get("eligible") and eval_res.get("f") is not None:
            candidates.append(eval_res)
            if eval_res["f"] < min_f:
                min_f = eval_res["f"]
                if not target_station_id:
                    optimal_station = eval_res

    # If user manually picked a specific station, use it
    if target_station_id:
        target_station = next((s for s in network_state["stations"] if s["id"] == target_station_id), None)
        if target_station:
            optimal_station = calculate_station_cost(target_station, o_lat, o_lon, d_lat, d_lon)
                
    if not optimal_station:
        # Fallback to lowest f among any valid station with batteries
        for station in network_state["stations"]:
            b_avail = station["Bi"] - station.get("Li", 0)
            if b_avail > 0:
                dist_o = haversine_km(o_lat, o_lon, station["latitude"], station["longitude"])
                dist_d = haversine_km(station["latitude"], station["longitude"], d_lat, d_lon)
                f_fallback = dist_o + dist_d
                if f_fallback < min_f:
                    min_f = f_fallback
                    optimal_station = {
                        "station": station,
                        "in_catchment": dist_o <= d_max,
                        "eligible": True,
                        "dist_o_s": dist_o,
                        "dist_s_d": dist_d,
                        "W": 0.0,
                        "I": 1.5,
                        "g": dist_o,
                        "h": dist_d,
                        "f": f_fallback
                    }
                    
    if not optimal_station:
        return None

    # Graph-aware path computations
    direct_coords, direct_dist = varanasi_graph.get_shortest_path_coords(o_lat, o_lon, d_lat, d_lon)
    
    s_lat = optimal_station["station"]["latitude"]
    s_lon = optimal_station["station"]["longitude"]
    
    # Calculate two segments:
    # 1. Shortest path from Origin node to Station node
    leg1_coords, leg1_dist = varanasi_graph.get_shortest_path_coords(o_lat, o_lon, s_lat, s_lon)
    # 2. Shortest path from Station node to Destination node
    leg2_coords, leg2_dist = varanasi_graph.get_shortest_path_coords(s_lat, s_lon, d_lat, d_lon)
    
    # Concatenate two paths into a single continuous route array (removing duplicate station node at join)
    detour_coords = leg1_coords + leg2_coords[1:]
    detour_dist = leg1_dist + leg2_dist
    
    return {
        "optimal_station": optimal_station["station"],
        "optimal_metrics": {
            "f": optimal_station.get("f", 0.0),
            "g": optimal_station.get("g", 0.0),
            "h": optimal_station.get("h", 0.0),
            "I": optimal_station.get("I", 0.0),
            "W": optimal_station.get("W", 0.0)
        },
        "candidate_stations": candidates,
        "all_station_evaluations": all_station_evals,
        "direct_route_distance": round(direct_dist, 3),
        "detour_route_distance": round(detour_dist, 3),
        "direct_route_coords": direct_coords,
        "detour_route_coords": detour_coords,
        "incentive_payout": round(optimal_station.get("I", 0.0), 2),
        "catchment_radius_km": d_max,
        "origin": [round(o_lat, 6), round(o_lon, 6)],
        "destination": [round(d_lat, 6), round(d_lon, 6)],
        "snapped_origin": {
            "node_id": str(orig_node),
            "distance_km": round(orig_snap_dist, 3)
        },
        "snapped_destination": {
            "node_id": str(dest_node),
            "distance_km": round(dest_snap_dist, 3)
        }
    }
