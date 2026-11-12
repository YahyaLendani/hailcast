{{ config(materialized='table') }}

WITH stg_trips AS (
    SELECT * FROM {{ ref('stg_trips') }}
),

hourly_aggregates AS (
    SELECT
        DATE_TRUNC('hour', pickup_datetime) AS time_bucket,
        pickup_location_id AS location_id,
        COUNT(id) AS trip_count,
        SUM(passenger_count) AS total_passengers,
        ROUND(AVG(trip_distance), 2) AS avg_distance,
        ROUND(AVG(fare_amount), 2) AS avg_fare,
        ROUND(SUM(total_amount), 2) AS total_revenue,
        ROUND(AVG(trip_duration_minutes), 2) AS avg_duration_minutes,
        NOW() AS updated_at
    FROM stg_trips
    GROUP BY 1, 2
)

SELECT * FROM hourly_aggregates

