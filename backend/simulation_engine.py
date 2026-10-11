import math
import random
import copy
from backend.routing_engine import calculate_station_cost, v_avg
from backend.varanasi_network import varanasi_graph, haversine_km

def sanitize_float(v):
    if math.isinf(v) or math.isnan(v):
        return 999.0
    return round(float(v), 2)

RIDER_NAMES = [
    "Aarav Mishra", "Pooja Verma", "Vikram Singh", "Ananya Sharma", "Rahul Gupta",
    "Sneha Patel", "Rohan Tripathi", "Neha Pandey", "Amitabh Roy", "Priyanka Yadav",
    "Kunal Srivastava", "Divya Tiwari", "Siddharth Jha", "Kavita Rao", "Manish Dubey",
    "Swati Agarwal", "Gaurav Sen", "Ritu Chaubey", "Deepak Maurya", "Simran Kaur",
    "Aditya Shukla", "Shreya Das", "Naveen Upadhyay", "Tanvi Joshi", "Harish Chandra",
    "Megha Mukherjee", "Sanjay Sonkar", "Bhavna Dixit", "Arjun Kashyap", "Poonam Ojha",
    "Tarun Bhatt", "Juhi Chatterjee", "Vishal Keshari", "Ankita Agrahari", "Rohit Raj"
]

ORIGIN_HUBS = [
    {"name": "Lanka / BHU Gate", "coords": (25.2677, 82.9913), "sector": "Lanka"},
    {"name": "Durgakund Mandir Area", "coords": (25.2840, 82.9950), "sector": "Durgakund"},
    {"name": "Assi Ghat Neighborhood", "coords": (25.2900, 83.0060), "sector": "Assi"},
    {"name": "Bhelupur Residential", "coords": (25.2980, 82.9920), "sector": "Bhelupur"},
    {"name": "Sigra Stadium Zone", "coords": (25.3160, 82.9850), "sector": "Sigra"},
    {"name": "Banaras Station Area", "coords": (25.2830, 82.9680), "sector": "Manduadih"},
    {"name": "Shivpur Central", "coords": (25.3520, 82.9750), "sector": "Shivpur"},
    {"name": "Pandeypur Enclave", "coords": (25.3400, 83.0100), "sector": "Pandeypur"},
    {"name": "Sarnath Road Junction", "coords": (25.3650, 83.0220), "sector": "Sarnath"}
]

DEST_HUBS = [
    {"name": "Godowlia Commercial Hub", "coords": (25.3090, 83.0050), "sector": "Godowlia"},
    {"name": "Dashashwamedh Main Ghat", "coords": (25.3060, 83.0100), "sector": "Dashashwamedh"},
    {"name": "Varanasi Cantt Station (Junction)", "coords": (25.3280, 82.9860), "sector": "Cantt"},
    {"name": "Chowk Vishwanath Corridor", "coords": (25.3110, 83.0120), "sector": "Chowk"},
    {"name": "Maidagin Town Hall", "coords": (25.3180, 83.0130), "sector": "Maidagin"},
    {"name": "Kachahri Circuit House (Civil Lines)", "coords": (25.3360, 82.9780), "sector": "Civil Lines"},
    {"name": "Lahurabir Market", "coords": (25.3190, 82.9950), "sector": "Lahurabir"},
    {"name": "DLW Administrative Hub", "coords": (25.2750, 82.9620), "sector": "DLW"}
]

def format_clock_time(minute_offset: int) -> str:
    """Formats minute offset from 08:00 AM master clock."""
    total_mins = 8 * 60 + int(minute_offset)
    h = (total_mins // 60) % 24
    m = total_mins % 60
    ampm = "AM" if h < 12 else "PM"
    display_h = h if h <= 12 else h - 12
    if display_h == 0:
        display_h = 12
    return f"{display_h:02d}:{m:02d} {ampm}"

class FleetSimulationEngine:
    def __init__(self, num_riders: int = 35, duration_minutes: int = 120, seed: int = 42, base_network_state: dict = None):
        self.num_riders = num_riders
        self.duration = duration_minutes
        self.seed = seed
        self.base_network_state = base_network_state or {}
        self.speed_kmh = 18.0 # Average city e-scooter speed (km/h)

    def run(self):
        random.seed(self.seed)
        base_stations = self.base_network_state.get("stations") or varanasi_graph.stations
        stations = copy.deepcopy(base_stations)
        for s in stations:
            s["charging_queue"] = []
            s["stockout_time"] = 0
            s["Li"] = 0
            s["total_swaps"] = 0
            if "capacity" not in s:
                s["capacity"] = s.get("Bi", 10) + s.get("Ei", 5)

        # 1. Generate Rider Commute Trips
        riders = []
        for i in range(self.num_riders):
            r_id = f"R-{101 + i}"
            r_name = RIDER_NAMES[i % len(RIDER_NAMES)]
            
            # Stagger start times across 0 to 95 mins so riders are active continuously throughout 2h
            t_start = int(random.uniform(0, max(10, self.duration - 25)))
            
            orig_info = random.choice(ORIGIN_HUBS)
            dest_info = random.choice(DEST_HUBS)
            
            o_lat = orig_info["coords"][0] + (random.random() - 0.5) * 0.005
            o_lon = orig_info["coords"][1] + (random.random() - 0.5) * 0.005
            d_lat = dest_info["coords"][0] + (random.random() - 0.5) * 0.005
            d_lon = dest_info["coords"][1] + (random.random() - 0.5) * 0.005
            
            # Initial low battery state (14% - 22%)
            battery_start = round(random.uniform(14.0, 22.0), 1)
            
            # Find optimal station via Directional A* cost evaluation
            best_candidate = None
            min_cost = float('inf')
            best_incentive = 2.0
            
            for s in stations:
                cost = calculate_station_cost(s, o_lat, o_lon, d_lat, d_lon)
                if cost and cost.get("eligible") and cost.get("f") is not None and cost["f"] < min_cost:
                    min_cost = cost["f"]
                    best_candidate = s
                    best_incentive = cost.get("I", 2.0)
            
            if not best_candidate:
                # Fallback to nearest station
                best_candidate = min(stations, key=lambda s: haversine_km(o_lat, o_lon, s["latitude"], s["longitude"]))
                best_incentive = 1.5
                
            # Build route coordinates passing through initial locked station
            s_lat = best_candidate["latitude"]
            s_lon = best_candidate["longitude"]
            route_coords, total_dist = varanasi_graph.get_via_route_coords(o_lat, o_lon, s_lat, s_lon, d_lat, d_lon)
            
            leg1_coords, leg1_dist = varanasi_graph.get_shortest_path_coords(o_lat, o_lon, s_lat, s_lon)
            leg2_coords, leg2_dist = varanasi_graph.get_shortest_path_coords(s_lat, s_lon, d_lat, d_lon)
            
            # Cumulative distance along polyline for 60FPS interpolation
            cum_dists = [0.0]
            for c_idx in range(len(route_coords) - 1):
                d = haversine_km(route_coords[c_idx][0], route_coords[c_idx][1], route_coords[c_idx+1][0], route_coords[c_idx+1][1])
                cum_dists.append(cum_dists[-1] + d)
            
            # Calculate realistic arrival times based on speed
            mins_to_station = max(2.5, (leg1_dist / self.speed_kmh) * 60.0)
            mins_to_dest = max(2.0, (leg2_dist / self.speed_kmh) * 60.0)
            
            t_swap = t_start + mins_to_station
            t_arrival = t_swap + mins_to_dest + 1.0 # +1 min swap operation buffer
            
            riders.append({
                "rider_id": r_id,
                "name": r_name,
                "origin_name": orig_info["name"],
                "origin_coords": [round(o_lat, 6), round(o_lon, 6)],
                "dest_name": dest_info["name"],
                "dest_coords": [round(d_lat, 6), round(d_lon, 6)],
                "t_start": t_start,
                "t_swap": round(t_swap, 2),
                "t_arrival": round(t_arrival, 2),
                "battery_start": battery_start,
                "battery_at_swap": max(5.0, round(battery_start - (leg1_dist * 3.2), 1)),
                "battery_post_swap": 100.0,
                "battery_at_dest": max(85.0, round(100.0 - (leg2_dist * 2.8), 1)),
                "locked_station_id": best_candidate["id"],
                "locked_station_name": best_candidate.get("name", f"Station {best_candidate['id']}"),
                "incentive": round(best_incentive, 2),
                "route_coords": route_coords,
                "cum_dists": cum_dists,
                "total_dist": round(total_dist, 3),
                "dist_to_station": round(leg1_dist, 3),
                "has_rerouted": False,
                "reroute_event": None
            })

        # 2. Programmatically Inject Mid-Way Rerouting Deals for a Subset of Riders
        # Select 4-6 riders to experience mid-route smart-switching when nearby station incentives spike
        riders.sort(key=lambda r: r["t_start"])
        reroute_candidates = [r for r in riders if (r["t_swap"] - r["t_start"]) >= 4.0][:5]
        
        for r in reroute_candidates:
            # Mid-point during leg 1
            t_reroute = round(r["t_start"] + (r["t_swap"] - r["t_start"]) * 0.45, 2)
            
            # Find current rider coordinates at t_reroute
            frac = 0.45
            seg_dist = r["dist_to_station"] * frac
            cur_lat, cur_lon = r["route_coords"][0]
            for c_idx in range(len(r["cum_dists"]) - 1):
                if r["cum_dists"][c_idx + 1] >= seg_dist:
                    p0 = r["route_coords"][c_idx]
                    p1 = r["route_coords"][c_idx + 1]
                    s_len = r["cum_dists"][c_idx + 1] - r["cum_dists"][c_idx]
                    f = (seg_dist - r["cum_dists"][c_idx]) / max(1e-5, s_len)
                    cur_lat = p0[0] + (p1[0] - p0[0]) * f
                    cur_lon = p0[1] + (p1[1] - p0[1]) * f
                    break
                    
            # Pick an alternative station in catchment that offers higher incentive
            alt_stations = [s for s in stations if s["id"] != r["locked_station_id"] and haversine_km(cur_lat, cur_lon, s["latitude"], s["longitude"]) <= 2.2]
            if alt_stations:
                new_st = max(alt_stations, key=lambda s: s.get("Bi", 8) - s.get("Li", 0))
                new_inc = round(r["incentive"] + random.uniform(1.20, 2.00), 2)
                
                # Recalculate route from mid-way coords -> new station -> destination
                new_route_coords, new_tot_dist = varanasi_graph.get_via_route_coords(
                    cur_lat, cur_lon, new_st["latitude"], new_st["longitude"], r["dest_coords"][0], r["dest_coords"][1]
                )
                
                # Prefix the already traveled coordinates
                traveled_prefix = [pt for idx, pt in enumerate(r["route_coords"]) if r["cum_dists"][idx] <= seg_dist]
                full_new_route = traveled_prefix + new_route_coords
                
                new_cum_dists = [0.0]
                for c_idx in range(len(full_new_route) - 1):
                    d = haversine_km(full_new_route[c_idx][0], full_new_route[c_idx][1], full_new_route[c_idx+1][0], full_new_route[c_idx+1][1])
                    new_cum_dists.append(new_cum_dists[-1] + d)
                
                leg1_sub_coords, leg1_sub_dist = varanasi_graph.get_shortest_path_coords(cur_lat, cur_lon, new_st["latitude"], new_st["longitude"])
                leg2_sub_coords, leg2_sub_dist = varanasi_graph.get_shortest_path_coords(new_st["latitude"], new_st["longitude"], r["dest_coords"][0], r["dest_coords"][1])
                
                new_mins_to_station = max(1.8, (leg1_sub_dist / self.speed_kmh) * 60.0)
                new_mins_to_dest = max(2.0, (leg2_sub_dist / self.speed_kmh) * 60.0)
                
                new_t_swap = round(t_reroute + new_mins_to_station, 2)
                new_t_arrival = round(new_t_swap + new_mins_to_dest + 1.0, 2)
                
                r["has_rerouted"] = True
                r["reroute_event"] = {
                    "time": t_reroute,
                    "clock": format_clock_time(t_reroute),
                    "old_station_id": r["locked_station_id"],
                    "old_station_name": r["locked_station_name"],
                    "new_station_id": new_st["id"],
                    "new_station_name": new_st.get("name", f"Station {new_st['id']}"),
                    "old_incentive": r["incentive"],
                    "new_incentive": new_inc,
                    "reroute_coords": [round(cur_lat, 6), round(cur_lon, 6)],
                    "new_route_coords": full_new_route,
                    "new_cum_dists": new_cum_dists,
                    "new_total_dist": round(new_cum_dists[-1], 3),
                    "new_dist_to_station": round(seg_dist + leg1_sub_dist, 3),
                    "new_t_swap": new_t_swap,
                    "new_t_arrival": new_t_arrival
                }

        # 3. Simulate Timeline Minute-by-Minute (0 to 120 mins)
        time_series_frames = []
        swap_events_log = []
        reroute_events_log = []
        
        cumulative_incentives = 0.0
        cumulative_swaps = 0
        cumulative_reroutes = 0
        
        for t in range(self.duration + 1):
            clock_str = format_clock_time(t)
            
            # Process Battery Charging queues (batteries finished charging replenish Bi)
            for s in stations:
                finished = [ct for ct in s["charging_queue"] if ct <= t]
                for _ in finished:
                    s["Bi"] = min(s["capacity"], s["Bi"] + 1)
                s["charging_queue"] = [ct for ct in s["charging_queue"] if ct > t]
            
            # Check for Swap Events happening in minute t
            events_this_min = []
            for r in riders:
                swap_time = r["reroute_event"]["new_t_swap"] if (r["has_rerouted"] and t >= r["reroute_event"]["time"]) else r["t_swap"]
                target_station_id = r["reroute_event"]["new_station_id"] if (r["has_rerouted"] and t >= r["reroute_event"]["time"]) else r["locked_station_id"]
                target_station_name = r["reroute_event"]["new_station_name"] if (r["has_rerouted"] and t >= r["reroute_event"]["time"]) else r["locked_station_name"]
                
                # If swap occurs at minute t
                if int(swap_time) == t:
                    st = next((s for s in stations if s["id"] == target_station_id), None)
                    if st:
                        if st["Bi"] > 0:
                            st["Bi"] -= 1
                            st["Ei"] = max(0, st.get("Ei", 0) - 1)
                            st["total_swaps"] += 1
                            st["charging_queue"].append(t + random.randint(30, 45)) # Recharges in 35 mins
                        
                        cumulative_swaps += 1
                        cumulative_incentives += r["reroute_event"]["new_incentive"] if r["has_rerouted"] else r["incentive"]
                        
                        ev = {
                            "type": "swap",
                            "minute": t,
                            "clock": clock_str,
                            "rider_id": r["rider_id"],
                            "rider_name": r["name"],
                            "station_id": target_station_id,
                            "station_name": target_station_name,
                            "incentive": r["reroute_event"]["new_incentive"] if r["has_rerouted"] else r["incentive"]
                        }
                        events_this_min.append(ev)
                        swap_events_log.append(ev)
                        
                # Check for Reroute Events happening at minute t
                if r["has_rerouted"] and int(r["reroute_event"]["time"]) == t:
                    cumulative_reroutes += 1
                    ev = {
                        "type": "reroute",
                        "minute": t,
                        "clock": clock_str,
                        "rider_id": r["rider_id"],
                        "rider_name": r["name"],
                        "old_station_id": r["reroute_event"]["old_station_id"],
                        "new_station_id": r["reroute_event"]["new_station_id"],
                        "new_station_name": r["reroute_event"]["new_station_name"],
                        "new_incentive": r["reroute_event"]["new_incentive"],
                        "coords": r["reroute_event"]["reroute_coords"]
                    }
                    events_this_min.append(ev)
                    reroute_events_log.append(ev)
            
            # Active riders at minute t
            active_riders_count = 0
            for r in riders:
                arr_time = r["reroute_event"]["new_t_arrival"] if r["has_rerouted"] else r["t_arrival"]
                if r["t_start"] <= t <= arr_time:
                    active_riders_count += 1
            
            # Snapshot of stations
            stations_snap = []
            for st in stations:
                bi = st["Bi"]
                cap = st["capacity"]
                status = "high" if bi >= 6 else ("low" if bi <= 2 else "medium")
                stations_snap.append({
                    "id": st["id"],
                    "name": st.get("name", f"Station {st['id']}"),
                    "sector": st.get("sector", "Varanasi"),
                    "latitude": st["latitude"],
                    "longitude": st["longitude"],
                    "Bi": bi,
                    "Ei": st.get("Ei", 0),
                    "Li": st.get("Li", 0),
                    "capacity": cap,
                    "status": status,
                    "total_swaps": st["total_swaps"]
                })
                
            time_series_frames.append({
                "minute": t,
                "clock": clock_str,
                "active_riders": active_riders_count,
                "cumulative_swaps": cumulative_swaps,
                "cumulative_incentives": round(cumulative_incentives, 2),
                "cumulative_reroutes": cumulative_reroutes,
                "stations_snap": stations_snap,
                "events": events_this_min
            })
            
        return {
            "duration_minutes": self.duration,
            "start_clock": "08:00 AM",
            "end_clock": format_clock_time(self.duration),
            "num_riders": len(riders),
            "riders": riders,
            "stations_initial": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "sector": s.get("sector", "Varanasi"),
                    "latitude": s["latitude"],
                    "longitude": s["longitude"],
                    "Bi": s["Bi"],
                    "Ei": s.get("Ei", 0),
                    "capacity": s["capacity"]
                }
                for s in stations
            ],
            "time_series_frames": time_series_frames,
            "swap_events": swap_events_log,
            "reroute_events": reroute_events_log,
            "total_incentives": round(cumulative_incentives, 2),
            "total_swaps": cumulative_swaps,
            "total_reroutes": cumulative_reroutes
        }

def run_simulation(num_riders: int = 35, time_window_hours: float = 2.0, random_seed: int = 42, base_network_state: dict = None):
    duration_mins = int(time_window_hours * 60)
    engine = FleetSimulationEngine(num_riders, duration_mins, random_seed, base_network_state)
    return engine.run()
