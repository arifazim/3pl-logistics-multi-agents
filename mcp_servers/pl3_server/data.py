"""Shared data for the consolidated 3PL MCP server."""

MARGIN_FLOOR_PCT = 12.0

# SF Bay Area Cities (100 locations)
BAY_AREA_CITIES = [
    "San Francisco", "Oakland", "San Jose", "Berkeley", "Fremont", "Palo Alto", "Mountain View",
    "Sunnyvale", "Santa Clara", "Milpitas", "Campbell", "Cupertino", "Los Gatos", "Saratoga",
    "Los Altos", "Menlo Park", "Redwood City", "San Mateo", "Daly City", "South San Francisco",
    "Hayward", "Union City", "Newark", "Alameda", "Dublin", "Pleasanton", "Livermore",
    "San Leandro", "Albany", "El Cerrito", "Richmond", "Concord", "Antioch", "Pittsburg",
    "Brentwood", "Oakley", "Martinez", "Benicia", "Vallejo", "Fairfield", "Vacaville",
    "Napa", "Sonoma", "Petaluma", "Santa Rosa", "Rohnert Park", "Windsor", "Healdsburg",
    "Calistoga", "American Canyon", "St. Helena", "Yountville", "Guerneville", "Sebastopol",
    "Cloverdale", "Cotati", "Novato", "San Anselmo", "Larkspur", "Mill Valley", "Corte Madera",
    "Fairfax", "Ross", "Belvedere", "Tiburon", "Sausalito", "Marinwood", "Ignacio",
    "Tracy", "Manteca", "Lodi", "Galt", "Elk Grove", "Sacramento", "West Sacramento",
    "Citrus Heights", "Roseville", "Rocklin", "Lincoln", "Auburn", "Placerville", "South Lake Tahoe",
    "Stockton", "Lathrop", "Ripon", "Escalon", "Lockeford", "Gustine", "Merced", "Turlock",
    "Modesto", "Ceres", "Delhi", "Los Banos", "Dos Palos", "Firebaugh", "Chowchilla", "Madera",
    "Fresno", "Clovis", "Sanger", "Selma", "Kingsburg", "Reedley", "Orange Cove", "Dinuba",
    "Visalia", "Tulare", "Porterville", "Hanford", "Lemoore", "Corcoran", "Parlier", "Sultana",
    "Bakersfield", "Oildale", "Wasco", "Shafter", "Taft", "Lebec", "Grapevine", "Castaic",
    "Valencia", "Santa Clarita", "Canyon Country", "Newhall", "Acton", "Agua Dulce", "Palmdale",
    "Lancaster", "Quartz Hill", "Rosamond", "California City", "Mojave", "Boron", "Barstow",
    "Needles", "Bullhead City", "Kingman", "Henderson", "Las Vegas", "North Las Vegas", "Summerlin",
    "Hollywood", "West Hollywood", "Beverly Hills", "Santa Monica", "Venice", "Culver City", "Malibu",
    "Thousand Oaks", "Simi Valley", "Moorpark", "Newbury Park", "Camarillo", "Oxnard", "Ventura",
    "Santa Barbara", "Goleta", "Carpinteria", "Montecito", "Summerland", "Santa Ynez", "Lompoc",
    "Nipomo", "Arroyo Grande", "Morro Bay", "Cambria", "San Simeon", "Big Sur", "Carmel",
]

# Bay Area lanes with rates
CUSTOMER_RATES = {
    "San Francisco->Oakland": {"base_rate": 280, "target_margin_pct": 14},
    "San Francisco->San Jose": {"base_rate": 320, "target_margin_pct": 15},
    "Oakland->San Francisco": {"base_rate": 280, "target_margin_pct": 14},
    "San Jose->San Francisco": {"base_rate": 320, "target_margin_pct": 15},
    "Berkeley->Palo Alto": {"base_rate": 220, "target_margin_pct": 13},
    "Fremont->Mountain View": {"base_rate": 180, "target_margin_pct": 12},
    "Tracy->Fremont": {"base_rate": 350, "target_margin_pct": 15},
    "Manteca->Hayward": {"base_rate": 400, "target_margin_pct": 12},
    "Vallejo->Concord": {"base_rate": 200, "target_margin_pct": 13},
    "San Rafael->Napa": {"base_rate": 250, "target_margin_pct": 14},
    "Santa Clara->Los Gatos": {"base_rate": 150, "target_margin_pct": 12},
    "Sunnyvale->Cupertino": {"base_rate": 80, "target_margin_pct": 11},
    "Redwood City->San Mateo": {"base_rate": 100, "target_margin_pct": 11},
    "Fremont->Hayward": {"base_rate": 120, "target_margin_pct": 12},
    "Oakland->Berkeley": {"base_rate": 60, "target_margin_pct": 10},
    "San Jose->Santa Clara": {"base_rate": 100, "target_margin_pct": 12},
    "Palo Alto->Menlo Park": {"base_rate": 50, "target_margin_pct": 10},
    "Mountain View->Sunnyvale": {"base_rate": 60, "target_margin_pct": 11},
    "Daly City->South San Francisco": {"base_rate": 90, "target_margin_pct": 10},
    "Alameda->Oakland": {"base_rate": 40, "target_margin_pct": 10},
    "Pleasanton->Dublin": {"base_rate": 80, "target_margin_pct": 11},
    "Livermore->Tracy": {"base_rate": 180, "target_margin_pct": 12},
    "Antioch->Pittsburg": {"base_rate": 70, "target_margin_pct": 10},
    "Brentwood->Oakley": {"base_rate": 90, "target_margin_pct": 10},
    "Napa->Sonoma": {"base_rate": 120, "target_margin_pct": 12},
    "Santa Rosa->Petaluma": {"base_rate": 150, "target_margin_pct": 13},
    "Rohnert Park->Windsor": {"base_rate": 80, "target_margin_pct": 11},
    "Vacaville->Fairfield": {"base_rate": 100, "target_margin_pct": 11},
    "Sacramento->West Sacramento": {"base_rate": 140, "target_margin_pct": 12},
    "Roseville->Rocklin": {"base_rate": 160, "target_margin_pct": 12},
    "Elk Grove->Sacramento": {"base_rate": 180, "target_margin_pct": 13},
    "Galt->Lodi": {"base_rate": 220, "target_margin_pct": 14},
    "Cerritos->Norwalk": {"base_rate": 100, "target_margin_pct": 11},
    "Downey->Bellflower": {"base_rate": 80, "target_margin_pct": 10},
    "Long Beach->Compton": {"base_rate": 90, "target_margin_pct": 11},
    "Inglewood->Hawthorne": {"base_rate": 70, "target_margin_pct": 10},
    "Torrance->Redondo Beach": {"base_rate": 80, "target_margin_pct": 10},
    "Manhattan Beach->Hermosa Beach": {"base_rate": 85, "target_margin_pct": 11},
    "Santa Monica->Venice": {"base_rate": 60, "target_margin_pct": 10},
    "Beverly Hills->West Hollywood": {"base_rate": 90, "target_margin_pct": 11},
    "Hollywood->Los Angeles": {"base_rate": 110, "target_margin_pct": 12},
    "Pasadena->Glendale": {"base_rate": 120, "target_margin_pct": 12},
    "Burbank->Studio City": {"base_rate": 130, "target_margin_pct": 13},
    "Van Nuys->Sherman Oaks": {"base_rate": 110, "target_margin_pct": 12},
    "Westwood->Brentwood": {"base_rate": 90, "target_margin_pct": 11},
}

# Generate vendor rates for all Bay Area lanes
VENDOR_RATES = []
vendor_names = ["SwiftTransport", "FalconFreight", "EcoHaul", "BayAreaHaul", "PeninsulaFreight", "EastBayCarriers"]
vendor_ids = ["V001", "V002", "V003", "V004", "V005", "V006"]

for idx, lane in enumerate(list(CUSTOMER_RATES.keys())[:30]):
    for v_idx, (vid, vname) in enumerate(zip(vendor_ids, vendor_names)):
        base = CUSTOMER_RATES[lane]["base_rate"]
        rate = base * (0.85 + (v_idx * 0.03) + (idx % 10) * 0.01)
        rel = 85 + v_idx * 2 + (idx % 5)
        VENDOR_RATES.append({
            "vendor_id": vid,
            "lane": lane,
            "rate": round(rate, 2),
            "reliability_score": min(rel, 99),
        })

VENDOR_DIRECTORY = {
    "V001": {
        "name": "SwiftTransport",
        "reliability_score": 92,
        "on_time_delivery_rate": 97,
        "status": "Preferred",
    },
    "V002": {
        "name": "FalconFreight",
        "reliability_score": 95,
        "on_time_delivery_rate": 96,
        "status": "Preferred",
    },
    "V003": {
        "name": "EcoHaul",
        "reliability_score": 88,
        "on_time_delivery_rate": 86,
        "status": "Approved",
    },
    "V004": {
        "name": "BayAreaHaul",
        "reliability_score": 90,
        "on_time_delivery_rate": 94,
        "status": "Approved",
    },
    "V005": {
        "name": "PeninsulaFreight",
        "reliability_score": 87,
        "on_time_delivery_rate": 91,
        "status": "Approved",
    },
    "V006": {
        "name": "EastBayCarriers",
        "reliability_score": 93,
        "on_time_delivery_rate": 95,
        "status": "Preferred",
    },
}

POLICIES = [
    {"name": "margin_protection", "rule": "margin >= 12%", "threshold": 12.0, "op": "gte"},
    {"name": "sla_compliance", "rule": "delivery_time <= 24h", "threshold": 24.0, "op": "lte"},
    {"name": "weight_limit", "rule": "weight <= 45000 lbs", "threshold": 45000.0, "op": "lte"},
]

TELEMETRY_SNAPSHOT = {
    "shipments_today": 47,
    "on_time_rate": 92.5,
    "margin_avg_pct": 14.2,
}

SHIPMENTS = [
    {
        "id": "S001",
        "origin": "Tracy",
        "destination": "Fremont",
        "pallets": 10,
        "weight": 5000,
        "status": "pending",
    },
]


def _build_eval_shipments() -> list[dict]:
    """Build deterministic shipment cases for local eval and dashboard playback."""
    lanes = list(CUSTOMER_RATES.keys())[:50]
    samples = []

    for idx in range(100):
        lane = lanes[idx % len(lanes)]
        parts = lane.split("->")
        sla_tier = "express" if idx % 4 == 0 else "standard"
        weight = 800 + ((idx * 375) % 12500)
        delivery_time = 18 + (idx % 12)
        shipment_id = f"EVAL-{idx + 1:03d}"
        samples.append(
            {
                "shipment_id": shipment_id,
                "lane": lane,
                "origin": parts[0],
                "destination": parts[1],
                "weight": weight,
                "pallets": 2 + (idx % 24),
                "sla_tier": sla_tier,
                "delivery_time": delivery_time,
                "customer": f"Customer {idx + 1:03d}",
                "expected_margin_floor_pct": MARGIN_FLOOR_PCT,
            }
        )
    return samples


EVAL_SHIPMENTS = _build_eval_shipments()

SLA_PREMIUM = {"standard": 0.0, "express": 0.15}
