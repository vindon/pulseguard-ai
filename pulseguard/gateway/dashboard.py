from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseGuard AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300;0,14..32,400;0,14..32,500;0,14..32,600;0,14..32,700;1,14..32,400&display=swap" rel="stylesheet">
<style>

/* ═══════════════════════════════════════════════════
   TOKENS
═══════════════════════════════════════════════════ */
:root {
  --white:   #ffffff;
  --gray-25: #FCFCFD;
  --gray-50: #F9FAFB;
  --gray-100:#F2F4F7;
  --gray-200:#E4E7EC;
  --gray-300:#D0D5DD;
  --gray-400:#98A2B3;
  --gray-500:#667085;
  --gray-600:#475467;
  --gray-700:#344054;
  --gray-800:#1D2939;
  --gray-900:#101828;

  --red-50:  #FEF3F2; --red-500: #F04438; --red-700: #B42318;
  --amber-50:#FFFAEB; --amber-500:#F79009; --amber-700:#B54708;
  --green-50:#ECFDF3; --green-500:#12B76A; --green-700:#027A48;
  --blue-50: #EFF8FF; --blue-500: #2E90FA; --blue-700: #175CD3;
  --purple-50:#F9F5FF;--purple-500:#9E77ED;--purple-700:#6941C6;

  /* Carriers */
  --verizon: #CD040B;
  --tmobile: #E20074;
  --att:     #009FDB;

  --font: 'Inter', -apple-system, sans-serif;
  --radius: 8px;
  --radius-lg: 12px;
  --shadow-xs: 0 1px 2px rgba(16,24,40,.05);
  --shadow-sm: 0 1px 3px rgba(16,24,40,.10), 0 1px 2px rgba(16,24,40,.06);
  --shadow-md: 0 4px 8px -2px rgba(16,24,40,.10), 0 2px 4px -2px rgba(16,24,40,.06);
  --shadow-lg: 0 12px 16px -4px rgba(16,24,40,.08), 0 4px 6px -2px rgba(16,24,40,.03);
  --transition: 150ms cubic-bezier(0.4,0,0.2,1);
}

/* ═══════════════════════════════════════════════════
   RESET
═══════════════════════════════════════════════════ */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{font-family:var(--font);background:var(--gray-50);color:var(--gray-900);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
button{font-family:var(--font);cursor:pointer;border:none;background:none}
a{color:inherit;text-decoration:none}
input{font-family:var(--font)}

/* ═══════════════════════════════════════════════════
   APP SHELL  — sidebar + main
═══════════════════════════════════════════════════ */
.shell{display:flex;height:100vh}

/* ─── Sidebar ──────────────────────────────────── */
.sidebar{
  width:240px;flex-shrink:0;
  background:var(--white);
  border-right:1px solid var(--gray-200);
  display:flex;flex-direction:column;
  overflow:hidden;
}

.sidebar-logo{
  padding:20px 20px 0;
  display:flex;align-items:center;gap:10px;
  margin-bottom:24px;
}
.logo-mark{
  width:32px;height:32px;border-radius:8px;
  background:linear-gradient(135deg,#6366F1,#8B5CF6);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-size:14px;font-weight:700;flex-shrink:0;
  box-shadow:0 1px 3px rgba(99,102,241,.4);
}
.logo-text{font-size:14px;font-weight:700;color:var(--gray-900)}
.logo-text span{color:#6366F1}

.sidebar-label{
  padding:0 20px 8px;
  font-size:11px;font-weight:600;letter-spacing:.6px;
  text-transform:uppercase;color:var(--gray-400);
}

/* Carrier nav items */
.carrier-item{
  margin:1px 10px;
  border-radius:var(--radius);
  padding:10px 12px;
  display:flex;align-items:center;gap:10px;
  cursor:pointer;
  transition:background var(--transition);
  position:relative;
}
.carrier-item:hover{background:var(--gray-50)}
.carrier-item.active{background:var(--c-light)}
.carrier-item.active::before{
  content:'';position:absolute;left:0;top:4px;bottom:4px;
  width:3px;border-radius:0 3px 3px 0;
  background:var(--c-brand);
}
.carrier-dot{
  width:28px;height:28px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:700;color:#fff;flex-shrink:0;
  background:var(--c-brand);
}
.carrier-info{flex:1;min-width:0}
.carrier-name{font-size:13px;font-weight:600;color:var(--gray-700)}
.carrier-item.active .carrier-name{color:var(--c-brand)}
.carrier-stat{font-size:11px;color:var(--gray-400);margin-top:1px}
.carrier-badge{
  min-width:20px;height:20px;padding:0 6px;border-radius:10px;
  background:var(--red-50);color:var(--red-700);
  font-size:11px;font-weight:700;
  display:flex;align-items:center;justify-content:center;
}
.carrier-badge.zero{background:var(--gray-100);color:var(--gray-400)}

[data-carrier="verizon"]{--c-brand:var(--verizon);--c-light:#FFF1F0}
[data-carrier="tmobile"]{--c-brand:var(--tmobile);--c-light:#FFF0F7}
[data-carrier="att"    ]{--c-brand:var(--att);    --c-light:#F0FAFF}

.sidebar-divider{height:1px;background:var(--gray-100);margin:16px 0}

/* Health summary in sidebar */
.health-card{
  margin:0 12px;padding:12px 14px;
  background:var(--gray-50);border-radius:var(--radius);
  border:1px solid var(--gray-200);
}
.health-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.health-row:last-child{margin-bottom:0}
.health-key{font-size:11px;color:var(--gray-500)}
.health-val{font-size:12px;font-weight:600;color:var(--gray-700)}
.health-val.red{color:var(--red-500)}
.health-val.green{color:var(--green-500)}
.health-val.amber{color:var(--amber-500)}

.sidebar-live{
  margin-top:auto;padding:16px 20px;
  display:flex;align-items:center;gap:8px;
  border-top:1px solid var(--gray-100);
  font-size:12px;color:var(--gray-500);
}
.live-dot{
  width:7px;height:7px;border-radius:50%;
  background:var(--green-500);flex-shrink:0;
  animation:livepulse 2s infinite;
}
@keyframes livepulse{0%,100%{opacity:1}50%{opacity:.35}}

/* ─── Main area ────────────────────────────────── */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}

/* Top bar */
.topbar{
  height:56px;flex-shrink:0;
  background:var(--white);
  border-bottom:1px solid var(--gray-200);
  padding:0 24px;
  display:flex;align-items:center;gap:12px;
  box-shadow:var(--shadow-xs);
}
.topbar-carrier{font-size:18px;font-weight:700;color:var(--c-brand)}
.topbar-slash{color:var(--gray-300);font-weight:300;font-size:18px}
.topbar-view{font-size:15px;font-weight:500;color:var(--gray-600)}

.feed-filters{display:flex;gap:4px;margin-left:auto}
.feed-chip{
  padding:5px 12px;border-radius:20px;
  font-size:12px;font-weight:500;color:var(--gray-500);
  border:1px solid transparent;
  cursor:pointer;transition:all var(--transition);
}
.feed-chip:hover{color:var(--gray-700);border-color:var(--gray-200);background:var(--gray-50)}
.feed-chip.active{
  background:var(--c-light);color:var(--c-brand);
  border-color:color-mix(in srgb, var(--c-brand) 30%, transparent);
  font-weight:600;
}
.feed-chip .cnt{
  display:inline-flex;align-items:center;justify-content:center;
  width:16px;height:16px;border-radius:50%;
  background:color-mix(in srgb, var(--c-brand) 15%, transparent);
  font-size:10px;font-weight:700;margin-left:4px;
}

/* ─── Content area (list + detail) ────────────── */
.content-area{flex:1;display:flex;overflow:hidden}

/* Queue list */
.queue-list{
  flex:1;overflow-y:auto;padding:16px 20px;
  min-width:0;
}
.queue-list::-webkit-scrollbar{width:4px}
.queue-list::-webkit-scrollbar-thumb{background:var(--gray-200);border-radius:2px}

/* Section headers */
.section-head{
  display:flex;align-items:center;gap:10px;
  margin-bottom:12px;margin-top:4px;
}
.section-head h2{font-size:13px;font-weight:600;color:var(--gray-700)}
.section-count{
  padding:2px 8px;border-radius:10px;
  font-size:11px;font-weight:600;
  background:var(--gray-100);color:var(--gray-500);
}
.section-count.urgent{background:var(--red-50);color:var(--red-700)}

/* ═══════════════════════════════════════════════
   SIGNAL CARDS
═══════════════════════════════════════════════ */
.signal-card{
  background:var(--white);border-radius:var(--radius-lg);
  border:1px solid var(--gray-200);
  box-shadow:var(--shadow-xs);
  margin-bottom:8px;
  cursor:pointer;
  transition:box-shadow var(--transition),border-color var(--transition),transform var(--transition);
  overflow:hidden;
  position:relative;
}
.signal-card:hover{
  box-shadow:var(--shadow-sm);
  border-color:var(--gray-300);
  transform:translateY(-1px);
}
.signal-card.active{
  border-color:var(--c-brand);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--c-brand) 15%,transparent),var(--shadow-sm);
}

/* Priority stripe */
.card-stripe{height:3px;background:var(--gray-200)}
.signal-card.p1 .card-stripe{background:var(--red-500)}
.signal-card.p2 .card-stripe{background:var(--amber-500)}
.signal-card.resolved .card-stripe{background:var(--green-500)}

.card-inner{padding:14px 16px}

.card-row1{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
.card-category{font-size:14px;font-weight:600;color:var(--gray-900);line-height:1.3}
.card-badges{display:flex;gap:4px;flex-wrap:wrap;align-items:center;flex-shrink:0}

.card-quote{
  font-size:13px;color:var(--gray-500);line-height:1.55;
  font-style:italic;
  margin-bottom:10px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}
.card-quote::before{content:'\201C';color:var(--gray-300);font-style:normal;font-size:16px;line-height:0;vertical-align:-.2em;margin-right:2px}
.card-quote::after{content:'\201D';color:var(--gray-300);font-style:normal;font-size:16px;line-height:0;vertical-align:-.2em;margin-left:2px}

.card-footer{
  display:flex;align-items:center;gap:8px;
  border-top:1px solid var(--gray-100);
  padding-top:10px;margin-top:2px;
}
.card-meta-pills{display:flex;gap:6px;flex:1;flex-wrap:wrap;align-items:center}
.card-action-area{flex-shrink:0}

/* ═══════════════════════════════════════════════
   BADGES / CHIPS
═══════════════════════════════════════════════ */
.badge{
  display:inline-flex;align-items:center;gap:3px;
  padding:2px 8px;border-radius:20px;
  font-size:11px;font-weight:600;white-space:nowrap;
  line-height:1.4;
}
.badge-p1     {background:var(--red-50);  color:var(--red-700); }
.badge-p2     {background:var(--amber-50);color:var(--amber-700)}
.badge-p3     {background:var(--amber-50);color:var(--amber-700);opacity:.7}
.badge-res    {background:var(--green-50);color:var(--green-700)}
.badge-churn  {background:var(--purple-50);color:var(--purple-700)}
.badge-src    {background:var(--gray-100);color:var(--gray-600)}
.badge-tier0  {background:var(--green-50);color:var(--green-700)}
.badge-tier1  {background:var(--blue-50); color:var(--blue-700) }
.badge-tier2  {background:var(--amber-50);color:var(--amber-700)}
.badge-valid  {background:var(--green-50);color:var(--green-700)}
.badge-invalid{background:var(--gray-100);color:var(--gray-400)}
.badge-sent-neg{background:var(--red-50);  color:var(--red-700)}
.badge-sent-neu{background:var(--gray-100);color:var(--gray-500)}
.badge-sent-pos{background:var(--green-50);color:var(--green-700)}
.badge-acked  {background:var(--green-50);color:var(--green-700)}
.badge-routing-res{background:var(--blue-50);color:var(--blue-700)}
.badge-routing-esc{background:var(--red-50);color:var(--red-700)}

/* ═══════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════ */
.btn{
  display:inline-flex;align-items:center;gap:6px;
  padding:7px 14px;border-radius:var(--radius);
  font-size:13px;font-weight:600;
  transition:all var(--transition);
  cursor:pointer;
}
.btn-primary{
  background:var(--gray-900);color:var(--white);
  box-shadow:var(--shadow-xs);
}
.btn-primary:hover{background:var(--gray-700)}
.btn-primary:disabled{background:var(--gray-200);color:var(--gray-400);cursor:default;box-shadow:none}
.btn-sm{padding:5px 11px;font-size:12px}
.btn-ghost{color:var(--gray-500);background:transparent}
.btn-ghost:hover{background:var(--gray-100);color:var(--gray-700)}

/* ═══════════════════════════════════════════════
   DETAIL PANEL
═══════════════════════════════════════════════ */
.detail-panel{
  width:420px;flex-shrink:0;
  background:var(--white);
  border-left:1px solid var(--gray-200);
  display:flex;flex-direction:column;
  overflow:hidden;
  box-shadow:var(--shadow-lg);
  transition:width var(--transition);
}
.detail-panel.empty{width:0;border:none}

.detail-panel-head{
  padding:16px 20px;
  border-bottom:1px solid var(--gray-200);
  flex-shrink:0;
}
.detail-panel-head .category{font-size:16px;font-weight:700;color:var(--gray-900);margin-bottom:6px}
.detail-panel-head .meta-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

.detail-panel-scroll{flex:1;overflow-y:auto;padding:0}
.detail-panel-scroll::-webkit-scrollbar{width:4px}
.detail-panel-scroll::-webkit-scrollbar-thumb{background:var(--gray-200);border-radius:2px}

/* Original post block */
.orig-post{
  padding:16px 20px;
  border-bottom:1px solid var(--gray-100);
}
.orig-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--gray-400);margin-bottom:8px}
.orig-text{
  font-size:13px;color:var(--gray-700);line-height:1.6;
  font-style:italic;
  padding:12px 14px;
  background:var(--gray-50);
  border-radius:var(--radius);
  border-left:3px solid var(--c-brand);
}
.orig-link{font-size:11px;color:var(--gray-400);margin-top:6px;display:flex;align-items:center;gap:4px}
.orig-link:hover{color:var(--gray-600)}

/* Agent steps */
.agent-step{border-bottom:1px solid var(--gray-100)}
.step-trigger{
  width:100%;padding:14px 20px;
  display:flex;align-items:center;gap:12px;
  background:none;cursor:pointer;
  transition:background var(--transition);
  text-align:left;
}
.step-trigger:hover{background:var(--gray-50)}
.step-icon{
  width:28px;height:28px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:800;color:#fff;flex-shrink:0;
}
.s-sentinel .step-icon{background:linear-gradient(135deg,#6366F1,#8B5CF6)}
.s-triage   .step-icon{background:linear-gradient(135deg,#F59E0B,#EF4444)}
.s-resolver .step-icon{background:linear-gradient(135deg,#10B981,#059669)}
.s-escalation .step-icon{background:linear-gradient(135deg,#F43F5E,#DC2626)}

.step-label-wrap{flex:1;min-width:0}
.step-label{font-size:12px;font-weight:700;color:var(--gray-700);text-transform:uppercase;letter-spacing:.5px}
.step-sublabel{font-size:11px;color:var(--gray-400);margin-top:1px}
.step-status{flex-shrink:0}
.step-chevron{color:var(--gray-300);font-size:11px;margin-left:4px;transition:transform var(--transition)}
.agent-step.open .step-chevron{transform:rotate(180deg)}

.step-body{display:none;padding:0 20px 16px}
.agent-step.open .step-body{display:block}

.fact-grid{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.fact-row{display:flex;gap:8px;align-items:baseline}
.fact-key{font-size:11px;color:var(--gray-400);min-width:120px;flex-shrink:0;font-weight:500}
.fact-val{font-size:12px;color:var(--gray-700);line-height:1.4}

.reasoning-block{
  background:var(--gray-50);border-radius:var(--radius);
  padding:12px 14px;
  border:1px solid var(--gray-200);
  margin-bottom:10px;
}
.reasoning-block .rb-label{
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  color:var(--gray-400);margin-bottom:6px;
}
.reasoning-block p{font-size:12px;color:var(--gray-600);line-height:1.6}

.draft-block{
  background:var(--blue-50);border-radius:var(--radius);
  padding:12px 14px;
  border:1px solid color-mix(in srgb,var(--blue-500) 25%,transparent);
  margin-bottom:10px;
}
.draft-block .rb-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--blue-700);margin-bottom:6px}
.draft-block p{font-size:12px;color:var(--blue-700);line-height:1.6}

.action-block{
  background:var(--green-50);border-radius:var(--radius);
  padding:12px 14px;
  border:1px solid color-mix(in srgb,var(--green-500) 30%,transparent);
}
.action-block .rb-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--green-700);margin-bottom:6px}
.action-block p{font-size:12px;color:var(--green-700);line-height:1.6}

/* Ack area in panel */
.ack-area{
  padding:16px 20px;
  border-top:1px solid var(--gray-200);
  flex-shrink:0;
  background:var(--white);
}
.ack-area .ack-msg{font-size:12px;color:var(--gray-500);margin-bottom:10px}
.ack-done{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--green-700);font-weight:600}

/* ═══════════════════════════════════════════════
   EMPTY / LOADING STATES
═══════════════════════════════════════════════ */
.empty-section{
  text-align:center;padding:48px 24px;
  color:var(--gray-400);
}
.empty-section .icon{font-size:32px;opacity:.4;margin-bottom:12px}
.empty-section h3{font-size:14px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.empty-section p{font-size:12px}

.section-space{margin-bottom:24px}

</style>
</head>
<body>
<div class="shell">

  <!-- ════════════ SIDEBAR ════════════ -->
  <aside class="sidebar">
    <div style="padding:20px 20px 0">
      <div class="sidebar-logo">
        <div class="logo-mark">P</div>
        <div class="logo-text"><span>Pulse</span>Guard AI</div>
      </div>
    </div>

    <div class="sidebar-label">Networks</div>

    <div id="carrier-nav">
      <div class="carrier-item" data-carrier="verizon" onclick="setCarrier('verizon')">
        <div class="carrier-dot" style="background:var(--verizon)">VZ</div>
        <div class="carrier-info">
          <div class="carrier-name">Verizon</div>
          <div class="carrier-stat" id="stat-verizon">—</div>
        </div>
        <div class="carrier-badge zero" id="badge-verizon">0</div>
      </div>
      <div class="carrier-item" data-carrier="tmobile" onclick="setCarrier('tmobile')">
        <div class="carrier-dot" style="background:var(--tmobile)">TM</div>
        <div class="carrier-info">
          <div class="carrier-name">T-Mobile</div>
          <div class="carrier-stat" id="stat-tmobile">—</div>
        </div>
        <div class="carrier-badge zero" id="badge-tmobile">0</div>
      </div>
      <div class="carrier-item" data-carrier="att" onclick="setCarrier('att')">
        <div class="carrier-dot" style="background:var(--att)">AT</div>
        <div class="carrier-info">
          <div class="carrier-name">AT&amp;T</div>
          <div class="carrier-stat" id="stat-att">—</div>
        </div>
        <div class="carrier-badge zero" id="badge-att">0</div>
      </div>
    </div>

    <div class="sidebar-divider"></div>
    <div class="sidebar-label">Intelligence</div>

    <div class="health-card" id="health-card">
      <div class="health-row"><span class="health-key">Signals (24h)</span><span class="health-val" id="hv-total">—</span></div>
      <div class="health-row"><span class="health-key">P1 open</span><span class="health-val red" id="hv-p1">—</span></div>
      <div class="health-row"><span class="health-key">Churn risk</span><span class="health-val amber" id="hv-churn">—</span></div>
      <div class="health-row"><span class="health-key">Auto-resolve rate</span><span class="health-val green" id="hv-res">—</span></div>
    </div>

    <div class="sidebar-live">
      <div class="live-dot"></div>
      <span id="last-tick">Syncing…</span>
    </div>
  </aside>

  <!-- ════════════ MAIN ════════════ -->
  <div class="main" style="--c-brand:#000;--c-light:#f0f0f0">
    <!-- Top bar -->
    <div class="topbar">
      <span class="topbar-carrier" id="tb-carrier">Select a network</span>
      <span class="topbar-slash" id="tb-slash" style="display:none">/</span>
      <span class="topbar-view" id="tb-view"></span>
      <div class="feed-filters" id="feed-filters"></div>
    </div>

    <!-- Content -->
    <div class="content-area">
      <div class="queue-list" id="queue-list">
        <div class="empty-section" style="margin-top:60px">
          <div class="icon">←</div>
          <h3>Select a network</h3>
          <p>Choose Verizon, T-Mobile or AT&amp;T from the sidebar</p>
        </div>
      </div>
      <div class="detail-panel empty" id="detail-panel"></div>
    </div>
  </div>

</div>

<script>
const KEY = '{{API_KEY}}';

// ─── State ───────────────────────────────────────
let signals = [];
let activeCarrier = null;
let activeFeed = 'all';
let selectedId = null;

// ─── Config ──────────────────────────────────────
const CARRIER_CFG = {
  verizon: { label:'Verizon',  accent:'#CD040B', light:'#FFF1F0' },
  tmobile: { label:'T-Mobile', accent:'#E20074', light:'#FFF0F7' },
  att:     { label:'AT&T',     accent:'#009FDB', light:'#F0FAFF' },
};
const FEEDS = [
  { id:'all',         icon:'◉', label:'All' },
  { id:'x',           icon:'𝕏', label:'X/Twitter' },
  { id:'reddit',      icon:'●', label:'Reddit' },
];
const FEED_LABEL = Object.fromEntries(FEEDS.map(f=>[f.id,f.label]));

// ─── Fetch ───────────────────────────────────────
async function apiFetch(p){ const r=await fetch('/api/v1'+p,{headers:{'X-API-Key':KEY}}); return r.json(); }
async function apiPost(p,b){ const r=await fetch('/api/v1'+p,{method:'POST',headers:{'X-API-Key':KEY,'Content-Type':'application/json'},body:JSON.stringify(b)}); return r.json(); }

async function refresh(){
  try{
    const d = await apiFetch('/pipeline/signals?hours=24');
    signals = d.signals || [];
    updateSidebar();
    if(activeCarrier) renderMain();
    document.getElementById('last-tick').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch(e){ console.error(e) }
}

// ─── Helpers ─────────────────────────────────────
function forCarrier(c){ return signals.filter(s=>(s.sentinel?.carrier||'').toLowerCase()===c); }
function forView(c,f){ const b=forCarrier(c); return f==='all'?b:b.filter(s=>s.sentinel?.source===f); }

function stage(s){
  if(s.escalation && Object.keys(s.escalation||{}).length) return 'escalated';
  if(s.resolver?.resolved===true||s.resolver?.resolved==='True'||s.resolver?.resolved==='true') return 'resolved';
  if(s.resolver && Object.keys(s.resolver||{}).length) return 'escalated';
  return s.stage||'triaged';
}

function sevClass(s){
  const v=(s.escalation?.severity||'').toLowerCase();
  return v||'';
}

function badge(cls,txt){ return `<span class="badge badge-${cls}">${txt}</span>`; }

function feedCntMap(c){
  const b=forCarrier(c);
  const m={all:b.length};
  ['x','reddit'].forEach(f=>{ m[f]=b.filter(s=>s.sentinel?.source===f).length; });
  return m;
}

function timeAgo(iso){
  if(!iso) return '';
  const s=Math.floor((Date.now()-new Date(iso.replace(/Z$/,'+00:00')))/1000);
  if(s<60) return s+'s ago';
  if(s<3600) return Math.floor(s/60)+'m ago';
  return Math.floor(s/3600)+'h ago';
}

function sentChip(v){
  if(v==null) return '';
  const f=parseFloat(v);
  if(f<-0.3) return badge('sent-neg', f.toFixed(2)+' sentiment');
  if(f>0.3)  return badge('sent-pos', '+'+f.toFixed(2)+' sentiment');
  return badge('sent-neu', f.toFixed(2)+' sentiment');
}

function sevBadge(sev){
  const m={P1:badge('p1','P1 · 1hr SLA'),P2:badge('p2','P2 · 4hr SLA'),P3:badge('p3','P3 · 24hr SLA')};
  return m[sev]||badge('p3',sev);
}

// ─── Sidebar updates ──────────────────────────────
function updateSidebar(){
  ['verizon','tmobile','att'].forEach(c=>{
    const base=forCarrier(c);
    const escOpen=base.filter(s=>stage(s)==='escalated'&&!s.escalation?.acknowledged).length;
    const churn=base.filter(s=>s.triage?.churn_risk||s.escalation?.churn_risk).length;
    document.getElementById('stat-'+c).textContent=`${base.length} signals · ${churn} churn`;
    const bdg=document.getElementById('badge-'+c);
    bdg.textContent=escOpen;
    bdg.className='carrier-badge'+(escOpen===0?' zero':'');
  });

  const cur=activeCarrier?forCarrier(activeCarrier):signals;
  const p1=cur.filter(s=>s.escalation?.severity==='P1'&&!s.escalation?.acknowledged).length;
  const churn=cur.filter(s=>s.triage?.churn_risk||s.escalation?.churn_risk).length;
  const res=cur.filter(s=>stage(s)==='resolved').length;
  const total=cur.length||1;
  document.getElementById('hv-total').textContent=cur.length;
  document.getElementById('hv-p1').textContent=p1;
  document.getElementById('hv-churn').textContent=churn;
  document.getElementById('hv-res').textContent=Math.round(res/total*100)+'%';

  // Active carrier styling
  document.querySelectorAll('.carrier-item').forEach(el=>{
    const c=el.dataset.carrier;
    const cfg=CARRIER_CFG[c];
    el.style.setProperty('--c-brand',cfg.accent);
    el.style.setProperty('--c-light',cfg.light);
    el.classList.toggle('active',c===activeCarrier);
  });
}

// ─── Set carrier ─────────────────────────────────
function setCarrier(c){
  activeCarrier=c;
  activeFeed='all';
  selectedId=null;
  const cfg=CARRIER_CFG[c];
  document.querySelector('.main').style.setProperty('--c-brand',cfg.accent);
  document.querySelector('.main').style.setProperty('--c-light',cfg.light);
  updateSidebar();
  renderMain();
}

// ─── Render main ─────────────────────────────────
function renderMain(){
  if(!activeCarrier) return;
  const cfg=CARRIER_CFG[activeCarrier];

  // Topbar
  document.getElementById('tb-carrier').textContent=cfg.label;
  document.getElementById('tb-slash').style.display='';
  document.getElementById('tb-view').textContent='Triage';

  // Feed filters
  const cnts=feedCntMap(activeCarrier);
  document.getElementById('feed-filters').innerHTML=FEEDS.map(f=>`
    <div class="feed-chip${activeFeed===f.id?' active':''}" onclick="setFeed('${f.id}')">
      ${f.icon} ${f.label}
      ${cnts[f.id]>0?`<span class="cnt">${cnts[f.id]}</span>`:''}
    </div>`).join('');

  renderQueue();
}

function setFeed(f){
  activeFeed=f;
  selectedId=null;
  renderMain();
}

// ─── Render queue ─────────────────────────────────
function renderQueue(){
  const view=forView(activeCarrier,activeFeed);
  const escalated=view.filter(s=>stage(s)==='escalated')
    .sort((a,b)=>(['P1','P2','P3'].indexOf(a.escalation?.severity||'P3'))-(['P1','P2','P3'].indexOf(b.escalation?.severity||'P3')));
  const resolved=view.filter(s=>stage(s)==='resolved');
  const inPipeline=view.filter(s=>!['escalated','resolved'].includes(stage(s)));

  let html='';

  // ── Escalations ──
  if(escalated.length){
    html+=`<div class="section-head section-space">
      <h2>Needs Human Action</h2>
      <span class="section-count urgent">${escalated.filter(s=>!s.escalation?.acknowledged).length} open</span>
    </div>`;
    html+=escalated.map(s=>signalCard(s)).join('');
  }

  // ── Resolved ──
  if(resolved.length){
    html+=`<div class="section-head section-space" style="margin-top:${escalated.length?28:4}px">
      <h2>Auto-Resolved</h2>
      <span class="section-count">${resolved.length}</span>
    </div>`;
    html+=resolved.map(s=>signalCard(s)).join('');
  }

  if(!escalated.length&&!resolved.length){
    html=`<div class="empty-section" style="margin-top:60px">
      <div class="icon">✓</div>
      <h3>${activeFeed==='all'?'Queue is clear':'Nothing from this feed'}${activeCarrier?' for '+CARRIER_CFG[activeCarrier].label:''}</h3>
      <p>Signals will appear here as they're processed</p>
    </div>`;
  }

  document.getElementById('queue-list').innerHTML=html;

  // Re-apply selection state
  if(selectedId){
    document.querySelectorAll('.signal-card').forEach(el=>{
      el.classList.toggle('active',el.dataset.id===selectedId);
    });
  }
}

function signalCard(s){
  const sen=s.sentinel||{};
  const tri=s.triage||{};
  const res=s.resolver||{};
  const esc=s.escalation||{};
  const st=stage(s);
  const sev=sevClass(s);
  const isEsc=st==='escalated';
  const isRes=st==='resolved';
  const acked=esc.acknowledged;
  const content=sen.content_preview||'';
  const id=s.signal_id;

  return `
<div class="signal-card ${isEsc?sev:''} ${isRes?'resolved':''} ${selectedId===id?'active':''}"
     data-id="${id}" onclick="selectSignal('${id}')">
  <div class="card-stripe"></div>
  <div class="card-inner">
    <div class="card-row1">
      <div class="card-category">${tri.category||'Uncategorised'}</div>
      <div class="card-badges">
        ${isEsc&&esc.severity ? sevBadge(esc.severity) : ''}
        ${isRes ? badge('res','✓ Auto-resolved') : ''}
        ${(tri.churn_risk||esc.churn_risk) ? badge('churn','⚠ Churn risk') : ''}
      </div>
    </div>
    <div class="card-quote">${content.substring(0,160)}${content.length>160?'…':''}</div>
    <div class="card-footer">
      <div class="card-meta-pills">
        ${badge('src', (FEED_LABEL[sen.source]||sen.source||'—'))}
        ${sentChip(tri.sentiment_score)}
        ${isEsc&&!acked ? `<span style="font-size:11px;color:var(--gray-400)">${timeAgo(esc.escalated_at)}</span>` : ''}
        ${isRes ? `<span style="font-size:11px;color:var(--gray-400)">conf ${parseFloat(res.confidence_score||0).toFixed(2)} · ${timeAgo(res.resolved_at)}</span>` : ''}
      </div>
      <div class="card-action-area">
        ${isEsc&&!acked
          ? `<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();doAck('${id}',this)">Mark actioned</button>`
          : isEsc&&acked
          ? `<span class="badge badge-acked">✓ Actioned</span>`
          : ''}
      </div>
    </div>
  </div>
</div>`;
}

// ─── Detail panel ─────────────────────────────────
function selectSignal(id){
  selectedId=id;
  const s=signals.find(x=>x.signal_id===id);

  // Update card selection state
  document.querySelectorAll('.signal-card').forEach(el=>{
    el.classList.toggle('active',el.dataset.id===id);
  });

  const panel=document.getElementById('detail-panel');
  panel.classList.remove('empty');

  if(!s){ panel.innerHTML=''; return; }

  const cfg=CARRIER_CFG[activeCarrier||'verizon'];
  panel.style.setProperty('--c-brand',cfg.accent);

  const sen=s.sentinel||{};
  const tri=s.triage||{};
  const res=s.resolver||{};
  const esc=s.escalation||{};
  const st=stage(s);
  const isEsc=st==='escalated';
  const acked=esc.acknowledged;

  panel.innerHTML=`
  <!-- Header -->
  <div class="detail-panel-head">
    <div class="category">${tri.category||'Uncategorised'}</div>
    <div class="meta-row">
      ${badge('src', FEED_LABEL[sen.source]||sen.source||'—')}
      ${isEsc&&esc.severity ? sevBadge(esc.severity) : ''}
      ${st==='resolved' ? badge('res','Auto-resolved') : ''}
      ${(tri.churn_risk||esc.churn_risk) ? badge('churn','⚠ Churn risk') : ''}
    </div>
  </div>

  <div class="detail-panel-scroll">
    <!-- Original post -->
    <div class="orig-post">
      <div class="orig-label">Customer's post · via ${FEED_LABEL[sen.source]||sen.source||'—'}</div>
      <div class="orig-text">${sen.content_preview||'—'}</div>
      ${sen.url?`<a class="orig-link" href="${sen.url}" target="_blank">↗ View original post</a>`:''}
    </div>

    <!-- SENTINEL -->
    <div class="agent-step s-sentinel open" id="ds-sentinel">
      <button class="step-trigger" onclick="toggleStep('ds-sentinel')">
        <span class="step-icon">S</span>
        <span class="step-label-wrap">
          <span class="step-label">Sentinel</span>
          <span class="step-sublabel">Signal validation · ${timeAgo(sen.validated_at)}</span>
        </span>
        <span class="step-status">${sen.is_valid ? badge('valid','✓ Valid') : badge('invalid','Dropped')}</span>
        <span class="step-chevron">▼</span>
      </button>
      <div class="step-body">
        <div class="fact-grid">
          <div class="fact-row"><span class="fact-key">Feed source</span><span class="fact-val">${FEED_LABEL[sen.source]||sen.source||'—'}</span></div>
          <div class="fact-row"><span class="fact-key">Carrier</span><span class="fact-val" style="font-weight:600;color:${cfg.accent}">${(sen.carrier||'unknown').toUpperCase()}</span></div>
          <div class="fact-row"><span class="fact-key">Result</span><span class="fact-val">${sen.is_valid ? badge('valid','Genuine support issue') : badge('invalid','Not a support issue')}</span></div>
        </div>
        <div class="reasoning-block">
          <div class="rb-label">Model Reasoning</div>
          <p>${sen.validity_reason||'No reasoning captured.'}</p>
        </div>
      </div>
    </div>

    <!-- TRIAGE -->
    ${Object.keys(tri).length ? `
    <div class="agent-step s-triage open" id="ds-triage">
      <button class="step-trigger" onclick="toggleStep('ds-triage')">
        <span class="step-icon">T</span>
        <span class="step-label-wrap">
          <span class="step-label">Triage</span>
          <span class="step-sublabel">Classification · ${timeAgo(tri.triaged_at)}</span>
        </span>
        <span class="step-status">${tri.routing_decision==='ESCALATION'?badge('routing-esc','→ Escalation'):badge('routing-res','→ Resolver')}</span>
        <span class="step-chevron">▼</span>
      </button>
      <div class="step-body">
        <div class="fact-grid">
          <div class="fact-row"><span class="fact-key">Issue type</span><span class="fact-val" style="font-weight:600">${tri.category||'—'}</span></div>
          <div class="fact-row"><span class="fact-key">Tier</span><span class="fact-val">${tri.resolution_tier!=null?badge(`tier${tri.resolution_tier}`,`Tier ${tri.resolution_tier} · ${['Deterministic','Attempt resolve','Human required'][tri.resolution_tier]||''}`):'—'}</span></div>
          <div class="fact-row"><span class="fact-key">Severity</span><span class="fact-val">${tri.severity_score||'—'} / 5</span></div>
          <div class="fact-row"><span class="fact-key">Sentiment</span><span class="fact-val">${sentChip(tri.sentiment_score)}</span></div>
          <div class="fact-row"><span class="fact-key">Churn signal</span><span class="fact-val">${tri.churn_risk?badge('churn','High risk'):'<span style="color:var(--gray-400)">Not detected</span>'}</span></div>
        </div>
        <div class="reasoning-block">
          <div class="rb-label">Routing Rationale</div>
          <p>${tri.routing_rationale||'No rationale captured.'}</p>
        </div>
      </div>
    </div>` : ''}

    <!-- RESOLVER -->
    ${Object.keys(res).length ? `
    <div class="agent-step s-resolver open" id="ds-resolver">
      <button class="step-trigger" onclick="toggleStep('ds-resolver')">
        <span class="step-icon">R</span>
        <span class="step-label-wrap">
          <span class="step-label">Resolver</span>
          <span class="step-sublabel">Autonomous resolution · ${timeAgo(res.resolved_at)}</span>
        </span>
        <span class="step-status">${(res.resolved===true||res.resolved==='True'||res.resolved==='true')?badge('res','Resolved'):badge('routing-esc','Escalated')}</span>
        <span class="step-chevron">▼</span>
      </button>
      <div class="step-body">
        <div class="fact-grid">
          <div class="fact-row"><span class="fact-key">Confidence</span><span class="fact-val" style="font-weight:600">${parseFloat(res.confidence_score||0).toFixed(3)} <span style="color:${parseFloat(res.confidence_score||0)>=.85?'var(--green-500)':'var(--amber-500)'}">/ 1.0 ${parseFloat(res.confidence_score||0)>=.85?'✓':'below threshold'}</span></span></div>
        </div>
        ${res.escalation_reason?`<div class="reasoning-block"><div class="rb-label">Why it escalated</div><p>${res.escalation_reason}</p></div>`:''}
        ${res.draft_response?`
        <div class="draft-block">
          <div class="rb-label">Draft response for ${FEED_LABEL[sen.source]||'feed'} — pending human review, not posted</div>
          <p>${res.draft_response}</p>
        </div>`:''}
      </div>
    </div>` : ''}

    <!-- ESCALATION -->
    ${Object.keys(esc).length ? `
    <div class="agent-step s-escalation open" id="ds-escalation">
      <button class="step-trigger" onclick="toggleStep('ds-escalation')">
        <span class="step-icon">E</span>
        <span class="step-label-wrap">
          <span class="step-label">Escalation</span>
          <span class="step-sublabel">Human handoff · ${timeAgo(esc.escalated_at)}</span>
        </span>
        <span class="step-status">${esc.acknowledged?badge('acked','✓ Actioned'):sevBadge(esc.severity)}</span>
        <span class="step-chevron">▼</span>
      </button>
      <div class="step-body">
        <div class="fact-grid">
          <div class="fact-row"><span class="fact-key">Priority</span><span class="fact-val">${sevBadge(esc.severity)}</span></div>
          <div class="fact-row"><span class="fact-key">Status</span><span class="fact-val">${esc.acknowledged?`<span style="color:var(--green-500);font-weight:600">Actioned by ${esc.acknowledged_by||'agent'}</span>`:'<span style="color:var(--red-500);font-weight:600">Waiting for human action</span>'}</span></div>
        </div>
        <div class="reasoning-block">
          <div class="rb-label">Why this was escalated</div>
          <p>${esc.summary||'—'}</p>
        </div>
        ${esc.recommended_action?`
        <div class="action-block">
          <div class="rb-label">What to do next</div>
          <p>${esc.recommended_action}</p>
        </div>`:''}
      </div>
    </div>` : ''}

  </div><!-- end scroll -->

  ${isEsc?`
  <div class="ack-area">
    ${acked
      ? `<div class="ack-done">✓ Marked as actioned by ${esc.acknowledged_by||'agent'}</div>`
      : `<div class="ack-msg">Once you've taken action on this case, mark it as actioned to clear it from the queue.</div>
         <button class="btn btn-primary" id="ack-btn" onclick="doAck('${s.signal_id}',this)">Mark as actioned</button>`}
  </div>` : ''}
  `;
}

function toggleStep(id){
  document.getElementById(id)?.classList.toggle('open');
}

async function doAck(id,btn){
  btn.disabled=true; btn.textContent='Actioning…';
  await apiPost(`/escalations/${id}/ack`,{ack_by:'cx_agent'});
  await refresh();
  if(selectedId===id) selectSignal(id);
}

// ─── Boot ─────────────────────────────────────────
refresh();
setInterval(refresh,10000);
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    from pulseguard.config import settings

    html = _HTML.replace("{{API_KEY}}", settings.pulseguard_api_key)
    return HTMLResponse(content=html)
