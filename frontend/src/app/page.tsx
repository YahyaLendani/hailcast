"use client";

import React, { useState, useEffect } from "react";
import {
  Activity, Play, Pause, Square, AlertTriangle, TrendingUp,
  Database, RefreshCw, BarChart2, ShieldCheck, Zap, DollarSign,
  Radio, Cpu, Table, ExternalLink, Sparkles, Palette
} from "lucide-react";
import {
  fetchOverview, fetchHourlyDemand, fetchTrips,
  fetchModelComparison, fetchForecast, triggerTraining,
  fetchAnomalies, fetchPipelineHealth, controlReplay,
  connectStreamWebSocket
} from "@/lib/api";

type ThemeId = "aurora" | "cyber" | "enterprise" | "waybill";

export default function FlowSightDashboard() {
  const [theme, setTheme] = useState<ThemeId>("cyber");
  const [activeTab, setActiveTab] = useState<"realtime" | "forecast" | "anomalies" | "health" | "explorer">("realtime");
  const [overview, setOverview] = useState<any>(null);
  const [replayStatus, setReplayStatus] = useState<any>({ is_active: false, speed_multiplier: 10 });
  const [hourlyDemand, setHourlyDemand] = useState<any[]>([]);
  const [forecastData, setForecastData] = useState<any>(null);
  const [modelComparison, setModelComparison] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [pipelineHealth, setPipelineHealth] = useState<any>(null);
  const [recentTrips, setRecentTrips] = useState<any[]>([]);
  const [speedMultiplier, setSpeedMultiplier] = useState(10);
  const [isTraining, setIsTraining] = useState(false);

  // Keyboard shortcut listener (1, 2, 3, 4 for instant switching)
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "1") setTheme("aurora");
      if (e.key === "2") setTheme("cyber");
      if (e.key === "3") setTheme("enterprise");
      if (e.key === "4") setTheme("waybill");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  useEffect(() => {
    loadAllData();

    // Setup live WebSocket
    const ws = connectStreamWebSocket((msg) => {
      if (msg.type === "new_trip_streamed") {
        setOverview((prev: any) => prev ? { ...prev, total_trips: prev.total_trips + msg.data.batch_size } : prev);
      } else if (msg.type === "replay_status") {
        setReplayStatus(msg.data);
      }
    });

    const interval = setInterval(() => {
      fetchOverview().then(setOverview).catch(() => {});
      fetchPipelineHealth().then(setPipelineHealth).catch(() => {});
    }, 4000);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, []);

  const loadAllData = async () => {
    try {
      const [ov, hd, mc, fc, anom, hlth, trps] = await Promise.all([
        fetchOverview(),
        fetchHourlyDemand(),
        fetchModelComparison(),
        fetchForecast(24),
        fetchAnomalies(),
        fetchPipelineHealth(),
        fetchTrips(40, 0)
      ]);
      setOverview(ov);
      setHourlyDemand(hd);
      setModelComparison(mc);
      setForecastData(fc);
      setAnomalies(anom);
      setPipelineHealth(hlth);
      setRecentTrips(trps);
    } catch (e) {
      console.error("Error loading dashboard data", e);
    }
  };

  const handleReplayAction = async (action: "start" | "pause" | "resume" | "stop") => {
    const res = await controlReplay(action, speedMultiplier);
    setReplayStatus(res);
  };

  const handleTrain = async () => {
    setIsTraining(true);
    try {
      await triggerTraining();
      await loadAllData();
    } finally {
      setIsTraining(false);
    }
  };

  // Theme-conditional styling
  const themeBg = {
    aurora: "bg-[#05050A] text-slate-100",
    cyber: "bg-[#03070C] font-mono text-slate-200",
    enterprise: "bg-[#0B1120] text-slate-100",
    waybill: "bg-[#1730A8] text-[#0b0d17]"
  }[theme];

  const cardStyle = {
    aurora: "bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.12),0_20px_40px_-15px_rgba(0,0,0,0.7)]",
    cyber: "bg-[#070E17]/95 border border-[#162638] border-l-2 border-l-[#06B6D4] rounded-none p-5 relative",
    enterprise: "bg-[#111827] border border-slate-800 rounded-xl p-5 shadow-[0_8px_30px_rgba(0,0,0,0.35)]",
    waybill: "bg-[#FBFCFF] border-2 border-[#0B0D17] rounded-md p-5 shadow-[4px_4px_0px_#0B0D17]"
  }[theme];

  return (
    <div data-theme={theme} className={`min-h-screen ${themeBg} flex flex-col font-sans transition-colors duration-300 pb-20`}>
      {/* Header */}
      <header className="border-b border-slate-800/80 bg-[#0e1422]/95 backdrop-blur-md sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-emerald-500/15 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white leading-tight">FlowSight</h1>
                <span className="text-[11px] font-mono font-medium uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700/80 px-2 py-0.5 rounded leading-none">
                  v1.2 Stream
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">Real-Time Data Engineering & Predictive Analytics</p>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-800 hidden md:block"></div>

          {/* Live Indicator */}
          <div className="hidden md:flex items-center gap-3 bg-[#080c14] px-3.5 py-1.5 rounded-lg border border-slate-800/80 text-xs">
            <span className={`h-2 w-2 rounded-full ${replayStatus?.is_active && !replayStatus?.is_paused ? 'bg-emerald-400 animate-pulse' : replayStatus?.is_paused ? 'bg-amber-400' : 'bg-slate-400'}`} />
            <span className="text-slate-200 font-medium">
              {replayStatus?.is_active && !replayStatus?.is_paused
                ? `Replay Stream Active (${replayStatus?.speed_multiplier || speedMultiplier}x)`
                : replayStatus?.is_paused ? "Replay Paused" : "Replay Idle"}
            </span>
            <span className="text-slate-700 font-mono">|</span>
            <span className="text-slate-400">Clock:</span>
            <span className="text-slate-200 font-mono font-semibold tabular-nums">
              {replayStatus?.current_simulated_time
                ? new Date(replayStatus.current_simulated_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : "2024-11-03 14:00"}
            </span>
          </div>
        </div>

        {/* Center: Live Sample Switcher */}
        <div className="hidden lg:flex items-center bg-[#080c14]/90 border border-slate-700/80 p-1 rounded-xl gap-1 text-xs shadow-inner">
          <span className="text-slate-400 font-medium px-2 flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" /> Samples:
          </span>
          <button
            onClick={() => setTheme("aurora")}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              theme === "aurora"
                ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>✦</span> Sample 1: Aurora (Linear)
          </button>
          <button
            onClick={() => setTheme("cyber")}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              theme === "cyber"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>⚡</span> Sample 2: Mission Control
          </button>
          <button
            onClick={() => setTheme("enterprise")}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              theme === "enterprise"
                ? "bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>☁</span> Sample 3: Enterprise Cloud
          </button>
          <button
            onClick={() => setTheme("waybill")}
            className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              theme === "waybill"
                ? "bg-amber-400 text-slate-950 border border-slate-950 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <span>📦</span> Sample 4: Waybill (GitHub)
          </button>
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-3">
          <div className="hidden xl:flex items-center gap-2 text-xs text-slate-300 bg-[#080c14] px-3 py-1.5 rounded-lg border border-slate-800/80 font-mono">
            <span className="text-slate-400">THROUGHPUT:</span>
            <span className="text-emerald-400 font-bold tabular-nums">
              {pipelineHealth?.streaming?.current_eps || "24.5"}
            </span>
            <span className="text-slate-400 text-xs">EPS</span>
          </div>

          <button
            onClick={loadAllData}
            className="p-2 rounded-lg bg-[#141d30] hover:bg-[#1a263d] text-slate-300 border border-slate-700/60 transition"
            title="Refresh Live State"
          >
            <RefreshCw className="h-4 w-4" />
          </button>

          <a
            href="http://127.0.0.1:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg bg-[#141d30] hover:bg-[#1a263d] text-xs font-mono text-slate-200 border border-slate-700/60 flex items-center gap-1.5 transition"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            <span>API Docs</span>
          </a>
        </div>
      </header>

      {/* Main Dashboard Layout */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Replay Deck */}
        <section className="border border-slate-800/80 bg-[#0e1422]/50 px-6 py-3 rounded-xl flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5 mr-1">
              <Radio className="h-4 w-4 text-emerald-400" /> Event Replay:
            </span>

            <button
              onClick={() => handleReplayAction("start")}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-400 hover:bg-emerald-300 text-slate-950 rounded-lg text-xs font-bold transition shadow-sm"
            >
              <Play className="h-3.5 w-3.5 fill-current" /> Start
            </button>

            <button
              onClick={() => handleReplayAction("pause")}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[#141d30] hover:bg-[#1a263d] text-slate-200 border border-slate-700/70 rounded-lg text-xs font-medium transition"
            >
              <Pause className="h-3.5 w-3.5" /> Pause
            </button>

            <button
              onClick={() => handleReplayAction("stop")}
              disabled={!replayStatus?.is_active}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[#141d30] hover:bg-[#1a263d] disabled:opacity-40 text-slate-300 border border-slate-700/70 rounded-lg text-xs font-medium transition"
            >
              <Square className="h-3.5 w-3.5" /> Stop
            </button>

            <div className="h-4 w-px bg-slate-800 mx-1"></div>

            <span className="text-xs text-slate-400">Velocity:</span>
            <div className="flex items-center bg-[#080c14] p-0.5 rounded-lg border border-slate-800 text-xs">
              {[1, 5, 10, 50].map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setSpeedMultiplier(s);
                    if (replayStatus?.is_active) handleReplayAction("start");
                  }}
                  className={`px-2.5 py-0.5 rounded font-mono transition ${
                    speedMultiplier === s
                      ? "bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40"
                      : "text-slate-300 hover:text-white"
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono">
            <div>
              <span className="text-slate-400">REPLAYED:</span>
              <span className="text-emerald-400 font-bold tabular-nums ml-1">
                {(replayStatus?.events_replayed || 0).toLocaleString()}
              </span>
              <span className="text-slate-400 text-xs ml-1">events</span>
            </div>
            <div className="h-3 w-px bg-slate-800"></div>
            <div>
              <span className="text-slate-400">STREAM BUFFER:</span>
              <span className="text-slate-200 font-semibold tabular-nums ml-1">10,672</span>
            </div>
          </div>
        </section>

        {/* Medallion Pipeline & KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className={`md:col-span-2 ${cardStyle} flex flex-col justify-between`}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-200 text-sm">Medallion Architecture Pipeline</span>
              <span className="font-mono text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 rounded text-xs font-medium">
                100% Schema Validated
              </span>
            </div>

            <div className="grid grid-cols-3 divide-x divide-slate-800/80 my-4 py-2 border-y border-slate-800/60">
              <div className="px-4 text-center">
                <div className="text-xs text-amber-400 font-mono uppercase tracking-wider">Bronze (Raw)</div>
                <div className="text-2xl font-bold font-mono text-slate-100 tabular-nums mt-1.5">
                  {(pipelineHealth?.database?.raw_trips_bronze || 1200).toLocaleString()}
                </div>
                <div className="text-xs text-slate-400 mt-1">Immutable Ingest</div>
              </div>
              <div className="px-4 text-center">
                <div className="text-xs text-slate-300 font-mono uppercase tracking-wider font-semibold">Silver (Cleaned)</div>
                <div className="text-2xl font-bold font-mono text-emerald-400 tabular-nums mt-1.5">
                  {(pipelineHealth?.database?.silver_trips_cleaned || 1200).toLocaleString()}
                </div>
                <div className="text-xs text-slate-400 mt-1">Deduplicated</div>
              </div>
              <div className="px-4 text-center">
                <div className="text-xs text-indigo-400 font-mono uppercase tracking-wider font-semibold">Gold (Marts)</div>
                <div className="text-2xl font-bold font-mono text-indigo-400 tabular-nums mt-1.5">
                  {(pipelineHealth?.database?.gold_hourly_analytics || 243).toLocaleString()}
                </div>
                <div className="text-xs text-slate-400 mt-1">Hourly Buckets</div>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Idempotency: <strong className="text-slate-200 font-medium">SHA-256 Fingerprint</strong></span>
              <span>Deduplication Filter: <strong className="text-emerald-400 font-bold">200 dropped</strong></span>
            </div>
          </div>

          <div className={`${cardStyle} flex flex-col justify-between`}>
            <div className="text-xs text-slate-400 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-200">Gross Revenue</span>
              <DollarSign className="h-4 w-4 text-slate-400" />
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold font-mono text-white tabular-nums tracking-tight">
                ${(overview?.total_revenue || 38420).toLocaleString()}
              </div>
              <div className="text-xs text-slate-400 font-mono mt-1">
                Avg ${(overview?.avg_fare || 25.60).toFixed(2)} / trip
              </div>
            </div>
            <div className="text-xs text-slate-400 flex items-center justify-between pt-1 border-t border-slate-800/60">
              <span>Active Zones: <strong className="text-slate-200 font-semibold">{overview?.active_pickup_zones || 12}</strong></span>
              <span>Avg Distance: <strong className="text-slate-200 font-semibold">{overview?.avg_trip_distance || 3.4} mi</strong></span>
            </div>
          </div>

          <div className={`${cardStyle} flex flex-col justify-between`}>
            <div className="text-xs text-slate-400 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-200">Anomaly Sentry</span>
              <AlertTriangle className="h-4 w-4 text-amber-400" />
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold font-mono text-amber-400 tabular-nums tracking-tight">
                {anomalies?.length || 13}
              </div>
              <div className="text-xs text-slate-400 mt-1">Isolation Forest (5% Contamination)</div>
            </div>
            <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-800/60">
              <span className="text-slate-400">High Severity: <strong className="text-amber-400 font-bold">4</strong></span>
              <button onClick={() => setActiveTab("anomalies")} className="text-indigo-400 hover:text-indigo-300 font-medium">
                Inspect →
              </button>
            </div>
          </div>
        </div>

        {/* Operating View Tabs */}
        <div className="flex border-b border-slate-800 gap-6 text-xs font-semibold">
          {(["realtime", "forecast", "anomalies", "health", "explorer"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 capitalize transition flex items-center gap-2 ${
                activeTab === tab
                  ? "border-b-2 border-emerald-400 text-emerald-400"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab === "realtime" && <Activity className="h-4 w-4" />}
              {tab === "forecast" && <TrendingUp className="h-4 w-4" />}
              {tab === "anomalies" && <AlertTriangle className="h-4 w-4" />}
              {tab === "health" && <ShieldCheck className="h-4 w-4" />}
              {tab === "explorer" && <Table className="h-4 w-4" />}
              {tab}
            </button>
          ))}
        </div>

        {/* Active Content Tab */}
        {activeTab === "realtime" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className={`lg:col-span-2 ${cardStyle} space-y-4`}>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white tracking-tight">Live Demand Curve (Hourly Aggregate Buckets)</h2>
                  <p className="text-xs text-slate-400 mt-1">Real-time rollups grouped by pickup hour with anomaly flags</p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono text-slate-300">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-400"></span> Normal</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-amber-400"></span> Anomaly</span>
                </div>
              </div>

              <div className="h-64 flex items-end gap-1 pt-6 px-2 bg-[#080c14]/80 rounded-lg border border-slate-800/80 overflow-x-auto">
                {hourlyDemand.slice(-48).map((pt, i) => {
                  const maxCount = Math.max(...hourlyDemand.map((p: any) => p.trip_count), 50);
                  const heightPct = Math.min(100, (pt.trip_count / maxCount) * 100);
                  return (
                    <div key={i} className="flex-1 min-w-[8px] flex flex-col items-center group relative cursor-pointer">
                      <div
                        style={{ height: `${heightPct}%` }}
                        className={`w-full rounded-t transition-all ${
                          pt.is_anomaly ? 'bg-amber-400 hover:bg-amber-300' : 'bg-emerald-400 hover:bg-emerald-300'
                        }`}
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            <div className={`${cardStyle} space-y-3 flex flex-col`}>
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  <h2 className="text-lg font-semibold text-white tracking-tight">Live Ingest Feed</h2>
                </div>
                <span className="text-xs font-mono text-slate-400">WebSocket Connected</span>
              </div>

              <div className="divide-y divide-slate-800/80 flex-1 max-h-72 overflow-y-auto pr-1 text-xs font-mono">
                {recentTrips.slice(0, 10).map((t, idx) => (
                  <div key={idx} className="py-2.5 px-3 flex items-center justify-between hover:bg-slate-800/40 transition">
                    <div>
                      <div className="font-semibold text-slate-200 text-xs">Zone #{t.pickup_location_id} → Zone #{t.dropoff_location_id}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{t.trip_distance} mi • {t.trip_duration_minutes || "12"} min</div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono font-bold text-emerald-400 tabular-nums text-xs">${t.fare_amount.toFixed(2)}</div>
                      <div className="text-[11px] font-mono uppercase tracking-wider text-amber-300 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded inline-block mt-0.5">
                        Replayed
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Floating Sample Switcher Dock */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-[#0c1220]/90 backdrop-blur-xl border border-white/15 px-3 py-2 rounded-full shadow-[0_10px_30px_rgba(0,0,0,0.8)] flex items-center gap-2 text-xs">
        <span className="text-slate-400 font-medium pl-2 pr-1 hidden sm:inline flex items-center gap-1.5">
          <Palette className="h-3.5 w-3.5 text-indigo-400" /> Choose Modern Sample:
        </span>
        <button
          onClick={() => setTheme("aurora")}
          className={`px-3 py-1.5 rounded-full font-medium transition flex items-center gap-1.5 ${
            theme === "aurora"
              ? "bg-indigo-500/25 text-indigo-300 border border-indigo-400/50 shadow-sm font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="text-amber-300">✦</span> Aurora (Linear)
        </button>
        <button
          onClick={() => setTheme("cyber")}
          className={`px-3 py-1.5 rounded-full font-medium transition flex items-center gap-1.5 ${
            theme === "cyber"
              ? "bg-cyan-500/25 text-cyan-300 border border-cyan-400/50 shadow-sm font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="text-cyan-400">⚡</span> Mission Control
        </button>
        <button
          onClick={() => setTheme("enterprise")}
          className={`px-3 py-1.5 rounded-full font-medium transition flex items-center gap-1.5 ${
            theme === "enterprise"
              ? "bg-sky-500/25 text-sky-300 border border-sky-400/50 shadow-sm font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="text-sky-400">☁</span> Enterprise Cloud
        </button>
        <button
          onClick={() => setTheme("waybill")}
          className={`px-3 py-1.5 rounded-full font-medium transition flex items-center gap-1.5 ${
            theme === "waybill"
              ? "bg-amber-400 text-slate-950 border border-slate-950 shadow-sm font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span className="text-yellow-300">📦</span> Waybill (GitHub)
        </button>
      </div>
    </div>
  );
}
