# PulseGuard: Telecom Customer-Care Copilot — Design Spec

Date: 2026-09-07
Status: approved by Vinoth, ready for implementation planning
Scope: repositions and extends the existing PulseGuard codebase (`pulseguard-ai`). Reuses the Sentinel → Triage → Resolver → Escalation agent core; adds multi-tenancy, publish-back capability, and a governance/quality layer. Not a rewrite.

## 1. Problem

The existing PulseGuard build is a single-tenant, telecom-carrier-locked triage tool with two structural mismatches to reality, surfaced across an audit and three rounds of market research on 2026-09-07:

1. **Market mismatch:** it implicitly competes with Sprinklr/Khoros for enterprise telecom accounts it cannot reach (their contracts run $50K-750K+/yr, multi-year, already signed) and its Resolver was originally envisioned to execute against carrier backend systems (CRM/Billing/Order/Device APIs) that no solo builder can get access to.
2. **Positioning mismatch:** no incumbent in the social/review customer-care market (Sprinklr, Khoros, Emplifi, Sprout Social, Brandwatch, Hootsuite, Chattermill) integrates proactive detection + drafted response + human-gated escalation into one coherent product — they're each strong in one or two of those and weak in the rest. PulseGuard's existing architecture already *is* that integration; it just isn't positioned or sold as one.

This spec repositions PulseGuard as a **human-copilot product** — AI drafts, a human always reviews and sends, nothing auto-posts by default — sold into a specifically-sized, real telecom buyer segment (regional carriers, independent MVNOs, cable operators newly launching mobile), rather than competing head-on with enterprise incumbents or diffusing into a broad multi-vertical, multi-buyer-type GTM the founder cannot execute solo.

## 2. Decisions locked with Vinoth (2026-09-07)

| Decision | Choice |
|---|---|
| Vertical scope | **Telecom-focused GTM**, vertical-agnostic architecture underneath. Telecom is the beachhead and proof-vertical, not a permanent hard boundary — but no scope expansion into other verticals until telecom is validated. |
| Target buyer | Regional/rural facilities-based wireless carriers, independent MVNOs, and cable/broadband operators newly launching mobile (NCTC/Reach-style) — explicitly **not** Tier-1 national carriers (Verizon/T-Mobile/AT&T, already Sprinklr/Khoros accounts) and explicitly **not** framed around freelancers or solo social-media managers. |
| Positioning | Human-copilot: AI drafts, a human approves and sends, always. Not "autonomous resolution." This is a permanent product decision, not a trust-building placeholder to graduate away from later — see §9. |
| Resolver capability | Drafts a response **and**, once a human clicks Approve & Send, actually posts it back to the source platform via a new publish-adapter layer. (Different from the original PulseGuard, whose Resolver never posts publicly under any circumstance.) |
| Pricing | Real B2B pricing: **$1,500-6,000/month ($18K-72K/year)**, average deal ~$30-42K/year — not indie/self-serve pricing, not enterprise-minimum pricing. |
| GTM motion | MVNE-channel-led (NCTC/Reach Mobile-style partnerships) as the primary lever, 3-5 direct lighthouse regional carriers for case studies/credibility, telecom BPOs (eClerx/Startek/IBEX) as a secondary longer-horizon channel. Not self-serve PLG, not enterprise field sales. |
| Revenue target | Realistic 3-year target: **$1.5M-3M ARR** — a real six-to-seven-figure beachhead business, explicitly not modeled or sold internally as a venture-scale outcome. |
| Code/architecture quality bar | No compromise: real LangGraph checkpointing/interrupts, typed schemas throughout, decision traceability, evals with regression gates, mandatory CI quality gates (lint/types/tests/evals/security, all blocking), spend guard with hard budget caps and strict halt-on-failure (not silent retry). Detailed in §9-§12. |

## 3. What stays exactly as built (reused, not rebuilt)

- The four-agent LangGraph pattern: **Sentinel** (validate/dedupe/detect brand — Claude Haiku), **Triage** (classify/severity — Claude Sonnet), **Resolver** (draft — Claude Sonnet w/ extended thinking), **Escalation** (package context, notify, wait for human action — Claude Opus for brief composition).
- PII sanitization and SHA-256 handle hashing at every signal-creation point (`adapters/base.py::_make_signal`) — non-negotiable, and *more* important now that the product holds other businesses' customer data, not just one company's.
- Prompt-injection framing (`<customer_post>` untrusted-data tagging) in every agent system prompt.
- Timing-safe API auth, the corrected rate-limiter trust-boundary logic, the enterprise integration channels already built (Slack, Teams, Zendesk, Freshdesk, generic signed webhook).
- X and Reddit adapters (kept from the earlier adapter-count cut; extended per §5).
- CI discipline (ruff, mypy --strict, pytest, real Redis service container) — extended, not replaced, per §11.

## 4. What changes: multi-tenancy

**New concepts:**
- **Workspace** — one buyer account. For a direct-sold regional carrier, one workspace = one carrier. For a BPO or MVNE-channel deal, one workspace can hold multiple **Client Brands** (the BPO's several regional-carrier clients, or the MVNE's several member operators).
- **Client Brand** — one monitored telecom operator inside a workspace: its own keywords/handles, connected sources, KB (replacing today's hardcoded `CARRIER_CONFIGS` — `CarrierConfig` generalizes to `ClientBrandConfig`, same shape, not telecom-specific field names), escalation routing, and severity thresholds.
- **Seats** — team members with roles: **Owner** (billing/admin), **Manager** (configures brands, sees everything), **Responder** (sees only their assigned brand's queue, drafts/sends).
- **Queue** — the core UI object: a cross-brand unified inbox for an ops lead, or a brand-filtered queue for a responder. Direct evolution of today's `/queue` page.

**Data model implications:** every signal, triage report, resolution, and escalation record gets a `workspace_id` and `brand_id`. Today's single static `PULSEGUARD_API_KEY` gateway auth is replaced with real per-user accounts and roles (Clerk, Auth.js, or Supabase Auth — pick one during implementation planning, not this spec).

**New data store:** Postgres for tenant/brand/seat/billing records (durable, relational, needs real constraints and joins). Redis remains for the event bus, queueing, and circuit-breaker/rate-limit state — it was never the right place for durable multi-tenant records, and this fixes that rather than forcing tenancy into Redis hashes.

**Sequencing note:** this section describes the target architecture, not a Day 1 build mandate — §15 Phase 0 deliberately ships a single-tenant-per-deployment pilot first and defers full multi-tenant infrastructure to Phase 2, once real customers justify the investment.

## 5. What changes: Triage taxonomy

Today's `_TIER_MAP` in `triage.py` is a fixed telecom taxonomy (Network outage, eSIM activation, Billing dispute, ...). This becomes:
- A **default telecom taxonomy** (today's categories, unchanged) shipped as the pre-built template for every new Client Brand.
- Each Client Brand can add categories/KB entries specific to its own operations during onboarding (e.g., a cable-operator-turned-MVNO may need "bundle/promo confusion" as a category their pure-wireless telecom peers don't).
- Source adapters extend beyond X/Reddit for this vertical where a **legitimate, documented, self-serve API exists**: Google Business Profile API and Yelp Fusion API are candidates (both public, both used for reviews telecom customers post). **Trustpilot's scraping approach is explicitly not revived** — it was cut for real legal-exposure reasons (undocumented endpoint, rotating fake user-agents) and that reasoning applies harder now that the product would be handling other businesses' reputations, not just one company's own social presence.

## 6. What's genuinely new: publish adapters

The single biggest capability gap versus the original PulseGuard: today's Resolver "never posts publicly," full stop. This product's entire value proposition is that clicking **Approve & Send** actually sends the reply. This needs:
- An **X reply adapter** (post a reply to the original complaint's thread).
- A **Google Business Profile review-reply adapter** (respond to a Google review).
- A **Reddit comment adapter** (reply to a Reddit post/comment).
- Each requires the Client Brand to complete an OAuth consent flow during onboarding, connecting *their own* social/review accounts — PulseGuard never holds a shared, unscoped credential across tenants.
- **This is real, non-trivial new engineering** — not a copy-paste of anything in the current codebase — and should be sized as its own work-stream in the implementation plan, not folded silently into "extend Escalation."
- **Sequencing note:** Phase 0/1 (§15) only requires *one* publish adapter working end-to-end (X or Google Business Profile) to validate the loop with a real pilot customer — all three are the target state, not the Phase 1 bar.

## 7. UI/UX — key screens

- **Unified Inbox** (evolution of `/queue`): cross-brand feed of pending drafts, filterable by brand/urgency/assignee.
- **Brand switcher**: sidebar list of Client Brands.
- **Draft Review Card** (evolution of `SignalDrawer`): original complaint + source link, AI draft, confidence/severity badge, **Edit / Approve & Send / Reassign / Dismiss**.
- **Client Brand setup wizard**: add brand, connect sources (OAuth), configure KB/voice/policies, invite team, set routing rules.
- **Team management**: seats, roles, brand assignment.
- **Analytics**: volume handled and time-to-resolution per brand — this is the ROI evidence a regional carrier's ops lead needs to justify the spend internally, and (for a BPO-channel deal) something the BPO can hand its own carrier clients as a report.

## 8. GTM, pricing, and revenue (from 2026-09-07 research — see conversation history for full sourcing)

**Buyer segment, sized:** ~150-300 real, named organizations — independent regional carriers (CTIA/CCA's ~100-provider count; named examples: Carolina West, Cellcom, Cellular One, GCI, Southern Linc, Union Telephone), independent MVNOs (est. 40-70 after netting out parent-owned mega-brands like Cricket/Metro/Boost), and a fast-growing pool of NCTC's 700+ small cable operators newly launching mobile via Reach Mobile.

**Consolidation risk:** Verizon has been actively acquiring independent regional carriers since 2020 (Bluegrass Cellular, Chat Mobility, Triangle Mobile, Chariton Valley) — this buyer pool shrinks over time. GTM should move with urgency and build channel relationships (MVNE, BPO) that survive any single carrier's acquisition, rather than betting on individual-carrier longevity.

**Pricing:** $1,500-6,000/month ($18K-72K/year), average ~$30-42K/year — positioned against real comparables (Talkdesk $85/seat/mo, UJET $150/seat/mo with confirmed telecom adoption, mid-market listening contracts at $25-50K/yr) and explicitly *not* self-serve pricing ($24-599/mo reads as "not a real vendor" to this buyer) or enterprise-minimum pricing (Sprinklr's $129,380/yr median is priced for a CX department this buyer doesn't have).

**GTM motion, in priority order:**
1. Lead with an MVNE channel partnership (NCTC/Reach Mobile, or equivalent — Totogi and Tata Communications MOVE both show movement toward the CX layer and are worth a conversation).
2. Simultaneously pursue 3-5 direct lighthouse regional-carrier customers for case studies and trade-press credibility (Fierce Wireless, Light Reading, Telecompetitor all actively cover this segment).
3. Treat telecom BPOs (eClerx, Startek, IBEX) as a secondary, longer-horizon channel — real telecom-vertical practices confirmed, but no named multi-carrier client roster confirmed publicly, so this is a slower, less-proven sell.
4. Use trade events (Cable MVNOs Summit, MVNO Nation USA) for visibility and credibility, not primary lead-gen.

**Revenue math (shown, not asserted):** conservative case ~$240K ARR (150 buyers, 5-10% adoption, $24K/yr avg); base case ~$1.6M ARR (250 buyers incl. new NCTC mobile entrants, 15% adoption over 2-3 years, $42K/yr avg); upside case +$840K ARR from a single MVNE channel conversion at scale. **Combined realistic 3-year target: $1.5M-3M ARR.**

**Explicit, unresolved gaps (do not treat as solved):** no public source discloses what any regional carrier or MVNO actually pays today for comparable software; no small/independent CX vendor has publicly and visibly won multiple regional-carrier/MVNO customers before (no proven playbook exists); no BPO's named multi-carrier client roster is confirmed. **The first real-world action this plan requires — before or alongside early engineering — is discovery calls with 3-5 named regional carriers to validate budget reality.** This is a business-development task, not an engineering one, and should run in parallel with Phase 0 below, not after it.

## 9. Positioning: human-copilot, permanently — not a trust-building phase

Every major incumbent (Sprinklr, Khoros, Emplifi) is currently fighting a trust-in-autonomy objection with its own buyers; consumer trust research found only 18% of consumers trust AI to make financial/consequential decisions independently, and 60% would abandon a tool after one autonomous mistake. This product's answer is architectural, not a temporary caution: **Resolver always drafts, a human always approves and sends.** This is not staged toward eventual full autonomy as the end-state — it is the product's permanent trust model and its main differentiation against incumbents racing toward "AI agent autonomy." (A narrow, opt-in, per-brand exception for a specific low-risk, reversible action class, earned after a long track record of correctly-approved drafts, is a legitimate *future* consideration — but it is explicitly out of scope for this build and not a milestone the roadmap should target.)

## 10. Ethics & Governance

- **Full decision traceability**: every agent decision (classification, confidence, drafted action, routing choice) logged with reasoning and alternatives considered — the `DecisionLogger` pattern already proven in the founder's telecom-call-intelligence project, applied here for the first time in PulseGuard.
- **Output-side screening, not just input-side**: current PulseGuard only screens *incoming* content for PII/prompt-injection. This adds an automated check on *drafted replies* before they reach a human reviewer — tone consistency, no discriminatory language, no promising an action the brand's KB doesn't authorize.
- **Per-tenant data governance**: each Client Brand's data is isolable and deletable on request.
- **Two independent gates, never blended**: a "was this drafted well" quality signal and a "can this brand/tenant's data be trusted" integrity signal are separate, named, independently tracked — never merged into one fuzzy confidence number.

## 11. Security

- Carried forward unchanged: PII hashing/sanitization, prompt-injection framing, timing-safe auth, the corrected rate-limiter trust boundary.
- **New**: per-tenant OAuth credential isolation for every connected social/review account — encrypted at rest, scoped per workspace/brand, never shared across tenants even at the infrastructure level.
- **New**: dependency and secret scanning as a mandatory CI gate, not a periodic manual check.

## 12. Inference & Evals

Current PulseGuard has none of this — it is the largest net-new engineering investment in this spec, and it is non-negotiable given the "no low quality code, ever" bar:
- A **versioned eval set**: labeled real (anonymized) or synthetic complaint examples with ground-truth classification, severity, and an acceptable-draft rubric.
- **Regression gate**: any prompt or model change must run against the eval set before shipping; a score drop below threshold fails CI exactly like a broken unit test.
- **LLM-as-judge scoring** for draft quality (tone, factual grounding against the brand's KB, policy compliance) — automated and repeatable, not a human eyeballing samples.

## 13. Code Quality & CI Gates

- `ruff` + `mypy --strict` + full test suite + eval suite + dependency/secret scan — **all mandatory, all blocking, nothing merges red.**
- **Every change gets a review pass before merge**, even solo — using structured code review as a standing practice, not an occasional check. This directly closes the exact failure mode the pre-pivot audit found: a safety-critical bug (the escalation-ack key mismatch) shipped and stayed broken for weeks specifically because there was no reviewer to catch a two-sided contract breaking.
- **Measured test coverage**, tracked and gated on a real threshold — the audit found the old codebase reported no coverage numbers anywhere, which is exactly how a real gap (zero coverage on the escalation-ack path) hid in plain sight.

## 14. Spend Guard / Stop-on-Stuck

Reusing the pattern already proven in the founder's telecom-call-intelligence project, adopted after a real incident there (a hung batch silently retried twice, ~$1.8 of wasted spend before a human noticed):
- **A BudgetGuard with a hard $ cap**, per-tenant and global, checked *before* every LLM call, not discovered after the fact in a bill.
- **Every LLM client construction has an explicit timeout and `max_retries=1`** — an unbounded timeout is exactly what lets a stuck pipeline burn spend silently.
- **Strict halt-on-failure**: if a pipeline stage errors repeatedly or a tenant's processing looks stuck, that pipeline halts and requires explicit human acknowledgment to resume. It does not silently retry, and a halt on one tenant's pipeline does not take down another tenant's processing.
- Circuit breakers already exist per-adapter (`adapter_circuit_breakers`, `global_circuit_breaker`) — this extends the same concept to LLM spend and per-tenant processing specifically.

## 15. Success Criteria (phased, calibrated to *this* business model — not indie-SaaS assumptions)

The earlier, more generic GTM-economics research proposed success criteria calibrated to self-serve/PLG SaaS ($1K MRR, $10K MRR milestones). Those don't apply here — this is a relationship- and channel-driven sale at $18-72K ACV, not a credit-card self-serve motion, so the milestones below replace those, not supplement them.

**Phase 0 — Business + product validation (parallel tracks, target 8-12 weeks):**
1. Discovery calls with 3-5 named regional carriers/MVNOs (from §8's list) to validate real budget and pain — this closes the single largest unresolved gap in the research and must happen before pricing is locked.
2. One outreach conversation with an MVNE (Reach Mobile/NCTC, Totogi, or Tata Communications MOVE) to gauge channel-partnership interest.
3. A pilot-ready, single-tenant-per-deployment version of the product (reusing the existing agent core + a human-approval review queue) — full multi-tenancy is *not* built speculatively before a paying customer exists; it's justified once 2-3 customers validate the model.
4. All actions remain draft-and-approve only, per §9.

**Phase 1 — First paid pilot (target within 6 months of Phase 0 completion):**
5. Convert at least one discovery conversation into a paid pilot at real dollar terms, inside or near the $18-72K/year band (a discounted or shortened-term pilot is acceptable; a $0 "trial forever" is not — real budget commitment is the signal, not just usage).
6. Validate the full draft-and-approve workflow against a live regional carrier's real complaint volume.
7. Publish-adapter posting confirmed working end-to-end in production for at least one platform (X or Google Business Profile).

**Phase 2 — Channel-driven scale (target 12-24 months):**
8. Land one working MVNE or BPO channel relationship that produces more than one customer per deal.
9. Reach $500K-1M ARR via a mix of direct lighthouse customers and early channel conversions.
10. Build out full multi-tenant infrastructure, the eval/governance layer (§10-§12), and CI quality gates (§13) to production maturity — justified and funded by real revenue at this point, not spent speculatively in Phase 0.

**Phase 3 — Realized beachhead (target 3 years):**
11. $1.5-3M ARR, per §8's revenue math.
12. At least one named case study and trade-press feature (Fierce Wireless, Light Reading, or Telecompetitor).

**Kill/pivot trigger, stated now:** if Phase 0's discovery calls reveal real budget reality materially below the $18-72K/year band across most conversations, or if no paid pilot materializes within 6 months of genuine, active outreach to 10+ named prospects, the honest move is to re-test pricing or the buyer segment — not to extend the timeline indefinitely on the same assumptions.

## 16. Non-goals (explicitly out of scope for this spec)

- No freelancer or solo-social-media-manager positioning, pricing tier, or marketing language, anywhere.
- No expansion beyond telecom operators as the buyer until Phase 2/3 milestones are hit.
- No autonomous/auto-send capability as a roadmap target (see §9) — this is a permanent design decision, not a phase to graduate past.
- No reviving Trustpilot-style undocumented-endpoint scraping for any new source adapter.
- No building the full multi-tenant platform speculatively before Phase 0's discovery calls validate real budget — engineering investment should follow revenue validation, not precede it.

## 17. Changing this spec later

- **Pricing and revenue targets** (§8) are the most likely to move once real discovery-call data comes in — update this section from actual conversations, not from re-modeling the same public comparables.
- **The permanent-copilot decision** (§9) is a considered, evidence-backed position, not a placeholder — changing it should get its own re-confirmation with Vinoth, not a quiet roadmap addition.
- **Scope/sequencing** (§15's phases) are independently checkpointable — stopping after Phase 0 or Phase 1 to reassess is a valid outcome, not a failure to hit an artificial deadline.
