import copy
from backend.varanasi_network import varanasi_graph

def generate_network_state():
    stations = copy.deepcopy(varanasi_graph.stations)
    
    # Active rider alert origin (Near Assi Ghat / Lanka corridor)
    o_alert = {
        "name": "Near Assi Ghat, Varanasi",
        "sector": "Assi Ghat Corridor",
        "latitude": 25.2862,
        "longitude": 83.0035
    }
    
    # Active rider destination (Varanasi Cantt Railway Station)
    d_dest = {
        "name": "Varanasi Cantt Station (Junction)",
        "sector": "Cantt Hub",
        "latitude": 25.3280,
        "longitude": 82.9860
    }
    
    return {
        "city": "Varanasi, UP, India",
        "center": [25.3176, 82.9739],
        "default_zoom": 13,
        "catchment_radius_km": 2.5,
        "stations": stations,
        "trip_request": {
            "origin": o_alert,
            "destination": d_dest
        },
        "road_network": varanasi_graph.topology
    }
