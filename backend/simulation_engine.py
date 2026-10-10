import math
import random
import copy
from backend.routing_engine import calculate_station_cost, v_avg
from backend.varanasi_network import varanasi_graph, haversine_km

def sanitize_float(v):
    if math.isinf(v) or math.isnan(v):
        return 999.0
    return round(float(v), 2)

class SimulationEngine:
    def __init__(self, num_riders, duration_minutes, seed, base_network_state):
        self.num_riders = num_riders
        self.duration = duration_minutes
        self.seed = seed
        self.base_network_state = base_network_state
        
        # Key origin zones (Residential & Universities) and destination zones (Commercial & Railway Hubs)
        self.origin_hubs = [
            (25.2677, 82.9913), # Lanka / BHU
            (25.2840, 82.9950), # Durgakund
            (25.3160, 82.9850), # Sigra
            (25.3400, 83.0100)  # Pandeypur
        ]
        self.dest_hubs = [
            (25.3090, 83.0050), # Godowlia
            (25.3060, 83.0100), # Dashashwamedh
            (25.3110, 83.0120), # Chowk
            (25.3280, 82.9860), # Varanasi Cantt Station
            (25.3180, 83.0130)  # Maidagin
        ]

    def generate_trips(self):
        random.seed(self.seed)
        trips = []
        for _ in range(self.num_riders):
            # Inhomogeneous Poisson peak around 60-120 minutes (Morning peak 8:00 AM - 9:30 AM)
            t_start = int(random.gauss(90, 35))
            t_start = max(0, min(self.duration - 20, t_start))
            
            orig_center = random.choice(self.origin_hubs)
            dest_center = random.choice(self.dest_hubs)
            
            o_lat = orig_center[0] + (random.random() - 0.5) * 0.006
            o_lon = orig_center[1] + (random.random() - 0.5) * 0.006
            d_lat = dest_center[0] + (random.random() - 0.5) * 0.006
            d_lon = dest_center[1] + (random.random() - 0.5) * 0.006
            
            trips.append({
                "t_start": t_start,
                "o_lat": round(o_lat, 6), "o_lon": round(o_lon, 6),
                "d_lat": round(d_lat, 6), "d_lon": round(d_lon, 6)
            })
        trips.sort(key=lambda x: x["t_start"])
        return trips

    def run_mode(self, mode="baseline"):
        random.seed(self.seed)
        trips = self.generate_trips()
        
        stations = copy.deepcopy(self.base_network_state["stations"])
        for s in stations:
            s["charging_queue"] = []
            s["stockout_time"] = 0
            s["Li"] = 0
            if "capacity" not in s:
                s["capacity"] = s.get("Bi", 10) + s.get("Ei", 5)
            
        events = []
        for trip in trips:
            events.append((trip["t_start"], "trip_start", trip))
            
        events.sort(key=lambda x: x[0])
        
        metrics = {
            "swaps_attempted": 0,
            "swaps_completed": 0,
            "swaps_failed": 0,
            "vans_dispatched": 0,
            "incentives_paid": 0.0,
            "total_detour_mins": 0.0
        }
        
        time_series = []
        trip_logs = []
        van_logs = []
        active_commuters = 0
        
        for t in range(self.duration):
            # 1. Process Battery Charging (completed charging moves to Bi)
            for s in stations:
                finished = [ct for ct in s["charging_queue"] if ct <= t]
                for ct in finished:
                    s["Bi"] += 1
                s["charging_queue"] = [ct for ct in s["charging_queue"] if ct > t]
                
            # 2. Check Physical Stockouts and Van Dispatches
            current_stockouts = 0
            for s in stations:
                # Physical stockout occurs if no physical batteries (Bi <= 0) or no empty bays (Ei <= 0)
                is_stocked_out = (s["Bi"] <= 0 or s.get("Ei", 0) <= 0)
                if is_stocked_out:
                    s["stockout_time"] += 1
                    current_stockouts += 1
                else:
                    s["stockout_time"] = 0
                    
                # Threshold for van dispatch (15 minutes of continuous unmitigated stockout)
                if s["stockout_time"] >= 15:
                    metrics["vans_dispatched"] += 1
                    s["stockout_time"] = 0
                    van_logs.append({"time": t, "station_id": s["id"]})
                    cap = s["capacity"]
                    s["Bi"] = max(4, cap // 2)
                    s["Ei"] = cap - s["Bi"]
                    s["charging_queue"] = []
                    
            # 3. Process Events at minute t
            current_events = [e for e in events if int(e[0]) == t]
            events = [e for e in events if int(e[0]) > t]
            
            for ev_time, ev_type, data in current_events:
                if ev_type == "trip_start":
                    active_commuters += 1
                    metrics["swaps_attempted"] += 1
                    
                    if mode == "baseline":
                        # Uncoordinated: pick geometrically closest station
                        best_s = min(stations, key=lambda s: haversine_km(data["o_lat"], data["o_lon"], s["latitude"], s["longitude"]))
                        dist = haversine_km(data["o_lat"], data["o_lon"], best_s["latitude"], best_s["longitude"])
                        travel_mins = max(1, int(dist / v_avg * 60))
                        arrival_time = t + travel_mins
                        
                        events.append((arrival_time, "arrival", {
                            "station_id": best_s["id"], 
                            "trip": data,
                            "locked": False
                        }))
                        events.sort(key=lambda x: x[0])
                        
                    elif mode == "proposed":
                        # Coordinated: Dynamic Directional A* with Incentives & Battery Reservation
                        best_candidate = None
                        min_f = float('inf')
                        best_cost_metrics = None
                        
                        for s in stations:
                            cost = calculate_station_cost(s, data["o_lat"], data["o_lon"], data["d_lat"], data["d_lon"])
                            if cost and cost.get("eligible") and cost.get("f") is not None and cost["f"] < min_f:
                                min_f = cost["f"]
                                best_candidate = s
                                best_cost_metrics = cost
                                
                        # Fallback to any surplus station if optimal is constrained
                        if not best_candidate:
                            for s in stations:
                                b_avail = s["Bi"] - s.get("Li", 0)
                                if b_avail >= 2 and s.get("Ei", 0) >= 1:
                                    best_candidate = s
                                    dist = haversine_km(data["o_lat"], data["o_lon"], s["latitude"], s["longitude"])
                                    best_cost_metrics = {
                                        "dist_o_s": dist,
                                        "dist_s_d": haversine_km(s["latitude"], s["longitude"], data["d_lat"], data["d_lon"]),
                                        "I": 2.5
                                    }
                                    break
                                
                        if best_candidate:
                            best_candidate["Li"] = best_candidate.get("Li", 0) + 1
                            dist = best_cost_metrics["dist_o_s"]
                            travel_mins = max(1, int(dist / v_avg * 60))
                            arrival_time = t + travel_mins
                            metrics["incentives_paid"] += best_cost_metrics.get("I", 0.0)
                            
                            dist_direct = haversine_km(data["o_lat"], data["o_lon"], data["d_lat"], data["d_lon"])
                            dist_detour = best_cost_metrics["dist_o_s"] + best_cost_metrics["dist_s_d"]
                            detour_mins = max(0, (dist_detour - dist_direct) / v_avg * 60)
                            metrics["total_detour_mins"] += detour_mins
                            
                            trip_logs.append({
                                "trip_id": len(trip_logs),
                                "o_lat": data["o_lat"], "o_lon": data["o_lon"],
                                "s_lat": best_candidate["latitude"], "s_lon": best_candidate["longitude"],
                                "t_start": t,
                                "t_arrival": arrival_time,
                                "station_id": best_candidate["id"]
                            })
                            events.append((arrival_time, "arrival", {
                                "station_id": best_candidate["id"], 
                                "trip": data, 
                                "locked": True
                            }))
                            events.sort(key=lambda x: x[0])
                        else:
                            metrics["swaps_failed"] += 1
                            active_commuters -= 1
                            
                elif ev_type == "arrival":
                    active_commuters = max(0, active_commuters - 1)
                    s = next((st for st in stations if st["id"] == data["station_id"]), None)
                    if s:
                        if data.get("locked") and s.get("Li", 0) > 0:
                            s["Li"] -= 1
                            
                        # Perform swap if battery available
                        if s["Bi"] > 0 and s.get("Ei", 0) > 0:
                            metrics["swaps_completed"] += 1
                            s["Bi"] -= 1
                            s["Ei"] -= 1
                            s["charging_queue"].append(t + 30) # 30 min charging
                        else:
                            metrics["swaps_failed"] += 1
                            # Immediate emergency stockout impact
                            s["stockout_time"] += 5
                            
            # 4. Telemetry snapshot (every minute)
            if t % 1 == 0 or t == self.duration - 1:
                snap = {
                    "minute": t,
                    "hour": round(t / 60, 2),
                    "active_commuters": active_commuters,
                    "stockouts": current_stockouts,
                    "cumulative_vans": metrics["vans_dispatched"],
                    "cumulative_incentives": round(metrics["incentives_paid"], 2),
                    "stations_snap": [{"id": st["id"], "Bi": st["Bi"], "Ei": st.get("Ei", 0), "Li": st.get("Li", 0), "name": st.get("name", "Station")} for st in stations]
                }
                time_series.append(snap)
                
        total_opex = metrics["vans_dispatched"] * 35.0 + metrics["incentives_paid"]
        succ_rate = (metrics["swaps_completed"] / metrics["swaps_attempted"]) * 100 if metrics["swaps_attempted"] > 0 else 0
        avg_detour = metrics["total_detour_mins"] / metrics["swaps_completed"] if metrics["swaps_completed"] > 0 else 0
        
        return {
            "success_rate": sanitize_float(succ_rate),
            "failed_swaps": metrics["swaps_failed"],
            "vans_dispatched": metrics["vans_dispatched"],
            "incentives_paid": sanitize_float(metrics["incentives_paid"]),
            "total_opex": sanitize_float(total_opex),
            "avg_detour_mins": sanitize_float(avg_detour),
            "time_series": time_series,
            "trip_logs": trip_logs,
            "van_logs": van_logs
        }

def run_simulation(num_riders, time_window_hours, random_seed, base_network_state):
    dur = int(time_window_hours * 60)
    engine = SimulationEngine(num_riders, dur, random_seed, base_network_state)
    
    base_res = engine.run_mode("baseline")
    prop_res = engine.run_mode("proposed")
    
    base_opex = base_res["total_opex"]
    prop_opex = prop_res["total_opex"]
    cost_savings_pct = ((base_opex - prop_opex) / base_opex * 100) if base_opex > 0 else 0.0
    vans_saved = max(0, base_res["vans_dispatched"] - prop_res["vans_dispatched"])
    succ_gain = prop_res["success_rate"] - base_res["success_rate"]
    
    time_series = []
    for i in range(min(len(base_res["time_series"]), len(prop_res["time_series"]))):
        b = base_res["time_series"][i]
        p = prop_res["time_series"][i]
        time_series.append({
            "hour": b["hour"],
            "baseline_stockout_incidents": b["stockouts"],
            "proposed_stockout_incidents": p["stockouts"],
            "baseline_active": b["active_commuters"],
            "proposed_active": p["active_commuters"],
            "stations_snap": p["stations_snap"],
            "baseline_vans": b["cumulative_vans"],
            "proposed_vans": p["cumulative_vans"],
            "cumulative_incentives": p["cumulative_incentives"]
        })

    return {
        "baseline": base_res,
        "proposed": prop_res,
        "comparison": {
            "cost_savings_pct": sanitize_float(cost_savings_pct),
            "vans_saved": vans_saved,
            "success_rate_gain_pct": sanitize_float(succ_gain)
        },
        "time_series_frames": time_series,
        "trip_logs": prop_res["trip_logs"],
        "van_logs": prop_res["van_logs"]
    }
