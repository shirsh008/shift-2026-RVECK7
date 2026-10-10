active_reservations = {} # rider_id -> station_id

def get_station(network_state, station_id):
    for s in network_state["stations"]:
        if s["id"] == station_id:
            return s
    return None

def reserve_station(network_state, rider_id, station_id):
    station = get_station(network_state, station_id)
    if not station:
        return False, "Station not found."

    current_reserved_station_id = active_reservations.get(rider_id)
    
    b_avail = station["Bi"] - station["Li"]
    if b_avail <= 0 or station["Ei"] <= 0:
        return False, "Station unavailable (insufficient batteries or bays)."

    if current_reserved_station_id:
        if current_reserved_station_id == station_id:
            return True, station
        else:
            old_station = get_station(network_state, current_reserved_station_id)
            if old_station and old_station.get("Li", 0) > 0:
                old_station["Li"] -= 1
            
            station["Li"] += 1
            active_reservations[rider_id] = station_id
            return True, station

    station["Li"] += 1
    active_reservations[rider_id] = station_id
    return True, station

def release_station(network_state, rider_id, station_id):
    if active_reservations.get(rider_id) == station_id:
        station = get_station(network_state, station_id)
        if station and station["Li"] > 0:
            station["Li"] -= 1
        del active_reservations[rider_id]
        return True
    return False

def swap_reservation(network_state, rider_id, old_station_id, new_station_id):
    if active_reservations.get(rider_id) != old_station_id:
        return False, "Mismatched active reservation."

    # Release old
    release_station(network_state, rider_id, old_station_id)
    
    # Reserve new
    success, data = reserve_station(network_state, rider_id, new_station_id)
    if not success:
        # Rollback in case of failure
        station_old = get_station(network_state, old_station_id)
        if station_old:
            station_old["Li"] += 1
            active_reservations[rider_id] = old_station_id
        return False, data
        
    return True, data
