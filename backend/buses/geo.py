from math import cos, radians

KM_PER_DEG_LAT = 111.32


def route_bbox(path):
    """(min_lat, min_lng, max_lat, max_lng) of a [[lat, lng], ...] path."""
    lats = [p[0] for p in path]
    lngs = [p[1] for p in path]
    return min(lats), min(lngs), max(lats), max(lngs)


def is_near_route_bbox(lat, lng, path, margin_km=5.0):
    """True if the point lies inside the route's bounding box grown by `margin_km` on every side."""
    min_lat, min_lng, max_lat, max_lng = route_bbox(path)
    dlat = margin_km / KM_PER_DEG_LAT
    mid_lat = (min_lat + max_lat) / 2
    dlng = margin_km / (KM_PER_DEG_LAT * max(cos(radians(mid_lat)), 0.01))
    return (min_lat - dlat <= lat <= max_lat + dlat) and (min_lng - dlng <= lng <= max_lng + dlng)