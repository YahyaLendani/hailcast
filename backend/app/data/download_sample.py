import json
import random
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Popular NYC Taxi Zones
ZONES = {
    161: "Midtown Center",
    236: "Upper East Side North",
    237: "Upper East Side South",
    186: "Penn Station / Madison Sq West",
    142: "Lincoln Square East",
    230: "Times Square / Theatre District",
    138: "LaGuardia Airport",
    132: "JFK Airport",
    79:  "East Village",
    148: "Lower East Side",
    234: "Flatiron",
    107: "Gramercy"
}

def generate_sample_dataset(output_path: Path, days: int = 7, base_trips_per_day: int = 1500):
    """Generate or download realistic multi-day NYC TLC trip dataset."""
    random.seed(42)
    np.random.seed(42)
    
    start_date = datetime(2024, 11, 3, 0, 0, 0)
    records = []
    
    zone_ids = list(ZONES.keys())

    for day in range(days):
        current_day = start_date + timedelta(days=day)
        is_weekend = current_day.weekday() in [5, 6]

        for hour in range(24):
            # Diurnal hourly demand curve
            if 0 <= hour <= 5:
                hourly_factor = 0.2
            elif 6 <= hour <= 9:
                hourly_factor = 1.6 if not is_weekend else 0.5  # Morning rush
            elif 10 <= hour <= 15:
                hourly_factor = 1.0
            elif 16 <= hour <= 20:
                hourly_factor = 1.9 if not is_weekend else 1.4  # Evening rush
            else:
                hourly_factor = 0.9 if not is_weekend else 1.5  # Nightlife

            # Add occasional artificial anomaly on Day 4 at 18:00 (e.g. major stadium event / concert spike)
            if day == 4 and hour == 18:
                hourly_factor *= 2.8

            trips_in_hour = int((base_trips_per_day / 24.0) * hourly_factor * np.random.uniform(0.85, 1.15))

            for _ in range(trips_in_hour):
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                p_time = current_day + timedelta(hours=hour, minutes=minute, seconds=second)

                p_loc = random.choice(zone_ids)
                d_loc = random.choice(zone_ids)

                is_airport = p_loc in [138, 132] or d_loc in [138, 132]
                if is_airport:
                    distance = round(float(np.random.normal(12.5, 3.0)), 2)
                    distance = max(5.0, distance)
                    duration_mins = round(distance * random.uniform(2.5, 4.0), 1)
                    fare = round(52.00 if (p_loc == 132 or d_loc == 132) else (distance * 2.8 + 10.0), 2)
                else:
                    distance = round(float(np.random.exponential(2.2) + 0.5), 2)
                    distance = min(25.0, max(0.4, distance))
                    duration_mins = round(max(3.0, distance * random.uniform(3.5, 6.0)), 1)
                    fare = round(3.00 + (distance * 2.8) + (duration_mins * 0.5), 2)

                d_time = p_time + timedelta(minutes=duration_mins)
                tip = round(fare * random.choice([0.15, 0.20, 0.25, 0.0]), 2)
                total = round(fare + tip + 2.50, 2)

                records.append({
                    "pickup_datetime": p_time.isoformat(),
                    "dropoff_datetime": d_time.isoformat(),
                    "passenger_count": random.choices([1, 2, 3, 4, 5], weights=[0.65, 0.18, 0.08, 0.05, 0.04])[0],
                    "trip_distance": distance,
                    "pickup_location_id": p_loc,
                    "dropoff_location_id": d_loc,
                    "fare_amount": fare,
                    "tip_amount": tip,
                    "total_amount": total,
                    "payment_type": random.choices(["Credit Card", "Cash"], weights=[0.82, 0.18])[0],
                    "is_replayed": True
                })

    records.sort(key=lambda x: x["pickup_datetime"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f)

    print(f"Generated {len(records)} realistic trip records at {output_path}")
    return records

if __name__ == "__main__":
    out = Path(__file__).parent / "sample_trips.json"
    generate_sample_dataset(out)

