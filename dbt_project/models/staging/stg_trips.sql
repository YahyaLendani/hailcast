{{ config(materialized='view') }}

WITH source_data AS (
    SELECT
        id,
        event_id,
        pickup_datetime,
        dropoff_datetime,
        passenger_count,
        trip_distance,
        pickup_location_id,
        dropoff_location_id,
        fare_amount,
        tip_amount,
        total_amount,
        payment_type,
        is_replayed,
        ingested_at
    FROM {{ source('raw_data', 'raw_trips') }}
),

cleaned_data AS (
    SELECT
        id,
        event_id,
        pickup_datetime,
        dropoff_datetime,
        -- Duration in minutes
        ROUND(EXTRACT(EPOCH FROM (dropoff_datetime - pickup_datetime)) / 60.0, 2) AS trip_duration_minutes,
        COALESCE(passenger_count, 1) AS passenger_count,
        trip_distance,
        pickup_location_id,
        dropoff_location_id,
        fare_amount,
        tip_amount,
        total_amount,
        payment_type,
        is_replayed,
        ingested_at
    FROM source_data
    WHERE
        dropoff_datetime > pickup_datetime
        AND trip_distance > 0.0
        AND fare_amount >= 2.50
        AND passenger_count BETWEEN 1 AND 8
)

SELECT * FROM cleaned_data

