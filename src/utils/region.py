"""
src/utils/region.py
===================
Canonical region utilities shared by normalize.py and the supplier layer.

Single source of truth for ONS NUTS/ITL code decoding and region
normalisation. Both layers import from here — never duplicate this logic.
"""
from __future__ import annotations

# ONS NUTS1/ITL1 and NUTS2/ITL2 code map — all UK regions covered
ONS_REGION_CODES: dict[str, str] = {
    # England — NUTS1 / ITL1
    "UKC": "North East England",
    "UKD": "North West England",
    "UKE": "Yorkshire and The Humber",
    "UKF": "East Midlands",
    "UKG": "West Midlands",
    "UKH": "East of England",
    "UKI": "London",
    "UKJ": "South East England",
    "UKK": "South West England",
    # Devolved nations
    "UKL": "Wales",
    "UKM": "Scotland",
    "UKN": "Northern Ireland",
    # NUTS2/ITL2 sub-regions
    "UKC1": "Tees Valley and Durham",
    "UKC2": "Northumberland and Tyne and Wear",
    "UKD1": "Cumbria",
    "UKD3": "Greater Manchester",
    "UKD4": "Lancashire",
    "UKD6": "Cheshire",
    "UKD7": "Merseyside",
    "UKE1": "East Yorkshire and Northern Lincolnshire",
    "UKE2": "North Yorkshire",
    "UKE3": "South Yorkshire",
    "UKE4": "West Yorkshire",
    "UKF1": "Derbyshire and Nottinghamshire",
    "UKF2": "Leicestershire, Rutland and Northamptonshire",
    "UKF3": "Lincolnshire",
    "UKG1": "Herefordshire, Worcestershire and Warwickshire",
    "UKG2": "Shropshire and Staffordshire",
    "UKG3": "West Midlands (Met County)",
    "UKH1": "East Anglia",
    "UKH2": "Bedfordshire and Hertfordshire",
    "UKH3": "Essex",
    "UKI3": "Inner London — West",
    "UKI4": "Inner London — East",
    "UKI5": "Outer London — East and North East",
    "UKI6": "Outer London — South",
    "UKI7": "Outer London — West and North West",
    "UKJ1": "Berkshire, Buckinghamshire and Oxfordshire",
    "UKJ2": "Surrey, East and West Sussex",
    "UKJ3": "Hampshire and Isle of Wight",
    "UKJ4": "Kent",
    "UKK1": "Gloucestershire, Wiltshire and Bristol/Bath area",
    "UKK2": "Dorset and Somerset",
    "UKK3": "Cornwall and Isles of Scilly",
    "UKK4": "Devon",
    "UKL1": "West Wales and The Valleys",
    "UKL2": "East Wales",
    "UKM5": "North Eastern Scotland",
    "UKM6": "Highlands and Islands",
    "UKM7": "Eastern Scotland",
    "UKM8": "West Central Scotland",
    "UKM9": "Southern Scotland",
}

# Canonical region slugs used in market profile YAML tier lists.
# Maps human-readable names (lowercased) to a canonical slug.
REGION_SLUGS: dict[str, str] = {
    "north east england": "north_east",
    "north east": "north_east",
    "north west england": "north_west",
    "north west": "north_west",
    "yorkshire and the humber": "yorkshire",
    "yorkshire": "yorkshire",
    "east midlands": "east_midlands",
    "west midlands": "west_midlands",
    "east of england": "east_of_england",
    "london": "london",
    "inner london — west": "london",
    "inner london — east": "london",
    "outer london — east and north east": "london",
    "outer london — south": "london",
    "outer london — west and north west": "london",
    "south east england": "south_east",
    "south east": "south_east",
    "south west england": "south_west",
    "south west": "south_west",
    "wales": "wales",
    "scotland": "scotland",
    "northern ireland": "northern_ireland",
}


def decode_region(raw_region: str | None) -> str | None:
    """
    Convert ONS NUTS/ITL codes to readable region names.
    Pass-through if already a readable string or None.
    Canonical implementation — imported by normalize.py and supplier layer.
    """
    if not raw_region:
        return raw_region
    stripped = raw_region.strip()
    for length in (5, 4, 3):
        candidate = stripped[:length].upper()
        if candidate in ONS_REGION_CODES:
            return ONS_REGION_CODES[candidate]
    return stripped


def region_slug(region: str | None) -> str | None:
    """
    Map a decoded region name to its canonical slug for profile tier matching.
    Returns None if the region cannot be mapped.
    """
    if not region:
        return None
    return REGION_SLUGS.get(region.strip().lower())
