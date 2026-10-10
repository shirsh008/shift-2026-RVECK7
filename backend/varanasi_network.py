import os
import math
import random
import numpy as np
import osmnx as ox
import networkx as nx
from typing import Dict, List, Tuple, Any

VARANASI_CENTER = (25.3176, 82.9739)
CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHML_CACHE = os.path.join(CACHE_DIR, "varanasi_osm.graphml")

# Landmark names to associate with sampled 50 stations
VARANASI_SECTOR_NAMES = [
    ("BHU Lanka Gate", "Lanka"),
    ("Assi Ghat Crossing", "Assi"),
    ("Durgakund Mandir", "Durgakund"),
    ("Bhelupur Thana", "Bhelupur"),
    ("IP Vijaya Crossing", "Bhelupur"),
    ("Sonarpura Chowk", "Sonarpura"),
    ("Rathyatra Crossing", "Rathyatra"),
    ("Mahmoorganj Hub", "Mahmoorganj"),
    ("Banaras Manduadih Station", "Manduadih"),
    ("Godowlia Central", "Godowlia"),
    ("Dashashwamedh Ghat", "Dashashwamedh"),
    ("Girjaghar Crossing", "Godowlia"),
    ("Chowk Vishwanath Corridor", "Chowk"),
    ("Manikarnika Ghat Road", "Chowk"),
    ("Maidagin Town Hall", "Maidagin"),
    ("Kabir Chaura Crossing", "Kabir Chaura"),
    ("Sigra Stadium Hub", "Sigra"),
    ("Chitranjan Park Rd", "Sigra"),
    ("Lahurabir Crossing", "Lahurabir"),
    ("Chetganj Chowk", "Chetganj"),
    ("Andhrapul Bridge", "Cantt"),
    ("Varanasi Cantt Station (Junction)", "Cantt"),
    ("Cantt Roadways Bus Stand", "Cantt"),
    ("Nadesar Mint House", "Nadesar"),
    ("Kachahri Circuit House", "Civil Lines"),
    ("Orderly Bazar", "Civil Lines"),
    ("Pandeypur Crossing", "Pandeypur"),
    ("Sarnath Road Junction", "Sarnath"),
    ("Teliyabagh Crossing", "Teliyabagh"),
    ("Golgadda Chowk", "Golgadda"),
    ("Rajghat Malviya Bridge", "Rajghat"),
    ("Shivpur Central Crossing", "Shivpur"),
    ("DLW Main Gate", "DLW"),
    ("Sunderpur Chowk", "Sunderpur"),
    ("Kakarmatta Flyover", "Kakarmatta"),
    ("Tulsidas Ghat Marg", "Assi"),
    ("Harishchandra Ghat Road", "Ghats"),
    ("Madanpura Silk Corridor", "Madanpura"),
    ("Lallapura Crossing", "Lallapura"),
    ("Jaitpura Chowk", "Jaitpura"),
    ("Alaipur Junction", "Alaipur"),
    ("Ashapur Crossing", "Sarnath"),
    ("Panchkroshi Marg", "Pandeypur"),
    ("Tagore Town Corridor", "Orderly Bazar"),
    ("Bhojubeer Crossing", "Bhojubeer"),
    ("Vidyapeeth Marg", "Sigra"),
    ("Gurubagh Crossing", "Rathyatra"),
    ("Kedar Ghat Lane", "Sonarpura"),
    ("Shivala Ghat Road", "Shivala"),
    ("Paharia Industrial Hub", "Paharia")
]

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class VaranasiOSMNetworkManager:
    def __init__(self):
        self.graph = None
        self.node_ids = []
        self.node_coords = None
        self.stations: List[Dict[str, Any]] = []
        self.topology: Dict[str, Any] = {"nodes": [], "edges": []}
        self.load_or_fetch_graph()
        self.build_spatial_index()
        self.generate_50_charging_stations()
        self.prepare_topology()

    def load_or_fetch_graph(self):
        """Loads Varanasi street graph via OSMnx or local cached GraphML."""
        if os.path.exists(GRAPHML_CACHE):
            try:
                print(f"[OSMnx] Loading cached Varanasi graph from {GRAPHML_CACHE}...")
                self.graph = ox.load_graphml(GRAPHML_CACHE)
                self.graph = ox.convert.to_undirected(self.graph)
                print(f"[OSMnx] Loaded {len(self.graph.nodes)} nodes and {len(self.graph.edges)} edges.")
                return
            except Exception as e:
                print(f"[OSMnx] Cache load failed ({e}), re-fetching from OpenStreetMap...")

        print("[OSMnx] Fetching real Varanasi road network graph from OpenStreetMap...")
        try:
            G = ox.graph_from_point(VARANASI_CENTER, dist=4500, network_type='drive', simplify=True)
            self.graph = ox.convert.to_undirected(G)
            try:
                ox.save_graphml(self.graph, GRAPHML_CACHE)
                print(f"[OSMnx] Saved graph cache to {GRAPHML_CACHE}")
            except Exception as save_err:
                print(f"[OSMnx] Could not save graph cache: {save_err}")
            print(f"[OSMnx] Fetched {len(self.graph.nodes)} nodes and {len(self.graph.edges)} edges.")
        except Exception as e:
            print(f"[OSMnx] Network fetch error ({e}), building fallback graph...")
            self._build_fallback_graph()

    def _build_fallback_graph(self):
        self.graph = nx.Graph()
        for i, (name, sec) in enumerate(VARANASI_SECTOR_NAMES):
            angle = (2 * math.pi * i) / len(VARANASI_SECTOR_NAMES)
            r = 0.015 + (i % 3) * 0.01
            lat = VARANASI_CENTER[0] + r * math.sin(angle)
            lon = VARANASI_CENTER[1] + r * math.cos(angle)
            self.graph.add_node(f"node_{i}", y=lat, x=lon, name=name, sector=sec)
            
        nodes = list(self.graph.nodes)
        for i in range(len(nodes)):
            n1 = nodes[i]
            n2 = nodes[(i + 1) % len(nodes)]
            dist = haversine_km(self.graph.nodes[n1]["y"], self.graph.nodes[n1]["x"], self.graph.nodes[n2]["y"], self.graph.nodes[n2]["x"])
            self.graph.add_edge(n1, n2, length=dist * 1000, name="Arterial Road")

    def build_spatial_index(self):
        """Builds vectorized coordinate cache for fast and exact nearest node search."""
        if not self.graph or len(self.graph.nodes) == 0:
            return
            
        self.node_ids = list(self.graph.nodes)
        coords_list = []
        for n in self.node_ids:
            d = self.graph.nodes[n]
            n_lat = d.get('y', d.get('lat', 25.3176))
            n_lon = d.get('x', d.get('lon', 82.9739))
            coords_list.append([n_lat, n_lon])
            
        self.node_coords = np.array(coords_list, dtype=np.float64)

    def find_nearest_node(self, lat: float, lon: float):
        """Finds the true nearest road network node using osmnx.distance.nearest_nodes with vectorized fallback."""
        try:
            best_node = ox.distance.nearest_nodes(self.graph, X=lon, Y=lat)
            n_data = self.graph.nodes[best_node]
            best_lat = n_data.get('y', n_data.get('lat', lat))
            best_lon = n_data.get('x', n_data.get('lon', lon))
            actual_dist = haversine_km(lat, lon, best_lat, best_lon)
            return best_node, actual_dist
        except Exception:
            if self.node_coords is None or len(self.node_coords) == 0:
                return None, 0.0
            target = np.array([lat, lon], dtype=np.float64)
            sq_dists = np.sum((self.node_coords - target)**2, axis=1)
            best_idx = int(np.argmin(sq_dists))
            best_node = self.node_ids[best_idx]
            best_lat, best_lon = self.node_coords[best_idx]
            actual_dist = haversine_km(lat, lon, best_lat, best_lon)
            return best_node, actual_dist

    def generate_50_charging_stations(self):
        """Spreads 50 battery swapping station nodes across the Varanasi road network graph."""
        self.stations = []
        if not self.graph or len(self.node_ids) == 0:
            return

        random.seed(42)
        step = max(1, len(self.node_ids) // 60)
        selected_nodes = self.node_ids[::step][:50]
        if len(selected_nodes) < 50:
            selected_nodes = random.sample(self.node_ids, min(50, len(self.node_ids)))

        for i, node_id in enumerate(selected_nodes):
            n_data = self.graph.nodes[node_id]
            lat = n_data.get('y', n_data.get('lat', 25.3176))
            lon = n_data.get('x', n_data.get('lon', 82.9739))
            
            sector_info = VARANASI_SECTOR_NAMES[i % len(VARANASI_SECTOR_NAMES)]
            name = f"Station S{i+1}: {sector_info[0]}"
            sector = sector_info[1]
            
            is_surplus = (i % 3 == 0) or any(k in sector for k in ["Lanka", "Pandeypur", "Shivpur", "Sarnath", "DLW", "Paharia"])
            capacity = random.randint(12, 16)
            bi = random.randint(8, 12) if is_surplus else random.randint(1, 4)
            ei = capacity - bi
            
            self.stations.append({
                "id": f"S{i+1}",
                "name": name,
                "sector": sector,
                "node_id": str(node_id),
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "Bi": bi,
                "Li": 0,
                "Ei": ei,
                "capacity": capacity,
                "type": "residential" if is_surplus else "commercial"
            })

        print(f"[Stations] Generated {len(self.stations)} battery charging stations across Varanasi.")

    def prepare_topology(self):
        """Prepares a vector topology representation of primary road segments for map rendering."""
        nodes_list = []
        edges_list = []
        
        all_edges = list(self.graph.edges(data=True))
        step = max(1, len(all_edges) // 1000)
        sampled_edges = all_edges[::step]
        
        visited_nodes = set()
        for u, v, d in sampled_edges:
            u_data = self.graph.nodes[u]
            v_data = self.graph.nodes[v]
            u_lat = u_data.get('y', u_data.get('lat', 25.3176))
            u_lon = u_data.get('x', u_data.get('lon', 82.9739))
            v_lat = v_data.get('y', v_data.get('lat', 25.3176))
            v_lon = v_data.get('x', v_data.get('lon', 82.9739))
            
            road_name = d.get('name', 'Varanasi Street')
            if isinstance(road_name, list):
                road_name = road_name[0]
                
            dist_km = haversine_km(u_lat, u_lon, v_lat, v_lon)
            
            edges_list.append({
                "source": str(u),
                "target": str(v),
                "name": str(road_name),
                "coordinates": [[round(u_lat, 6), round(u_lon, 6)], [round(v_lat, 6), round(v_lon, 6)]],
                "distance_km": round(dist_km, 3)
            })
            
            visited_nodes.add(u)
            visited_nodes.add(v)

        for n in visited_nodes:
            d = self.graph.nodes[n]
            n_lat = d.get('y', d.get('lat', 25.3176))
            n_lon = d.get('x', d.get('lon', 82.9739))
            nodes_list.append({
                "id": str(n),
                "latitude": round(n_lat, 6),
                "longitude": round(n_lon, 6)
            })

        self.topology = {
            "nodes": nodes_list,
            "edges": edges_list
        }

    def clean_path(self, coords: List[List[float]]) -> List[List[float]]:
        """Removes micro-duplicate coordinates from path sequences."""
        if len(coords) < 2:
            return coords
            
        cleaned = [coords[0]]
        for pt in coords[1:]:
            d = ((pt[0] - cleaned[-1][0])**2 + (pt[1] - cleaned[-1][1])**2)**0.5
            if d > 1e-6:
                cleaned.append(pt)
                
        return cleaned

    def get_shortest_path_coords(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float):
        """Calculates NetworkX shortest path between two coordinate pairs."""
        start_node, _ = self.find_nearest_node(start_lat, start_lon)
        end_node, _ = self.find_nearest_node(end_lat, end_lon)

        if not start_node or not end_node or start_node == end_node:
            return [[start_lat, start_lon], [end_lat, end_lon]], haversine_km(start_lat, start_lon, end_lat, end_lon)

        try:
            path_nodes = nx.shortest_path(self.graph, source=start_node, target=end_node, weight='length')
            coords = [[start_lat, start_lon]]
            total_dist = 0.0
            
            for i, n in enumerate(path_nodes):
                n_data = self.graph.nodes[n]
                n_lat = n_data.get('y', n_data.get('lat', 25.3176))
                n_lon = n_data.get('x', n_data.get('lon', 82.9739))
                coords.append([round(n_lat, 6), round(n_lon, 6)])
                if i > 0:
                    prev_n = self.graph.nodes[path_nodes[i-1]]
                    prev_lat = prev_n.get('y', prev_n.get('lat', 25.3176))
                    prev_lon = prev_n.get('x', prev_n.get('lon', 82.9739))
                    total_dist += haversine_km(prev_lat, prev_lon, n_lat, n_lon)
                    
            coords.append([end_lat, end_lon])
            cleaned = self.clean_path(coords)
            return cleaned, total_dist
        except Exception:
            return [[start_lat, start_lon], [end_lat, end_lon]], haversine_km(start_lat, start_lon, end_lat, end_lon)

    def get_via_route_coords(self, start_lat: float, start_lon: float, via_lat: float, via_lon: float, end_lat: float, end_lon: float):
        """Calculates two-segment shortest path passing through intermediate via node."""
        leg1_coords, leg1_dist = self.get_shortest_path_coords(start_lat, start_lon, via_lat, via_lon)
        leg2_coords, leg2_dist = self.get_shortest_path_coords(via_lat, via_lon, end_lat, end_lon)
        detour_coords = leg1_coords + leg2_coords[1:]
        detour_dist = leg1_dist + leg2_dist
        return detour_coords, detour_dist

varanasi_graph = VaranasiOSMNetworkManager()
