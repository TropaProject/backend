from typing import Dict

def build_rect_from_bbox(bbox: Dict[str, float]) -> str:
    """
    Наши bbox: {"min_lat": ..., "max_lat": ..., "min_lon": ..., "max_lon": ...}
    Geoapify rect требует: rect:min_lon,max_lat,max_lon,min_lat  (lon1,lat1,lon2,lat2)
    """
    min_lat = bbox["min_lat"]
    max_lat = bbox["max_lat"]
    min_lon = bbox["min_lon"]
    max_lon = bbox["max_lon"]
    return f"{min_lon},{max_lat},{max_lon},{min_lat}"

