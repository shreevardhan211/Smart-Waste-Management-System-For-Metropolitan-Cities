"""
optimization/route_planner.py
-------------------------------
Implements a simple but genuinely useful route-optimization algorithm for
waste collection trucks.

ALGORITHM: Nearest-Neighbor heuristic over bins that need collection
----------------------------------------------------------------------
1. Filter to only bins with fill_level >= COLLECTION_THRESHOLD (default 70%).
   No point routing a truck to an empty bin.
2. Starting from a depot (truck garage) location, repeatedly jump to the
   CLOSEST not-yet-visited "needs collection" bin (great-circle distance).
3. This produces a short, practical route without needing a heavyweight
   TSP solver -- nearest-neighbor is a well-known, easy-to-explain
   approximation that's good enough for a city-scale demo and is exactly
   the kind of heuristic real waste-management routing tools use as a
   first pass before more advanced optimization (e.g. OR-Tools, Google
   Routes API) in production.

Distance is computed with the Haversine formula (great-circle distance
between two lat/lng points on Earth), so it works correctly with the
real-world coordinates used for the bins.
"""

import math

# Threshold at which a bin is considered "needs collection" for routing
COLLECTION_THRESHOLD = 70

# Simulated truck depot location (could be a real garage/yard in production)
DEPOT = {"name": "Waste Collection Depot", "lat": 16.6995, "lng": 74.2356}


def haversine_distance(lat1, lng1, lat2, lng2):
    """
    Calculate the great-circle distance in kilometers between two
    lat/lng points using the Haversine formula.
    """
    R = 6371  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def optimize_route(bins, threshold=COLLECTION_THRESHOLD, depot=DEPOT):
    """
    Given a list of bin dicts (each with bin_id, name, lat, lng, fill_level),
    return an ordered collection route using nearest-neighbor heuristic,
    plus summary stats.

    Returns a dict:
    {
        "route": [ {bin_id, name, lat, lng, fill_level, distance_from_prev_km}, ... ],
        "total_distance_km": float,
        "bins_needing_collection": int,
        "estimated_time_minutes": float
    }
    """
    # Step 1: filter to bins that actually need collection
    candidates = [b for b in bins if b.get("fill_level") is not None
                  and b["fill_level"] >= threshold]

    if not candidates:
        return {
            "route": [],
            "total_distance_km": 0,
            "bins_needing_collection": 0,
            "estimated_time_minutes": 0,
            "depot": depot
        }

    # Step 2: nearest-neighbor greedy walk starting from depot
    remaining = candidates.copy()
    current_lat, current_lng = depot["lat"], depot["lng"]
    route = []
    total_distance = 0.0

    while remaining:
        # Find the closest remaining bin to current position
        nearest = min(
            remaining,
            key=lambda b: haversine_distance(current_lat, current_lng, b["lat"], b["lng"])
        )
        dist = haversine_distance(current_lat, current_lng, nearest["lat"], nearest["lng"])
        total_distance += dist

        route.append({
            "bin_id": nearest["bin_id"],
            "name": nearest["name"],
            "lat": nearest["lat"],
            "lng": nearest["lng"],
            "fill_level": nearest["fill_level"],
            "distance_from_prev_km": round(dist, 2)
        })

        current_lat, current_lng = nearest["lat"], nearest["lng"]
        remaining.remove(nearest)

    # Step 3: estimate time -- assume avg 25 km/h city driving + 5 min stop per bin
    driving_minutes = (total_distance / 25) * 60
    stop_minutes = len(route) * 5
    estimated_time = driving_minutes + stop_minutes

    return {
        "route": route,
        "total_distance_km": round(total_distance, 2),
        "bins_needing_collection": len(route),
        "estimated_time_minutes": round(estimated_time, 1),
        "depot": depot
    }
