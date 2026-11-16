"""Taxi zones used by the sample, with an approximate centre point for each.

The trip records (like real NYC TLC data since 2016) store pickup and drop-off zones, not GPS
points. These centres are approximate public locations used to place a trip on a map.
"""

# location_id: (name, latitude, longitude)
ZONES = {
    161: ("Midtown Center", 40.7580, -73.9776),
    236: ("Upper East Side North", 40.7779, -73.9530),
    237: ("Upper East Side South", 40.7680, -73.9640),
    186: ("Penn Station / Madison Sq West", 40.7496, -73.9925),
    142: ("Lincoln Square East", 40.7738, -73.9818),
    230: ("Times Square / Theatre District", 40.7590, -73.9865),
    138: ("LaGuardia Airport", 40.7740, -73.8720),
    132: ("JFK Airport", 40.6447, -73.7820),
    79: ("East Village", 40.7265, -73.9840),
    148: ("Lower East Side", 40.7170, -73.9870),
    234: ("Flatiron", 40.7410, -73.9900),
    107: ("Gramercy", 40.7368, -73.9845),
}

ZONE_NAMES = {zone_id: name for zone_id, (name, _, _) in ZONES.items()}
