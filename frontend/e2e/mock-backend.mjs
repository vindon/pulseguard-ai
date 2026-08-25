// A minimal stand-in for the real FastAPI gateway, used only for e2e tests.
// The real backend needs Redis plus live Anthropic calls to actually move a
// signal through the pipeline — slow, costly, and flaky to depend on in CI.
// This serves fixed, realistic fixture data over the same routes so the
// frontend (proxying, rendering, interactions) gets exercised for real,
// without depending on infrastructure this repo doesn't provision in CI.
import { createServer } from 'node:http';

const PORT = process.env.MOCK_BACKEND_PORT || 8001;

const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();

const escalatedSignal = {
  signal_id: 'e2e-escalated-0001',
  stage: 'escalated',
  severity: 'P1',
  acknowledged: false,
  sentinel: {
    source: 'x',
    carrier: 'verizon',
    is_valid: true,
    validity_reason: 'Repeated billing overcharge with churn threat.',
    content_preview: 'Verizon overcharged me AGAIN this month, third time in a row.',
    url: 'https://example.com/x/e2e-escalated-0001',
    posted_at: minutesAgo(6),
    validated_at: minutesAgo(6),
  },
  triage: {
    category: 'Billing dispute',
    resolution_tier: 2,
    severity_score: 5,
    sentiment_score: -0.9,
    churn_risk: true,
    routing_decision: 'ESCALATION',
    routing_rationale: 'Repeat billing overcharge with explicit churn threat.',
    triaged_at: minutesAgo(5),
  },
  escalation: {
    severity: 'P1',
    summary: 'High-severity repeat billing dispute from a Verizon customer.',
    recommended_action: 'Review billing history and issue a full credit.',
    churn_risk: true,
    sentiment_score: -0.9,
    acknowledged: false,
    acknowledged_by: null,
    escalated_at: minutesAgo(4),
  },
};

const resolvedSignal = {
  signal_id: 'e2e-resolved-0002',
  stage: 'resolved',
  sentinel: {
    source: 'app_store',
    carrier: 'tmobile',
    is_valid: true,
    validity_reason: 'eSIM activation issue.',
    content_preview: "eSIM won't activate on the new plan, tried scanning the QR code 3 times.",
    url: 'https://example.com/app_store/e2e-resolved-0002',
    posted_at: minutesAgo(20),
    validated_at: minutesAgo(20),
  },
  triage: {
    category: 'eSIM activation',
    resolution_tier: 0,
    severity_score: 2,
    sentiment_score: -0.3,
    churn_risk: false,
    routing_decision: 'RESOLVER',
    routing_rationale: 'Known self-serve fix available.',
    triaged_at: minutesAgo(19),
  },
  resolver: {
    resolved: true,
    confidence_score: 0.92,
    draft_response: 'To activate your eSIM: Settings > Cellular > Add eSIM, then rescan the QR code.',
    escalation_reason: null,
    resolved_at: minutesAgo(18),
  },
};

const pipelineSignals = { signals: [escalatedSignal, resolvedSignal], count: 2 };

const escalationBrief = {
  signal_id: escalatedSignal.signal_id,
  summary: escalatedSignal.escalation.summary,
  source_platform: 'x',
  carrier: 'verizon',
  category: 'Billing dispute',
  severity: 'P1',
  sentiment_score: -0.9,
  churn_risk: true,
  original_post_url: escalatedSignal.sentinel.url,
  attempted_resolution: null,
  recommended_action: escalatedSignal.escalation.recommended_action,
  escalation_trace_id: 'trace-e2e-0001',
  escalated_at: escalatedSignal.escalation.escalated_at,
  acknowledged: false,
  acknowledged_by: null,
  acknowledged_at: null,
};

const ADAPTER_NAMES = ['x', 'reddit', 'google_play', 'app_store', 'trustpilot', 'quora'];

const adapterStatus = {
  adapters: Object.fromEntries(
    ADAPTER_NAMES.map((name) => [
      name,
      {
        adapter_name: name,
        status: 'HEALTHY',
        last_successful_fetch: minutesAgo(2),
        consecutive_errors: 0,
        monthly_cap_used: name === 'x' ? 1200 : null,
        monthly_cap_limit: name === 'x' ? 15000 : null,
        error_message: null,
      },
    ])
  ),
  count: ADAPTER_NAMES.length,
};

const orchestratorStatus = {
  running: true,
  queue_depth_unacknowledged: 1,
  global_circuit_open: false,
  adapter_circuit_breakers: Object.fromEntries(
    ADAPTER_NAMES.map((name) => [
      name,
      { name, state: 'closed', consecutive_errors: 0, opened_at: null },
    ])
  ),
  x_monthly_reads: 1200,
  x_monthly_cap: 15000,
};

// Mutable so the ack test can observe a real state change.
let escalationAcknowledged = false;

function send(res, status, body) {
  const json = JSON.stringify(body);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(json) });
  res.end(json);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const { pathname, searchParams } = url;

  if (pathname === '/health') return send(res, 200, { status: 'ok' });

  // Test-only: puts mutable fixture state back to its initial value. Tests
  // that mutate shared state (e.g. acknowledging the one fixture escalation)
  // call this first so run order/parallelism can't make another test flaky.
  if (pathname === '/e2e/reset' && req.method === 'POST') {
    escalationAcknowledged = false;
    return send(res, 200, { reset: true });
  }

  if (pathname === '/api/v1/pipeline/signals') {
    const source = searchParams.get('source');
    const signals = source
      ? pipelineSignals.signals.filter((s) => s.sentinel?.source === source)
      : pipelineSignals.signals;
    return send(res, 200, { signals, count: signals.length });
  }

  if (pathname.match(/^\/api\/v1\/signals\/[^/]+\/lifecycle$/)) {
    const id = pathname.split('/')[4];
    const found = pipelineSignals.signals.find((s) => s.signal_id === id);
    if (!found) return send(res, 404, { detail: 'not found' });
    return send(res, 200, {
      ...found,
      escalation: found.escalation ? { ...found.escalation, acknowledged: escalationAcknowledged } : undefined,
    });
  }

  if (pathname === '/api/v1/escalations') {
    const acknowledgedFilter = searchParams.get('acknowledged');
    const priorityFilter = searchParams.get('priority');
    let briefs = [{ ...escalationBrief, acknowledged: escalationAcknowledged }];
    if (acknowledgedFilter !== null) {
      briefs = briefs.filter((b) => String(b.acknowledged) === acknowledgedFilter);
    }
    if (priorityFilter) {
      briefs = briefs.filter((b) => b.severity === priorityFilter);
    }
    return send(res, 200, { briefs, count: briefs.length });
  }

  if (pathname.match(/^\/api\/v1\/escalations\/[^/]+\/ack$/) && req.method === 'POST') {
    escalationAcknowledged = true;
    return send(res, 200, {
      acknowledged: true,
      signal_id: escalationBrief.signal_id,
      acknowledged_by: 'e2e-test',
    });
  }

  if (pathname === '/api/v1/adapters/status') return send(res, 200, adapterStatus);
  if (pathname === '/api/v1/orchestrator/status') return send(res, 200, orchestratorStatus);

  if (pathname === '/api/v1/signals/ingest' && req.method === 'POST') {
    return send(res, 200, {
      signal_id: 'e2e-ingested-0003',
      trace_id: 'trace-e2e-0003',
      status: 'queued',
    });
  }

  send(res, 404, { detail: 'not found' });
});

server.listen(PORT, () => {
  console.log(`mock-backend listening on ${PORT}`);
});
