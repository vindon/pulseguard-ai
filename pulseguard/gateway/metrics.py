from prometheus_client import Counter, Gauge, Histogram

# ── Counters ────────────────────────────────────────────────────────────────
signals_ingested = Counter(
    "pulseguard_signals_ingested_total",
    "Total signals ingested",
    ["source", "carrier"],
)

signals_by_routing = Counter(
    "pulseguard_signals_by_routing_total",
    "Signals by resolution tier and carrier",
    ["tier", "carrier"],
)

resolutions_total = Counter(
    "pulseguard_resolutions_total",
    "Total resolution outcomes",
    ["outcome", "carrier"],
)

escalations_total = Counter(
    "pulseguard_escalations_total",
    "Total escalations by priority and carrier",
    ["priority", "carrier"],
)

adapter_errors_total = Counter(
    "pulseguard_adapter_errors_total",
    "Total adapter errors",
    ["adapter"],
)

# ── Gauges ──────────────────────────────────────────────────────────────────
x_api_reads_monthly = Gauge(
    "pulseguard_x_api_reads_monthly",
    "Current X API monthly read count",
)

escalation_queue_depth = Gauge(
    "pulseguard_escalation_queue_depth",
    "Current unacknowledged escalation queue depth",
)

# ── Histograms ──────────────────────────────────────────────────────────────
agent_latency = Histogram(
    "pulseguard_agent_latency_seconds",
    "Agent node processing latency",
    ["agent", "node"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
