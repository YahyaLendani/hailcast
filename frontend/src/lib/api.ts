const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/stream";

export async function fetchOverview() {
  const res = await fetch(`${API_BASE}/analytics/overview`);
  return res.json();
}

export async function fetchHourlyDemand(locationId?: number) {
  const url = locationId
    ? `${API_BASE}/analytics/hourly-demand?location_id=${locationId}`
    : `${API_BASE}/analytics/hourly-demand`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchTopZones() {
  const res = await fetch(`${API_BASE}/analytics/zones`);
  return res.json();
}

export async function fetchTrips(limit: number = 50, offset: number = 0) {
  const res = await fetch(`${API_BASE}/analytics/trips?limit=${limit}&offset=${offset}`);
  return res.json();
}

export async function fetchModelComparison() {
  const res = await fetch(`${API_BASE}/ml/models`);
  return res.json();
}

export async function fetchForecast(horizonHours: number = 24, locationId?: number) {
  const res = await fetch(`${API_BASE}/ml/forecast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ horizon_hours: horizonHours, location_id: locationId }),
  });
  return res.json();
}

export async function triggerTraining() {
  const res = await fetch(`${API_BASE}/ml/train`, { method: "POST" });
  return res.json();
}

export async function fetchAnomalies() {
  const res = await fetch(`${API_BASE}/ml/anomalies`);
  return res.json();
}

export async function fetchPipelineHealth() {
  const res = await fetch(`${API_BASE}/health/`);
  return res.json();
}

export async function controlReplay(action: "start" | "pause" | "resume" | "stop", speed: number = 10.0) {
  const res = await fetch(`${API_BASE}/stream/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, speed_multiplier: speed }),
  });
  return res.json();
}

export function connectStreamWebSocket(onMessage: (data: any) => void) {
  const ws = new WebSocket(WS_BASE);
  ws.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      onMessage(parsed);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };
  return ws;
}

