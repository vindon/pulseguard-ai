# PulseGuard frontend design rework — design spec

Date: 2026-09-06
Status: approved by Vinoth, ready for implementation planning
Scope: `frontend/` only. No backend, API, or data-shape changes.

## 1. Problem

The current frontend (Next.js 16, plain CSS custom properties, no component
library) is functional but reads as an internal admin tool rather than a
polished SaaS product. Goal: bring it to the visual and interaction quality
of category-leading CX/ops tools (Zendesk, Freshdesk, ServiceNow) —
specifically their *design principles* (warm neutral palettes, one confident
brand hue plus a jewel-tone accent family, organic depth via gradients and
soft shadows, generous but purposeful whitespace) — adapted into PulseGuard's
own identity. Nothing here reuses Zendesk's actual color names, hex values,
or illustrations.

PulseGuard is the **pilot**. SignalHarvest AI (`~/project/signalharvest`)
gets its own follow-up spec once this one ships and is reviewed running in
the browser, reusing this same token architecture and shadcn component set
with its own accent (currently teal).

## 2. Decisions locked with Vinoth

| Decision | Choice |
|---|---|
| Tooling | Migrate from hand-rolled CSS to **Tailwind CSS + shadcn/ui** |
| Visual direction | Crisp & friendly (Zendesk-like), elevated with jewel-tone accents and gradient depth |
| Pilot product | **PulseGuard AI** first; SignalHarvest ported afterward |
| Brand color | New palette proposed and approved (see §3) — not a re-skin of the current indigo |
| e2e test selectors | Add `data-testid` hooks; update the 6 Playwright spec files off presentational classes |

Approved visual reference: [PulseGuard Design Preview artifact](https://claude.ai/code/artifact/4462ee37-9af5-438f-825a-7ddea88bc4f1)
(palette swatches + app-shell mockup, light/dark toggle). Treat that artifact
as the living visual reference — if it's updated later, this spec's token
table below should be re-synced from it, not the other way around.

## 3. Design tokens — the single source of truth

**This section is the part most likely to change.** Keep every value below
as a named CSS variable (mapped into `tailwind.config.ts` `theme.extend`),
never hardcoded in components. Changing an accent, a radius, or a shadow
later should mean editing one token file, not hunting through components.

### 3.1 Color — light

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#FBF9F5` | App background (warm near-cream, not gray) |
| `--surface` | `#FFFFFF` | Cards, panels, sidebar, topbar |
| `--border` | `#EAE5DA` | Hairlines |
| `--ink` | `#1C1A16` | Primary text (warm near-black) |
| `--muted` | `#726C60` | Secondary text |
| `--brand` | `#2F6FED` | Primary actions, active nav, links |
| `--brand-deep` | `#1E4FC0` | Hover/active state of brand |
| `--brand-tint` | `#E8EFFE` | Brand-tinted backgrounds |
| `--jewel-violet` / `-tint` | `#7C3AED` / `#F0E9FE` | Decorative accent (category chips, gradients) |
| `--jewel-teal` / `-tint` | `#0D9488` / `#DFF5F2` | Decorative accent |
| `--jewel-rose` / `-tint` | `#BE1868` / `#FBE7F0` | Decorative accent |
| `--critical` / `-tint` | `#C0335A` / `#FBE9EF` | Semantic: critical/error only |
| `--warning` / `-tint` | `#B5720A` / `#FCF1DA` | Semantic: warning only |
| `--success` / `-tint` | `#0A7550` / `#E0F5EC` | Semantic: success only |
| `--neutral-tint` | `#F2EFE7` | Neutral badge/hover fill |

> Note: `--success` was darkened from the originally-approved `#0E8A5F` to
> `#0A7550` after a post-implementation WCAG AA contrast check found the
> original value measured below 4.5:1 against both white and
> `--success-tint`; `#0A7550` clears AA with margin (~5.7:1 / ~5.0:1) while
> preserving the same hue.

**Rule:** jewel tones (violet/teal/rose) are decorative/categorical only —
never used to mean "error" or "success." Semantic colors are reserved
exclusively for status. This separation must hold in the component library
(§5), not just the mockup.

### 3.2 Color — dark

| Token | Hex |
|---|---|
| `--bg` | `#17151D` |
| `--surface` | `#201E27` |
| `--border` | `#332F3C` |
| `--ink` | `#F2EFEA` |
| `--muted` | `#A099AA` |
| `--brand` / `-deep` / `-tint` | `#8FADFF` / `#B7C9FF` / `#242C48` |
| `--jewel-violet` / `-tint` | `#B296F7` / `#2A2145` |
| `--jewel-teal` / `-tint` | `#3FDCCB` / `#123632` |
| `--jewel-rose` / `-tint` | `#F17BAE` / `#3B2130` |
| `--critical` / `-tint` | `#F0708F` / `#3B2030` |
| `--warning` / `-tint` | `#F0BD5C` / `#3A2E17` |
| `--success` / `-tint` | `#4FD6A5` / `#123329` |
| `--neutral-tint` | `#272430` |

Same three-state theme contract as today: bare `:root` (light default),
`@media (prefers-color-scheme: dark)` guarded by `:not([data-theme="light"])`,
and `:root[data-theme="dark"]` override. This already exists in
`app/globals.css` — carry the pattern into the Tailwind token setup, just
with the new values above.

### 3.3 Typography

Keep all three fonts already loaded (no font migration needed):
- **Display** — Plus Jakarta Sans (700/800) — page titles, stat values, nav brand
- **Body** — Inter (400/500/600/700) — everything else
- **Mono** — JetBrains Mono (500/600) — signal IDs, timestamps

Introduce a defined scale (replacing today's ad hoc per-component sizing):
`11 / 12 / 13 / 14(base) / 16 / 19 / 23 / 28px`, weights `500/600/700/800`
only (no 400 outside body copy, no 900).

### 3.4 Shape & elevation

- Radius: `10px` small controls, `12–13px` cards/panels, `9999px` pills/badges/avatars
- Shadow: two-layer soft shadow for cards (`--shadow-card`: a 1px near-black hairline shadow + a diffuse 20px blur at low opacity) — see mockup CSS `--shadow-card` for exact values in both themes
- Gradients: brand mark, avatars, and primary buttons use a 100°
  `--brand → --jewel-violet` gradient. This is the one recurring "signature"
  gradient — don't introduce others ad hoc.

## 4. Layout & navigation

Keep the existing sidebar (236px) + topbar shell structure — it's proven,
just rebuilt on the new tokens and shadcn primitives:

- **Sidebar**: gradient brand mark, section-grouped nav, active item gets a
  subtle brand→violet gradient tint background, user row becomes a real
  `DropdownMenu` (sign out, settings placeholder).
- **Topbar**: the search bar becomes a functioning **command palette**
  trigger (shadcn `Command`, bound to `⌘K` / `Ctrl+K`) that jumps to the 5
  pages and (stretch, not required for v1) recently viewed signals. Bell
  icon becomes a `Popover`/`DropdownMenu` listing unacknowledged escalations
  pulled from the same polling data already used for the nav badge.
- **Content**: page header (title/subtitle/primary action) gets a very
  faint dual radial-gradient wash behind it (brand + violet, ~10-14%
  opacity, decorative only, `pointer-events:none`) — matches the mockup,
  must never reduce text contrast below WCAG AA.

## 5. Component mapping

| Current (plain CSS) | New (shadcn primitive) | Notes |
|---|---|---|
| `.stat-card` | `Card` | icon chip color varies by metric per §3.1 rule (decorative jewel tones for non-status metrics, semantic color when the metric *is* a status count, e.g. Escalations → critical tint) |
| `.queue-row` / `.esc-row` | `Table` (custom cell renderers) | sticky header, `Skeleton` rows while loading |
| `.badge` | `Badge` | tone variants: critical / warning / success / neutral (semantic only) |
| new: category chip | small custom component, not shadcn | uses jewel tones only, per mockup `.m-cat-chip` |
| `.drawer` | `Sheet` | right-side, same width behavior (`min(480px, 92vw)`) |
| `.filter-pill` | `ToggleGroup` | |
| `.form-card` + fields | `Card` + `Input`/`Textarea`/`Select`/`Label`/`Form` | |
| `.status-grid` | `Card` grid | unchanged structure |
| `icons.tsx` (custom SVG) | `lucide-react` | same outline style; swap 1:1, drop the hand-rolled file once unused |
| Agent trail / pipeline trail | bespoke (no shadcn equivalent) | keep custom, restyle to tokens, add the pulse animation on the active node (§3.4, respects `prefers-reduced-motion`) |
| Command palette | shadcn `Command` (new) | new capability, not a replacement |
| Notification dropdown | shadcn `DropdownMenu`/`Popover` (new) | new capability |

`usePolling`, `lib/api.ts`, `lib/types.ts`, `lib/format.ts` are unchanged —
this is a presentation-layer rework only.

## 6. Pages in scope

All 5 existing routes, no new routes, no removed routes:

1. `/` Overview — stat cards + recent signals table
2. `/queue` Signal queue — filterable table
3. `/escalations` Escalations — filterable table + acknowledge flow
4. `/status` Adapter status — status card grid
5. `/ingest` Send test signal — form

## 7. Test migration

PulseGuard's Playwright suite (`e2e/*.spec.ts`, 6 files) currently selects
on presentational classes (`.queue-row`, `.esc-row`, `.status-card`,
`.drawer`, `.nav-badge`, `.page-title`, `.callout.-success`,
`.status-dot.-down`, etc.). Under Tailwind these classes disappear.

Plan: add `data-testid` to every element these specs touch (rows, drawer,
nav badge, page title, stat cards, status dots, callouts), update all 6
spec files to select on `data-testid` instead. `vitest` unit tests and the
`a11y.spec.ts` axe scan are re-run as-is after the migration (a11y scan
should improve, not regress — shadcn primitives ship with ARIA roles the
hand-rolled markup didn't always have, e.g. the drawer becomes a real
`Sheet` with proper focus trap).

## 8. Rollout sequence

1. Install & configure Tailwind + shadcn/ui; add tokens from §3 to
   `tailwind.config.ts` and `app/globals.css`.
2. Generate shadcn primitives (`components/ui/*`): Button, Card, Badge,
   Table, Sheet, DropdownMenu, Popover, Command, Input, Textarea, Select,
   Label, Form, ToggleGroup, Tooltip, Skeleton, Separator, Avatar,
   ScrollArea.
3. Rebuild `AppShell` (sidebar, topbar, command palette, notification
   dropdown) — highest-visibility piece, first review checkpoint.
4. Rebuild shared pieces: `Badge`, category chip, stat card, table shell,
   `Sheet`-based drawer, agent trail.
5. Port the 5 pages one at a time onto the new shell/components, adding
   `data-testid`s as each page is touched.
6. Update the 6 e2e spec files to the new selectors (§7); run
   `vitest` + `playwright test` + `a11y.spec.ts` to confirm parity.
7. Vinoth reviews the running app in the browser (`npm run dev`).
8. Only after sign-off: open the SignalHarvest follow-up spec, reusing this
   token architecture and component set with SignalHarvest's own accent.

## 9. Non-goals

- No backend, API, database, or agent-logic changes.
- No new routes or removed functionality.
- No change to `usePolling` intervals or data-fetching strategy.
- SignalHarvest is explicitly out of scope for this spec — separate spec,
  separate approval, after this one ships.

## 10. Changing this spec later

Three things are designed to be cheap to change without re-doing this spec:

- **Colors** — edit §3.1/§3.2 and the corresponding CSS variables /
  `tailwind.config.ts` values. Components reference tokens, never literals.
- **Visual reference** — the approved artifact preview URL in §2 can be
  updated (republished) independently; if it changes materially, re-sync
  the token tables here from it before implementing.
- **Scope/sequencing** — §8's steps are independently checkpointable;
  stopping after step 3 or 4 to re-review before continuing is fine.

Anything touching §5 (which shadcn primitive backs which component) or §7
(test migration approach) is a bigger change and should get a quick
re-confirmation before implementation, since it affects more files.
