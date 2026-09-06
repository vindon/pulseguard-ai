# PulseGuard Frontend Design Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate PulseGuard's frontend from hand-rolled CSS to Tailwind CSS + shadcn/ui, applying the approved crisp/friendly-with-jewel-tones design system, with zero backend/functional changes.

**Architecture:** Presentation-layer-only rework. `lib/api.ts`, `lib/usePolling.ts`, `lib/types.ts`, `lib/format.ts` are untouched. Every component keeps its exact props, state, and data-fetching logic — only markup/className changes from hand-rolled CSS classes to Tailwind utilities backed by shadcn/ui primitives. Work proceeds shell-first (AppShell), then shared building blocks (Badge, StatCard, CategoryChip, AgentTrail), then page-by-page, adding `data-testid` hooks and updating the corresponding Playwright spec as each piece lands — not as one big final step — so every task ends in a green, runnable check.

**Tech Stack:** Next.js 16 (unchanged), Tailwind CSS v4, shadcn/ui (Radix UI primitives + `class-variance-authority` + `tailwind-merge`), `lucide-react` icons, `tw-animate-css`.

**Spec:** `docs/superpowers/specs/2026-09-06-frontend-design-rework-design.md`

## Global Constraints

- No backend, API, database, or agent-logic changes (spec §9).
- No new routes, no removed functionality, no changed data-fetching intervals (spec §9).
- CSP in `next.config.mjs` allows no external script/style hosts (`script-src 'self' 'unsafe-inline'`, `style-src 'self' 'unsafe-inline'`) — Tailwind/shadcn/lucide are all bundled at build time, not loaded from a CDN, so this holds automatically as long as nothing adds an external `<script>`/`<link>` tag.
- Jewel tones (violet/teal/rose) are decorative/categorical only — never repurposed to mean error/warning/success. Semantic colors (`critical`/`warning`/`success`) are reserved exclusively for status (spec §3.1).
- Design tokens (colors, radius, shadow) live only in `app/globals.css` as CSS variables mapped through Tailwind's `@theme inline` — components reference token-backed utility classes (`bg-brand`, `text-critical`, etc.), never literal hex values, except where a value is genuinely per-row runtime data (e.g. `carrierColor()`), which stays inline style as it does today.
- Every exact string asserted by an existing Playwright test (button labels, callout copy, drawer title format `"{category} — {carrier}"`, etc.) must be preserved verbatim.
- `npm run verify` (lint + typecheck + vitest + build + playwright) is the ground truth for "done." Node ≥20.9.0 per `package.json` `engines`.

---

## Task 1: Tailwind CSS v4 setup with design tokens

**Files:**
- Modify: `frontend/package.json` (add devDependencies)
- Create: `frontend/postcss.config.mjs`
- Modify: `frontend/app/globals.css` (full rewrite)

**Interfaces:**
- Produces: CSS custom properties `--bg`, `--surface`, `--border`, `--ink`, `--muted`, `--brand`, `--brand-deep`, `--brand-tint`, `--jewel-violet(-tint)`, `--jewel-teal(-tint)`, `--jewel-rose(-tint)`, `--critical(-tint)`, `--warning(-tint)`, `--success(-tint)`, `--neutral-tint`, `--shadow-card`, `--font-display`, `--font-sans`, `--font-mono` — every later task's Tailwind classes (`bg-brand`, `text-jewel-violet`, `font-display`, `shadow-[var(--shadow-card)]`, etc.) depend on these existing.
- Produces: `.agent-pulse` class + `@keyframes agent-pulse` — consumed by Task 4 (AgentTrail).

- [ ] **Step 1: Install Tailwind v4 and supporting packages**

```bash
cd frontend
npm install -D tailwindcss @tailwindcss/postcss tw-animate-css
```

- [ ] **Step 2: Create the PostCSS config**

`frontend/postcss.config.mjs`:
```js
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};
```

- [ ] **Step 3: Rewrite `app/globals.css` with Tailwind + the approved token set**

Replace the entire file with:
```css
@import "tailwindcss";
@import "tw-animate-css";

:root {
  --bg: #FBF9F5;
  --surface: #FFFFFF;
  --border: #EAE5DA;
  --ink: #1C1A16;
  --muted: #726C60;
  --brand: #2F6FED;
  --brand-deep: #1E4FC0;
  --brand-tint: #E8EFFE;
  --jewel-violet: #7C3AED;
  --jewel-violet-tint: #F0E9FE;
  --jewel-teal: #0D9488;
  --jewel-teal-tint: #DFF5F2;
  --jewel-rose: #BE1868;
  --jewel-rose-tint: #FBE7F0;
  --critical: #C0335A;
  --critical-tint: #FBE9EF;
  --warning: #B5720A;
  --warning-tint: #FCF1DA;
  --success: #0E8A5F;
  --success-tint: #E0F5EC;
  --neutral-tint: #F2EFE7;
  --shadow-card: 0 1px 2px rgba(40,25,15,0.04), 0 8px 20px -14px rgba(40,25,15,0.18);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #17151D;
    --surface: #201E27;
    --border: #332F3C;
    --ink: #F2EFEA;
    --muted: #A099AA;
    --brand: #8FADFF;
    --brand-deep: #B7C9FF;
    --brand-tint: #242C48;
    --jewel-violet: #B296F7;
    --jewel-violet-tint: #2A2145;
    --jewel-teal: #3FDCCB;
    --jewel-teal-tint: #123632;
    --jewel-rose: #F17BAE;
    --jewel-rose-tint: #3B2130;
    --critical: #F0708F;
    --critical-tint: #3B2030;
    --warning: #F0BD5C;
    --warning-tint: #3A2E17;
    --success: #4FD6A5;
    --success-tint: #123329;
    --neutral-tint: #272430;
    --shadow-card: 0 1px 2px rgba(0,0,0,0.3), 0 8px 20px -14px rgba(0,0,0,0.5);
  }
}
:root[data-theme="dark"] {
  --bg: #17151D;
  --surface: #201E27;
  --border: #332F3C;
  --ink: #F2EFEA;
  --muted: #A099AA;
  --brand: #8FADFF;
  --brand-deep: #B7C9FF;
  --brand-tint: #242C48;
  --jewel-violet: #B296F7;
  --jewel-violet-tint: #2A2145;
  --jewel-teal: #3FDCCB;
  --jewel-teal-tint: #123632;
  --jewel-rose: #F17BAE;
  --jewel-rose-tint: #3B2130;
  --critical: #F0708F;
  --critical-tint: #3B2030;
  --warning: #F0BD5C;
  --warning-tint: #3A2E17;
  --success: #4FD6A5;
  --success-tint: #123329;
  --neutral-tint: #272430;
  --shadow-card: 0 1px 2px rgba(0,0,0,0.3), 0 8px 20px -14px rgba(0,0,0,0.5);
}

@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-border: var(--border);
  --color-ink: var(--ink);
  --color-muted: var(--muted);
  --color-brand: var(--brand);
  --color-brand-deep: var(--brand-deep);
  --color-brand-tint: var(--brand-tint);
  --color-jewel-violet: var(--jewel-violet);
  --color-jewel-violet-tint: var(--jewel-violet-tint);
  --color-jewel-teal: var(--jewel-teal);
  --color-jewel-teal-tint: var(--jewel-teal-tint);
  --color-jewel-rose: var(--jewel-rose);
  --color-jewel-rose-tint: var(--jewel-rose-tint);
  --color-critical: var(--critical);
  --color-critical-tint: var(--critical-tint);
  --color-warning: var(--warning);
  --color-warning-tint: var(--warning-tint);
  --color-success: var(--success);
  --color-success-tint: var(--success-tint);
  --color-neutral-tint: var(--neutral-tint);
  --font-display: var(--font-jakarta), -apple-system, sans-serif;
  --font-sans: var(--font-inter), -apple-system, sans-serif;
  --font-mono: var(--font-jetbrains), 'SF Mono', monospace;
}

*{box-sizing:border-box;}
html,body{height:100%;}
body{
  margin:0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  font-size: 14px;
  line-height: 1.5;
}
:focus-visible{outline:2px solid var(--brand); outline-offset:2px; border-radius:4px;}

@keyframes agent-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand) 45%, transparent); }
  50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--brand) 0%, transparent); }
}
.agent-pulse { animation: agent-pulse 1.8s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) {
  .agent-pulse { animation: none; }
}
```

Note: this deletes every `.shell`, `.sidebar`, `.queue-row`, `.badge`, etc. rule from the old file. The app will render unstyled/structurally-broken for any component not yet ported in a later task — expected mid-migration state, resolved by Task 8.

- [ ] **Step 4: Verify the build compiles**

Run: `npm run build`
Expected: build succeeds (pages will look unstyled — that's expected until later tasks land; the check here is that Tailwind compiles with no CSS/PostCSS errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/postcss.config.mjs frontend/app/globals.css
git commit -m "Set up Tailwind CSS v4 with the approved design tokens"
```

---

## Task 2: shadcn/ui installation and primitives

**Files:**
- Create: `frontend/components.json`
- Create: `frontend/lib/utils.ts`
- Create: `frontend/components/ui/{button,badge,sheet,dropdown-menu,popover,command,input,textarea,select,label,toggle-group,tooltip,skeleton,separator,avatar,scroll-area}.tsx` (generated by CLI — no `table` or `card`; see the Task 5 note on rows staying as buttons, and the Task 4 note on `StatCard` staying a plain styled `div`)
- Modify: `frontend/components/ui/sheet.tsx` (accessible-name fix, see Step 4)
- Modify: `frontend/package.json` (new dependencies from the CLI)

**Interfaces:**
- Produces: `cn()` from `@/lib/utils` — consumed by every component task from here on.
- Produces: shadcn primitives importable from `@/components/ui/*` — consumed by Tasks 3–8.

- [ ] **Step 1: Write `components.json` so `shadcn add` targets our token setup**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "app/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 2: Generate the primitives**

```bash
cd frontend
npx shadcn@latest add button badge sheet dropdown-menu popover command input textarea select label toggle-group tooltip skeleton separator avatar scroll-area
```

This creates `lib/utils.ts` and `components/ui/*.tsx`, and installs `lucide-react`, `class-variance-authority`, `clsx`, `tailwind-merge`, `cmdk`, and the relevant `@radix-ui/react-*` packages into `package.json`.

- [ ] **Step 3: Run the build to confirm the generated files compile as-is**

Run: `npm run build`
Expected: succeeds. If the CLI's generated `app/globals.css` additions conflict with Task 1's `@theme inline` block, reconcile by keeping Task 1's token names and removing any duplicate/default shadcn color tokens the CLI appended (e.g. its own `--background`/`--foreground` if unused elsewhere).

- [ ] **Step 4: Guarantee the Sheet's close button has an explicit accessible label**

Open `components/ui/sheet.tsx`. Find the `SheetContent`'s built-in close button (a `SheetPrimitive.Close` styled as a small icon button, typically containing an `<XIcon />` and a `sr-only` "Close" span). Add an explicit `aria-label="Close"` to that `SheetPrimitive.Close` element so `page.getByLabel('Close')` (used throughout the e2e suite, e.g. `frontend/e2e/queue.spec.ts:27`) matches it regardless of the exact accessible-name computation the generated markup uses. Example of the element after the edit:

```tsx
<SheetPrimitive.Close
  aria-label="Close"
  className="ring-offset-background focus:ring-ring data-[state=open]:bg-secondary absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:outline-hidden disabled:pointer-events-none"
>
  <XIcon className="size-4" />
  <span className="sr-only">Close</span>
</SheetPrimitive.Close>
```

(Keep whatever className the CLI actually generated — only add the `aria-label="Close"` attribute.)

- [ ] **Step 5: Verify**

Run: `npm run build`
Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/components.json frontend/lib/utils.ts frontend/components/ui frontend/package.json frontend/package-lock.json
git commit -m "Install shadcn/ui primitives"
```

---

## Task 3: Rebuild AppShell — sidebar, topbar, command palette, notification dropdown

**Files:**
- Modify: `frontend/components/AppShell.tsx`
- Modify: `frontend/e2e/overview.spec.ts` (nav-badge assertion only)

**Interfaces:**
- Consumes: `usePolling<EscalationsResponse>` from `@/lib/usePolling` (unchanged), `relativeTime` from `@/lib/format`, shadcn `DropdownMenu*`/`CommandDialog`/`CommandInput`/`CommandList`/`CommandEmpty`/`CommandGroup`/`CommandItem` from Task 2.
- Produces: a `[data-testid="nav-badge"]` element showing the unacknowledged-escalation count — consumed by `overview.spec.ts` (this task) and `escalations.spec.ts` (Task 6).

- [ ] **Step 1: Update the nav-badge assertion in `overview.spec.ts` to the new selector (red)**

In `frontend/e2e/overview.spec.ts`, change:
```ts
  test('sidebar shows the unacknowledged escalation badge', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.nav-badge')).toHaveText('1');
  });
```
to:
```ts
  test('sidebar shows the unacknowledged escalation badge', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('nav-badge')).toHaveText('1');
  });
```

- [ ] **Step 2: Confirm it currently fails**

Run: `npm run build && npx playwright test e2e/overview.spec.ts -g "sidebar shows the unacknowledged escalation badge"`
Expected: FAIL — `nav-badge` testid doesn't exist yet.

- [ ] **Step 3: Rewrite `components/AppShell.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import type { EscalationsResponse } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime } from '@/lib/format';
import { LayoutGrid, List, TriangleAlert, Activity, Send, Search, Bell, ShieldCheck, ChevronDown } from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const NAV_ITEMS = [
  { href: '/', label: 'Overview', icon: LayoutGrid },
  { href: '/queue', label: 'Signal queue', icon: List },
  { href: '/escalations', label: 'Escalations', icon: TriangleAlert, badgeKey: 'escalations' as const },
  { href: '/status', label: 'Adapter status', icon: Activity },
  { href: '/ingest', label: 'Send test signal', icon: Send },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { data } = usePolling<EscalationsResponse>('/escalations?acknowledged=false', 20000);
  const unacknowledged = data?.count ?? 0;
  const recentEscalations = (data?.briefs ?? []).slice(0, 4);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  function goTo(href: string) {
    setPaletteOpen(false);
    router.push(href);
  }

  return (
    <div className="grid min-h-screen grid-cols-[236px_1fr]">
      <aside className="flex flex-col border-r border-border bg-surface p-3">
        <div className="flex items-center gap-2.5 px-2 pb-5 pt-1">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br from-brand to-jewel-violet text-white shadow-[0_4px_10px_-4px_rgba(47,111,237,0.5)]">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="font-display text-[14.5px] font-extrabold leading-none">PulseGuard</div>
            <div className="mt-0.5 text-[10px] text-muted">Telecom CX triage</div>
          </div>
        </div>

        <nav aria-label="Primary" className="flex-1">
          <div className="px-2.5 pb-1.5 pt-3 font-display text-[10px] font-bold uppercase tracking-wider text-muted">
            Workspace
          </div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`mb-0.5 flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-[13px] font-semibold ${
                  active
                    ? 'bg-gradient-to-r from-brand-tint to-jewel-violet-tint text-brand-deep'
                    : 'text-muted hover:bg-neutral-tint hover:text-ink'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">{item.label}</span>
                {item.badgeKey === 'escalations' && unacknowledged > 0 && (
                  <span
                    data-testid="nav-badge"
                    className="ml-auto rounded-full bg-critical-tint px-1.5 py-0.5 text-[10px] font-bold text-critical"
                  >
                    {unacknowledged}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-border pt-3">
          <DropdownMenu>
            <DropdownMenuTrigger className="flex w-full items-center gap-2.5 rounded-[9px] p-2 text-left hover:bg-neutral-tint">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-jewel-violet text-[10.5px] font-bold text-white">
                VN
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] font-semibold">Vinoth N.</div>
                <div className="truncate text-[10px] text-muted">CX Operations</div>
              </div>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-52">
              <DropdownMenuLabel>Vinoth N.</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>Settings</DropdownMenuItem>
              <DropdownMenuItem disabled>Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex h-[54px] shrink-0 items-center gap-3 border-b border-border bg-surface px-6">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex max-w-[420px] flex-1 items-center gap-2 rounded-[9px] border border-border bg-bg px-3 py-2 text-left text-[13px] text-muted"
          >
            <Search className="h-3.5 w-3.5 shrink-0" />
            <span className="flex-1">Search signals, carriers, categories…</span>
            <kbd className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted">
              ⌘K
            </kbd>
          </button>

          <div className="ml-auto flex items-center gap-2.5">
            <DropdownMenu>
              <DropdownMenuTrigger className="relative flex h-[30px] w-[30px] items-center justify-center rounded-lg text-muted hover:bg-neutral-tint">
                <Bell className="h-[15px] w-[15px]" />
                {unacknowledged > 0 && (
                  <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full border-[1.5px] border-surface bg-critical" />
                )}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80">
                <DropdownMenuLabel>Unacknowledged escalations</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {recentEscalations.length === 0 && (
                  <div className="px-2 py-3 text-center text-[12.5px] text-muted">Nothing waiting right now.</div>
                )}
                {recentEscalations.map((brief) => (
                  <DropdownMenuItem key={brief.signal_id} onSelect={() => goTo('/escalations')}>
                    <div className="min-w-0">
                      <div className="truncate text-[12.5px] font-medium">{brief.summary}</div>
                      <div className="text-[11px] text-muted">
                        {brief.category} · {relativeTime(brief.escalated_at)}
                      </div>
                    </div>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => goTo('/escalations')}>View all escalations</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1">{children}</main>
      </div>

      <CommandDialog open={paletteOpen} onOpenChange={setPaletteOpen}>
        <CommandInput placeholder="Jump to a page…" />
        <CommandList>
          <CommandEmpty>No results.</CommandEmpty>
          <CommandGroup heading="Workspace">
            {NAV_ITEMS.map((item) => (
              <CommandItem key={item.href} onSelect={() => goTo(item.href)}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </div>
  );
}
```

- [ ] **Step 4: Run the targeted test again**

Run: `npm run build && npx playwright test e2e/overview.spec.ts -g "sidebar shows the unacknowledged escalation badge"`
Expected: PASS. (The other `overview.spec.ts` test will still fail — its `.page-title`/`.stat-card`/`.queue-row` assertions aren't satisfiable until Task 5. That's expected at this point in the plan.)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/AppShell.tsx frontend/e2e/overview.spec.ts
git commit -m "Rebuild AppShell on Tailwind + shadcn with a command palette and notification dropdown"
```

---

## Task 4: Shared building blocks — Badge, CategoryChip, StatCard, AgentTrail

**Files:**
- Modify: `frontend/components/Badge.tsx`
- Create: `frontend/components/CategoryChip.tsx`
- Create: `frontend/components/StatCard.tsx`
- Modify: `frontend/components/AgentTrail.tsx`

**Interfaces:**
- Produces: `Badge({tone, dot, children})` default export, plus named exports `severityTone`, `severityLabel`, `stageTone`, `stageLabel` — signatures unchanged from the original, consumed by Tasks 5 and 6.
- Produces: `CategoryChip({category}: {category: string})` default export and `categoryTone(category: string): 'violet'|'teal'|'rose'` named export — consumed by Task 5 (QueueTable).
- Produces: `StatCard({label, value, sub, icon, iconTone}: {label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; iconTone?: 'violet'|'critical'|'success'|'teal'})` default export — consumed by Tasks 5 and 7.
- Produces: `AgentTrail({signal}: {signal: SignalLifecycle})` default export — same prop shape as before, consumed by Task 5.

Note on a spec deviation: §5 of the design spec maps `.stat-card` to shadcn's `Card` primitive. `StatCard` below is a plain styled `div` instead. Reason: shadcn's generated `Card` component's default classes reference shadcn's own conventional tokens (`bg-card`, `border`, etc.), which don't exist in our token set from Task 1 (`--surface`, `--border`, ...) — using it would mean either defining a second, parallel token namespace just for `Card` or overriding every one of its default classes via `className`, for a component that here needs no header/footer/action composability, just a bordered, padded, shadowed box. A plain `div` styled directly off our own tokens is simpler and has no version-specific internals to fight.

No e2e spec currently targets these units in isolation (they're only checked once wired into a page in later tasks), so this task's automated check is build/typecheck only — consistent with this project's existing test strategy (no unit-test layer; behavior is verified end-to-end via Playwright, per `vitest.config.mts`).

- [ ] **Step 1: Rewrite `components/Badge.tsx`**

```tsx
type Tone = 'critical' | 'warning' | 'success' | 'neutral';

const TONE_CLASSES: Record<Tone, string> = {
  critical: 'bg-critical-tint text-critical',
  warning: 'bg-warning-tint text-warning',
  success: 'bg-success-tint text-success',
  neutral: 'bg-neutral-tint text-muted',
};

export default function Badge({
  tone,
  dot = false,
  children,
}: {
  tone: Tone;
  dot?: boolean;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${TONE_CLASSES[tone]}`}
    >
      {dot && <span className="h-[5px] w-[5px] rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function severityTone(severity: 'P1' | 'P2' | 'P3' | undefined): Tone {
  if (severity === 'P1') return 'critical';
  if (severity === 'P2') return 'warning';
  return 'neutral';
}

export function severityLabel(severity: 'P1' | 'P2' | 'P3' | undefined): string {
  if (severity === 'P1') return 'P1 Critical';
  if (severity === 'P2') return 'P2 High';
  if (severity === 'P3') return 'P3 Standard';
  return 'Unranked';
}

export function stageTone(stage: string): Tone {
  if (stage === 'escalated') return 'critical';
  if (stage === 'resolved') return 'success';
  if (stage === 'triaged') return 'warning';
  return 'neutral';
}

export function stageLabel(stage: string): string {
  switch (stage) {
    case 'validated':
      return 'Validated';
    case 'triaged':
      return 'Triaged';
    case 'resolved':
      return 'Resolved';
    case 'escalated':
      return 'Escalated';
    default:
      return 'Unknown';
  }
}
```

- [ ] **Step 2: Create `components/CategoryChip.tsx`**

```tsx
type CategoryTone = 'violet' | 'teal' | 'rose';

const TONE_CLASSES: Record<CategoryTone, string> = {
  violet: 'bg-jewel-violet-tint text-jewel-violet',
  teal: 'bg-jewel-teal-tint text-jewel-teal',
  rose: 'bg-jewel-rose-tint text-jewel-rose',
};

const TONES: CategoryTone[] = ['violet', 'teal', 'rose'];

// Deterministic hash so the same category string always renders the same
// jewel tone across the app, without maintaining a manual category-to-color
// map that would need updating every time Triage introduces a new category.
export function categoryTone(category: string): CategoryTone {
  let hash = 0;
  for (let i = 0; i < category.length; i++) {
    hash = (hash * 31 + category.charCodeAt(i)) >>> 0;
  }
  return TONES[hash % TONES.length];
}

export default function CategoryChip({ category }: { category: string }) {
  const tone = categoryTone(category);
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-[7px] py-0.5 text-[9.5px] font-bold ${TONE_CLASSES[tone]}`}
    >
      {category}
    </span>
  );
}
```

- [ ] **Step 3: Create `components/StatCard.tsx`**

```tsx
import type { ReactNode } from 'react';

type IconTone = 'violet' | 'critical' | 'success' | 'teal';

const ICON_TONE_CLASSES: Record<IconTone, string> = {
  violet: 'bg-jewel-violet-tint text-jewel-violet',
  critical: 'bg-critical-tint text-critical',
  success: 'bg-success-tint text-success',
  teal: 'bg-jewel-teal-tint text-jewel-teal',
};

export default function StatCard({
  label,
  value,
  sub,
  icon,
  iconTone = 'violet',
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  iconTone?: IconTone;
}) {
  return (
    <div
      data-testid="stat-card"
      className="rounded-xl border border-border bg-surface p-3.5 shadow-[var(--shadow-card)]"
    >
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-muted">{label}</span>
        {icon && (
          <span
            className={`flex h-[23px] w-[23px] items-center justify-center rounded-md ${ICON_TONE_CLASSES[iconTone]}`}
          >
            {icon}
          </span>
        )}
      </div>
      <div className="mt-1.5 font-display text-[23px] font-extrabold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-[10.5px] font-semibold text-success">{sub}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Rewrite `components/AgentTrail.tsx`**

```tsx
import { Check, TriangleAlert, Circle } from 'lucide-react';
import type { SignalLifecycle } from '@/lib/types';

type NodeState = 'done' | 'active' | 'escalated' | 'pending';

const NODE_CLASSES: Record<NodeState, string> = {
  done: 'border-success bg-success text-white',
  active: 'border-brand bg-brand text-white agent-pulse',
  escalated: 'border-critical bg-critical text-white',
  pending: 'border-border bg-surface text-muted',
};

function nodeIcon(state: NodeState) {
  if (state === 'done') return <Check className="h-2.5 w-2.5" />;
  if (state === 'escalated') return <TriangleAlert className="h-2.5 w-2.5" strokeWidth={2.4} />;
  return <Circle className="h-2.5 w-2.5" />;
}

function deriveStates(signal: SignalLifecycle): [NodeState, NodeState, NodeState] {
  const sentinelDone = Boolean(signal.sentinel);
  const triageDone = Boolean(signal.triage);
  const finalDone = Boolean(signal.resolver) || Boolean(signal.escalation);
  const finalEscalated = Boolean(signal.escalation);

  const sentinel: NodeState = sentinelDone ? 'done' : 'active';
  const triage: NodeState = triageDone ? 'done' : sentinelDone ? 'active' : 'pending';
  const final: NodeState = finalDone
    ? finalEscalated
      ? 'escalated'
      : 'done'
    : triageDone
      ? 'active'
      : 'pending';

  return [sentinel, triage, final];
}

export default function AgentTrail({ signal }: { signal: SignalLifecycle }) {
  const [sentinel, triage, final] = deriveStates(signal);
  return (
    <div
      className="flex items-center"
      title={`Sentinel: ${sentinel} · Triage: ${triage} · Resolver/Escalation: ${final}`}
    >
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[sentinel]}`}
      >
        {nodeIcon(sentinel)}
      </div>
      <div className={`h-0.5 w-3 shrink-0 ${sentinel === 'done' ? 'bg-success' : 'bg-border'}`} />
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[triage]}`}
      >
        {nodeIcon(triage)}
      </div>
      <div className={`h-0.5 w-3 shrink-0 ${triage === 'done' ? 'bg-success' : 'bg-border'}`} />
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[final]}`}
      >
        {nodeIcon(final)}
      </div>
    </div>
  );
}
```

Note `deriveStates` is byte-for-byte identical logic to the original — only the rendered markup changed.

- [ ] **Step 5: Verify**

Run: `npm run typecheck && npm run build`
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/Badge.tsx frontend/components/CategoryChip.tsx frontend/components/StatCard.tsx frontend/components/AgentTrail.tsx
git commit -m "Add Tailwind-based Badge, CategoryChip, StatCard, and restyle AgentTrail"
```

---

## Task 5: Port QueueTable, SignalDrawer, OverviewStats, Overview page, Queue page

**Files:**
- Modify: `frontend/components/QueueTable.tsx`
- Modify: `frontend/components/SignalDrawer.tsx`
- Modify: `frontend/components/OverviewStats.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/queue/page.tsx`
- Modify: `frontend/e2e/overview.spec.ts` (remaining assertions)
- Modify: `frontend/e2e/queue.spec.ts`
- Modify: `frontend/e2e/a11y.spec.ts` (drawer selectors)

**Interfaces:**
- Consumes: `Badge`/`severityTone`/`severityLabel`/`stageTone`/`stageLabel` (Task 4), `CategoryChip` (Task 4), `StatCard` (Task 4), `AgentTrail` (Task 4), shadcn `ToggleGroup`/`ToggleGroupItem`, `Sheet`/`SheetContent`/`SheetHeader`/`SheetTitle`/`SheetFooter`, `Button` (Task 2).
- Produces: `[data-testid="page-title"]`, `[data-testid="stat-card"]` (from StatCard), `[data-testid="queue-row"]`, `[data-testid="signal-drawer"]`, `[data-testid="timeline-agent"]`, `[data-testid="drawer-footer"]`, `[data-testid="empty-state"]` — consumed by this task's own specs and reused by `escalations.spec.ts` (Task 6) via `SignalDrawer`.

Note on a spec deviation: §5 of the design spec lists shadcn's `Table` primitive as the mapping for `.queue-row`/`.esc-row`. This task keeps rows as clickable `<button>` elements in a CSS grid instead, matching the original implementation's structure (Task 6 does the same for escalation rows). Reason: shadcn's `Table` renders a real `<table>/<tbody>/<tr>/<td>` tree, and a `<button>` isn't valid markup inside `<tr>`/`<td>` — the original code already avoided native table semantics for exactly this reason (a whole clickable row is simpler as a styled button than as a `<tr>` with a click handler plus cell-level focus management). Using `Table` here would mean rebuilding the row-click interaction, not just restyling it, which is out of scope for a presentation-only rework. The visual result (borders, spacing, hover state) is unaffected.

- [ ] **Step 1: Update `e2e/overview.spec.ts` and `e2e/queue.spec.ts` to the new selectors (red)**

Replace `frontend/e2e/overview.spec.ts` in full:
```ts
import { test, expect } from './fixtures';

test.describe('Overview', () => {
  test('loads with stats and recent signals, no console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(String(err)));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/');

    await expect(page.getByTestId('page-title')).toHaveText('Overview');
    await expect(page.getByTestId('stat-card')).toHaveCount(4);
    await expect(page.getByText('Recent signals')).toBeVisible();

    await expect(page.getByTestId('queue-row')).toHaveCount(2);
    await expect(page.getByText(/Verizon overcharged me AGAIN/)).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('sidebar shows the unacknowledged escalation badge', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('nav-badge')).toHaveText('1');
  });
});
```

Replace `frontend/e2e/queue.spec.ts` in full:
```ts
import { test, expect } from './fixtures';

test.describe('Signal queue', () => {
  test('lists both fixture signals and filters by source', async ({ page }) => {
    await page.goto('/queue');
    await expect(page.getByTestId('queue-row')).toHaveCount(2);

    await page.getByRole('button', { name: 'App Store' }).click();
    await expect(page.getByTestId('queue-row')).toHaveCount(1);
    await expect(page.getByText(/eSIM won't activate/)).toBeVisible();

    await page.getByRole('button', { name: 'All feeds' }).click();
    await expect(page.getByTestId('queue-row')).toHaveCount(2);
  });

  test('opens the detail drawer with the full agent trail and closes it', async ({ page }) => {
    await page.goto('/queue');
    await page.getByTestId('queue-row').filter({ hasText: 'Verizon overcharged' }).click();

    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText('Billing dispute — verizon')).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Sentinel' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Triage' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Escalation' })).toBeVisible();
    await expect(drawer.getByRole('button', { name: /Acknowledge/ })).toBeVisible();

    await drawer.getByLabel('Close').click();
    await expect(drawer).toBeHidden();
  });

  test('resolved signal shows a Resolved badge and no escalation section', async ({ page }) => {
    await page.goto('/queue');
    await page.getByTestId('queue-row').filter({ hasText: "eSIM won't activate" }).click();

    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Resolver' })).toBeVisible();
    await expect(drawer.getByTestId('timeline-agent').filter({ hasText: 'Escalation' })).toHaveCount(0);
    await expect(drawer.getByTestId('drawer-footer')).not.toBeVisible();
  });
});
```

Replace the drawer-related test in `frontend/e2e/a11y.spec.ts`:
```ts
  test('the signal detail drawer has no violations while open', async ({ page }) => {
    await page.goto('/queue');
    await page.getByTestId('queue-row').first().click();
    await expect(page.getByTestId('signal-drawer')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
```

- [ ] **Step 2: Confirm these fail**

Run: `npm run build && npx playwright test e2e/overview.spec.ts e2e/queue.spec.ts e2e/a11y.spec.ts`
Expected: FAIL — none of the new testids exist yet.

- [ ] **Step 3: Rewrite `components/QueueTable.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { PipelineSignalsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial, sourceLabel } from '@/lib/format';
import Badge, { severityTone, severityLabel, stageTone, stageLabel } from './Badge';
import CategoryChip from './CategoryChip';
import AgentTrail from './AgentTrail';
import SignalDrawer from './SignalDrawer';
import { ChevronRight, Inbox } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

const SOURCES = [
  { value: null, label: 'All feeds' },
  { value: 'x', label: 'X' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'google_play', label: 'Google Play' },
  { value: 'app_store', label: 'App Store' },
  { value: 'trustpilot', label: 'Trustpilot' },
  { value: 'quora', label: 'Quora' },
];

export default function QueueTable({
  hours = 24,
  limit,
  showFilters = false,
  initialData = null,
}: {
  hours?: number;
  limit?: number;
  showFilters?: boolean;
  initialData?: PipelineSignalsResponse | null;
}) {
  const [source, setSource] = useState<string | null>(null);
  const path = `/pipeline/signals?hours=${hours}${source ? `&source=${source}` : ''}`;
  const { data, error, loading } = usePolling<PipelineSignalsResponse>(
    path,
    5000,
    source === null ? initialData : null
  );
  const [selected, setSelected] = useState<SignalLifecycle | null>(null);

  const signals = (data?.signals ?? []).slice(0, limit);

  return (
    <>
      {showFilters && (
        <ToggleGroup
          type="single"
          value={source ?? 'all'}
          onValueChange={(v) => setSource(v === 'all' || !v ? null : v)}
          className="mb-4 flex-wrap justify-start gap-2"
        >
          {SOURCES.map((s) => (
            <ToggleGroupItem
              key={s.label}
              value={s.value ?? 'all'}
              className="rounded-full border border-border px-3 py-1.5 text-[12.5px] font-semibold text-muted data-[state=on]:bg-ink data-[state=on]:text-bg"
            >
              {s.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
      <div className="overflow-hidden rounded-[13px] border border-border bg-surface shadow-[var(--shadow-card)]">
        <div className="grid grid-cols-[28px_1.3fr_96px_150px_96px_84px_20px] gap-3.5 border-b border-border px-4 py-2.5 text-[10px] font-bold uppercase tracking-wide text-muted">
          <div></div>
          <div>Signal</div>
          <div>Carrier</div>
          <div>Agent trail</div>
          <div className="text-right">Priority</div>
          <div className="text-right">Time</div>
          <div></div>
        </div>

        {loading && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Loading live signals…
          </div>
        )}

        {!loading && !error && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            <Inbox className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <div>No signals in the last {hours}h. Send a test signal to see the pipeline run.</div>
          </div>
        )}

        {error && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Couldn&apos;t reach the gateway — {error}
          </div>
        )}

        {signals.map((signal) => {
          const sentinel = signal.sentinel;
          const carrier = sentinel?.carrier ?? null;
          return (
            <button
              key={signal.signal_id}
              type="button"
              data-testid="queue-row"
              className={`grid w-full grid-cols-[28px_1.3fr_96px_150px_96px_84px_20px] items-center gap-3.5 border-b border-border px-4 py-[11px] text-left text-[12.5px] last:border-b-0 hover:bg-neutral-tint ${
                selected?.signal_id === signal.signal_id
                  ? 'bg-gradient-to-r from-brand-tint to-jewel-violet-tint'
                  : ''
              }`}
              onClick={() => setSelected(signal)}
            >
              <div
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                style={{ background: carrierColor(carrier) }}
              >
                {carrierInitial(carrier)}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[12.5px] font-semibold">
                  {sentinel?.content_preview || '(content pending validation)'}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted">
                  <CategoryChip
                    category={signal.triage?.category ?? (sentinel ? sourceLabel(sentinel.source) : 'Uncategorised')}
                  />
                  <span className="font-mono">{signal.signal_id.slice(0, 8)}</span>
                </div>
              </div>
              <div>
                <Badge tone="neutral">{carrier ?? 'Unknown'}</Badge>
              </div>
              <AgentTrail signal={signal} />
              <div className="text-right">
                {signal.stage === 'escalated' || signal.stage === 'resolved' ? (
                  <Badge tone={signal.stage === 'resolved' ? 'success' : severityTone(signal.severity)} dot>
                    {signal.stage === 'resolved' ? 'Resolved' : severityLabel(signal.severity)}
                  </Badge>
                ) : (
                  <Badge tone={stageTone(signal.stage)}>{stageLabel(signal.stage)}</Badge>
                )}
              </div>
              <div className="text-right text-[12px] tabular-nums text-muted">
                {sentinel?.posted_at ? relativeTime(sentinel.posted_at) : '—'}
              </div>
              <div className="flex text-muted">
                <ChevronRight className="h-[15px] w-[15px]" />
              </div>
            </button>
          );
        })}
      </div>

      {selected && <SignalDrawer signal={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
```

- [ ] **Step 4: Rewrite `components/SignalDrawer.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { SignalLifecycle } from '@/lib/types';
import { relativeTime, sourceLabel } from '@/lib/format';
import { requestRefresh } from '@/lib/usePolling';
import Badge, { severityTone, severityLabel } from './Badge';
import { Check, Download, TriangleAlert } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';

export default function SignalDrawer({
  signal,
  onClose,
}: {
  signal: SignalLifecycle;
  onClose: () => void;
}) {
  const [acking, setAcking] = useState(false);
  const [acked, setAcked] = useState(signal.escalation?.acknowledged ?? false);
  const [ackError, setAckError] = useState<string | null>(null);

  async function acknowledge() {
    setAcking(true);
    setAckError(null);
    try {
      const res = await fetch(`/api/proxy/escalations/${signal.signal_id}/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ack_by: 'vinoth@pulseguard.local' }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setAcked(true);
      requestRefresh();
    } catch (err) {
      setAckError(err instanceof Error ? err.message : 'Acknowledge failed');
    } finally {
      setAcking(false);
    }
  }

  function exportJson() {
    window.open(`/api/proxy/escalations/${signal.signal_id}/export`, '_blank');
  }

  const carrier = signal.sentinel?.carrier ?? 'Unknown carrier';
  const category = signal.triage?.category ?? signal.sentinel?.source ?? 'Uncategorised';

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        data-testid="signal-drawer"
        className="flex w-[min(480px,92vw)] flex-col gap-0 p-0 sm:max-w-none"
        aria-label={`Signal ${signal.signal_id}`}
      >
        <SheetHeader className="gap-2 border-b border-border px-6 py-5 text-left">
          <span className="font-mono text-[11.5px] text-muted">
            {signal.signal_id.slice(0, 8)} · {signal.sentinel ? sourceLabel(signal.sentinel.source) : '—'}
          </span>
          <SheetTitle className="font-display text-[17px] font-extrabold">
            {category} — {carrier}
          </SheetTitle>
          <div className="flex flex-wrap gap-1.5">
            {signal.severity && (
              <Badge tone={severityTone(signal.severity)} dot>
                {severityLabel(signal.severity)}
              </Badge>
            )}
            {signal.triage && (
              <Badge tone="neutral">Churn risk: {signal.triage.churn_risk ? 'High' : 'Low'}</Badge>
            )}
            {signal.triage && <Badge tone="neutral">Sentiment: {signal.triage.sentiment_score.toFixed(2)}</Badge>}
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-wide text-muted">Agent trail</div>
          <div className="flex flex-col">
            {signal.sentinel && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-success-tint text-success">
                    <Check className="h-3.5 w-3.5" />
                  </div>
                  <div className="mt-1 w-0.5 flex-1 bg-border" />
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Sentinel
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    validated · {relativeTime(signal.sentinel.validated_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    {signal.sentinel.validity_reason ?? 'Deduplicated, PII-sanitised, carrier detected.'}
                  </div>
                </div>
              </div>
            )}

            {signal.triage && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-success-tint text-success">
                    <Check className="h-3.5 w-3.5" />
                  </div>
                  {(signal.resolver || signal.escalation) && <div className="mt-1 w-0.5 flex-1 bg-border" />}
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Triage
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    classified · {relativeTime(signal.triage.triaged_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    Category: {signal.triage.category} · Tier {signal.triage.resolution_tier} · severity{' '}
                    {signal.triage.severity_score}/5 · routed to {signal.triage.routing_decision}
                  </div>
                </div>
              </div>
            )}

            {signal.resolver && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div
                    className={`flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full ${
                      signal.resolver.resolved ? 'bg-success-tint text-success' : 'bg-critical-tint text-critical'
                    }`}
                  >
                    {signal.resolver.resolved ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : (
                      <TriangleAlert className="h-3.5 w-3.5" />
                    )}
                  </div>
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Resolver
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    {signal.resolver.resolved ? 'resolved' : 'attempted'} ·{' '}
                    {relativeTime(signal.resolver.resolved_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    Confidence {(signal.resolver.confidence_score * 100).toFixed(0)}%
                    {signal.resolver.escalation_reason ? ` — ${signal.resolver.escalation_reason}` : ''}
                  </div>
                  <div className="mt-2 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal text-ink">
                    {signal.resolver.draft_response}
                  </div>
                </div>
              </div>
            )}

            {signal.escalation && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-critical-tint text-critical">
                    <TriangleAlert className="h-3.5 w-3.5" />
                  </div>
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Escalation
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    raised · {relativeTime(signal.escalation.escalated_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">{signal.escalation.summary}</div>
                  <div className="mt-2 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal text-ink">
                    {signal.escalation.recommended_action}
                  </div>
                </div>
              </div>
            )}

            {!signal.sentinel && (
              <div className="py-6 text-center text-[13px] text-muted">No lifecycle data yet.</div>
            )}
          </div>
        </div>

        {signal.escalation && (
          <SheetFooter data-testid="drawer-footer" className="flex-row gap-2.5 border-t border-border px-6 py-4">
            <Button variant="outline" className="flex-1" onClick={exportJson}>
              <Download className="h-3.5 w-3.5" />
              Export
            </Button>
            <Button
              className="flex-1 bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
              onClick={acknowledge}
              disabled={acked || acking}
            >
              {acked ? (
                <>
                  <Check className="h-3.5 w-3.5" />
                  Acknowledged
                </>
              ) : acking ? (
                'Acknowledging…'
              ) : (
                <>
                  <Check className="h-3.5 w-3.5" />
                  Acknowledge
                </>
              )}
            </Button>
          </SheetFooter>
        )}
        {ackError && (
          <div
            data-testid="callout-error"
            className="mx-6 mb-4 rounded-[10px] bg-critical-tint px-3.5 py-3 text-[13px] text-critical"
          >
            {ackError}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 5: Rewrite `components/OverviewStats.tsx`**

```tsx
'use client';

import type { PipelineSignalsResponse } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import StatCard from './StatCard';
import { List, TriangleAlert, CircleCheck, Activity } from 'lucide-react';

function avgTriageSeconds(signals: PipelineSignalsResponse['signals']): number | null {
  const deltas = signals
    .filter((s) => s.sentinel && s.triage)
    .map((s) => {
      const validated = new Date(s.sentinel!.validated_at).getTime();
      const triaged = new Date(s.triage!.triaged_at).getTime();
      return (triaged - validated) / 1000;
    })
    .filter((d) => Number.isFinite(d) && d >= 0);
  if (deltas.length === 0) return null;
  return deltas.reduce((a, b) => a + b, 0) / deltas.length;
}

export default function OverviewStats({
  initialData = null,
}: {
  initialData?: PipelineSignalsResponse | null;
}) {
  const { data } = usePolling<PipelineSignalsResponse>('/pipeline/signals?hours=24', 5000, initialData);
  const signals = data?.signals ?? [];

  const open = signals.filter((s) => s.stage !== 'resolved').length;
  const resolved = signals.filter((s) => s.stage === 'resolved').length;
  const escalated = signals.filter((s) => s.stage === 'escalated');
  const p1 = escalated.filter((s) => s.severity === 'P1').length;
  const resolvedPct = signals.length > 0 ? Math.round((resolved / signals.length) * 100) : null;
  const avgTriage = avgTriageSeconds(signals);

  return (
    <div className="mb-5 grid grid-cols-4 gap-3.5 max-[760px]:grid-cols-2">
      <StatCard
        label="Open signals"
        value={signals.length > 0 ? open : '—'}
        sub="last 24h"
        icon={<List className="h-3 w-3" />}
        iconTone="violet"
      />
      <StatCard
        label="Auto-resolved"
        value={resolvedPct !== null ? `${resolvedPct}%` : '—'}
        sub="of triaged signals"
        icon={<CircleCheck className="h-3 w-3" />}
        iconTone="success"
      />
      <StatCard
        label="Escalated (P1)"
        value={p1}
        sub={`${escalated.length} escalated total`}
        icon={<TriangleAlert className="h-3 w-3" />}
        iconTone="critical"
      />
      <StatCard
        label="Avg. time to triage"
        value={avgTriage !== null ? `${avgTriage.toFixed(1)}s` : '—'}
        sub="Sentinel → Triage"
        icon={<Activity className="h-3 w-3" />}
        iconTone="teal"
      />
    </div>
  );
}
```

- [ ] **Step 6: Rewrite `app/page.tsx`**

```tsx
import { apiFetch } from '@/lib/api';
import type { PipelineSignalsResponse } from '@/lib/types';
import OverviewStats from '@/components/OverviewStats';
import QueueTable from '@/components/QueueTable';

async function getInitialSignals(): Promise<PipelineSignalsResponse | null> {
  try {
    return await apiFetch<PipelineSignalsResponse>('/api/v1/pipeline/signals?hours=24');
  } catch {
    return null;
  }
}

export default async function OverviewPage() {
  const initialData = await getInitialSignals();

  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Overview
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">Live triage across 6 feeds</div>
        </div>
      </div>

      <OverviewStats initialData={initialData} />

      <div className="mb-3 text-[12px] font-semibold text-ink">Recent signals</div>
      <QueueTable hours={24} limit={8} initialData={initialData} />
    </div>
  );
}
```

- [ ] **Step 7: Rewrite `app/queue/page.tsx`**

```tsx
import { apiFetch } from '@/lib/api';
import type { PipelineSignalsResponse } from '@/lib/types';
import QueueTable from '@/components/QueueTable';

async function getInitialSignals(): Promise<PipelineSignalsResponse | null> {
  try {
    return await apiFetch<PipelineSignalsResponse>('/api/v1/pipeline/signals?hours=24');
  } catch {
    return null;
  }
}

export default async function QueuePage() {
  const initialData = await getInitialSignals();

  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Signal queue
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">Every signal, full lifecycle, live</div>
        </div>
      </div>
      <QueueTable hours={24} showFilters initialData={initialData} />
    </div>
  );
}
```

- [ ] **Step 8: Run the targeted tests again**

Run: `npm run build && npx playwright test e2e/overview.spec.ts e2e/queue.spec.ts e2e/a11y.spec.ts -g "Overview|Signal queue|/ has no|/queue has no|drawer has no"`
Expected: PASS for all Overview, Signal queue, and the `/`, `/queue`, and drawer a11y checks. (The `/escalations`, `/status`, `/ingest` a11y checks still fail — those pages aren't converted yet; that's expected until Tasks 6–8.)

- [ ] **Step 9: Commit**

```bash
git add frontend/components/QueueTable.tsx frontend/components/SignalDrawer.tsx frontend/components/OverviewStats.tsx frontend/app/page.tsx frontend/app/queue/page.tsx frontend/e2e/overview.spec.ts frontend/e2e/queue.spec.ts frontend/e2e/a11y.spec.ts
git commit -m "Port Overview and Signal queue pages, QueueTable, and SignalDrawer to Tailwind + shadcn"
```

---

## Task 6: Port EscalationsTable and Escalations page

**Files:**
- Modify: `frontend/components/EscalationsTable.tsx`
- Modify: `frontend/app/escalations/page.tsx`
- Modify: `frontend/e2e/escalations.spec.ts`

**Interfaces:**
- Consumes: `Badge`/`severityTone`/`severityLabel` (Task 4), `SignalDrawer` (Task 5), shadcn `ToggleGroup`/`ToggleGroupItem`/`Button` (Task 2).
- Produces: `[data-testid="escalation-row"]` — used only within this task's spec.

- [ ] **Step 1: Replace `e2e/escalations.spec.ts` in full (red)**

```ts
import { test, expect } from './fixtures';

test.describe('Escalations', () => {
  test('lists the unacknowledged escalation by default and filters by priority', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.getByTestId('escalation-row')).toHaveCount(1);
    await expect(page.getByText(/High-severity repeat billing dispute/)).toBeVisible();

    await page.getByRole('button', { name: 'P2 High' }).click();
    await expect(page.getByTestId('empty-state')).toBeVisible();

    await page.getByRole('button', { name: 'All priorities' }).click();
    await expect(page.getByTestId('escalation-row')).toHaveCount(1);
  });

  test('acknowledging from the drawer updates the row and clears the sidebar badge', async ({ page }) => {
    await page.goto('/escalations');
    await expect(page.getByTestId('nav-badge')).toHaveText('1');

    await page.getByTestId('escalation-row').click();
    const drawer = page.getByTestId('signal-drawer');
    await expect(drawer).toBeVisible();

    await drawer.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(drawer.getByRole('button', { name: 'Acknowledged' })).toBeVisible();

    await drawer.getByLabel('Close').click();

    await expect(page.getByTestId('empty-state')).toBeVisible();
    await expect(page.getByTestId('nav-badge')).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Confirm it fails**

Run: `npm run build && npx playwright test e2e/escalations.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Rewrite `components/EscalationsTable.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { EscalationsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial } from '@/lib/format';
import Badge, { severityTone, severityLabel } from './Badge';
import SignalDrawer from './SignalDrawer';
import { Inbox } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Button } from '@/components/ui/button';

const PRIORITIES = [
  { value: null, label: 'All priorities' },
  { value: 'P1', label: 'P1 Critical' },
  { value: 'P2', label: 'P2 High' },
  { value: 'P3', label: 'P3 Standard' },
];

export default function EscalationsTable({
  initialData = null,
}: {
  initialData?: EscalationsResponse | null;
}) {
  const [priority, setPriority] = useState<string | null>(null);
  const [showAcked, setShowAcked] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SignalLifecycle | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const params = new URLSearchParams();
  if (priority) params.set('priority', priority);
  if (!showAcked) params.set('acknowledged', 'false');
  const isDefaultFilters = priority === null && !showAcked;
  const { data, error, loading } = usePolling<EscalationsResponse>(
    `/escalations?${params.toString()}`,
    5000,
    isDefaultFilters ? initialData : null
  );
  const briefs = data?.briefs ?? [];

  async function openSignal(signalId: string) {
    setSelectedId(signalId);
    setDrawerLoading(true);
    try {
      const res = await fetch(`/api/proxy/signals/${signalId}/lifecycle`, { cache: 'no-store' });
      if (res.ok) {
        setSelected((await res.json()) as SignalLifecycle);
      }
    } finally {
      setDrawerLoading(false);
    }
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={priority ?? 'all'}
          onValueChange={(v) => setPriority(v === 'all' || !v ? null : v)}
          className="flex-wrap justify-start gap-2"
        >
          {PRIORITIES.map((p) => (
            <ToggleGroupItem
              key={p.label}
              value={p.value ?? 'all'}
              className="rounded-full border border-border px-3 py-1.5 text-[12.5px] font-semibold text-muted data-[state=on]:bg-ink data-[state=on]:text-bg"
            >
              {p.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <div className="flex-1" />
        <Button
          type="button"
          variant="outline"
          className="rounded-full px-3 py-1.5 text-[12.5px] font-semibold"
          onClick={() => setShowAcked((v) => !v)}
        >
          {showAcked ? 'Showing all' : 'Unacknowledged only'}
        </Button>
      </div>

      <div className="overflow-hidden rounded-[13px] border border-border bg-surface shadow-[var(--shadow-card)]">
        <div className="grid grid-cols-[28px_1.4fr_110px_130px_100px] gap-3.5 border-b border-border px-4 py-2.5 text-[10px] font-bold uppercase tracking-wide text-muted">
          <div></div>
          <div>Escalation</div>
          <div>Carrier</div>
          <div>Priority</div>
          <div className="text-right">Raised</div>
        </div>

        {loading && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Loading escalations…
          </div>
        )}

        {!loading && !error && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            <Inbox className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <div>{showAcked ? 'No escalations match these filters.' : 'Nothing unacknowledged right now.'}</div>
          </div>
        )}

        {error && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Couldn&apos;t reach the gateway — {error}
          </div>
        )}

        {briefs.map((brief) => (
          <button
            key={brief.signal_id}
            type="button"
            data-testid="escalation-row"
            className={`grid w-full grid-cols-[28px_1.4fr_110px_130px_100px] items-center gap-3.5 border-b border-border px-4 py-[11px] text-left text-[12.5px] last:border-b-0 hover:bg-neutral-tint ${
              selectedId === brief.signal_id ? 'bg-gradient-to-r from-brand-tint to-jewel-violet-tint' : ''
            }`}
            onClick={() => openSignal(brief.signal_id)}
          >
            <div
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
              style={{ background: carrierColor(brief.carrier) }}
            >
              {carrierInitial(brief.carrier)}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-semibold">{brief.summary}</div>
              <div className="mt-0.5 text-[10.5px] text-muted">
                {brief.category} · <span className="font-mono">{brief.signal_id.slice(0, 8)}</span>
              </div>
            </div>
            <div>
              <Badge tone="neutral">{brief.carrier}</Badge>
            </div>
            <div>
              {brief.acknowledged ? (
                <Badge tone="success" dot>
                  Acknowledged
                </Badge>
              ) : (
                <Badge tone={severityTone(brief.severity)} dot>
                  {severityLabel(brief.severity)}
                </Badge>
              )}
            </div>
            <div className="text-right text-[12px] tabular-nums text-muted">{relativeTime(brief.escalated_at)}</div>
          </button>
        ))}
      </div>

      {selectedId && !drawerLoading && selected && (
        <SignalDrawer
          signal={selected}
          onClose={() => {
            setSelectedId(null);
            setSelected(null);
          }}
        />
      )}
    </>
  );
}
```

- [ ] **Step 4: Rewrite `app/escalations/page.tsx`**

```tsx
import { apiFetch } from '@/lib/api';
import type { EscalationsResponse } from '@/lib/types';
import EscalationsTable from '@/components/EscalationsTable';

async function getInitialEscalations(): Promise<EscalationsResponse | null> {
  try {
    return await apiFetch<EscalationsResponse>('/api/v1/escalations?acknowledged=false');
  } catch {
    return null;
  }
}

export default async function EscalationsPage() {
  const initialData = await getInitialEscalations();

  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Escalations
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">Everything routed to a human, live</div>
        </div>
      </div>
      <EscalationsTable initialData={initialData} />
    </div>
  );
}
```

- [ ] **Step 5: Run the tests again**

Run: `npm run build && npx playwright test e2e/escalations.spec.ts e2e/a11y.spec.ts -g "Escalations|/escalations has no"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/EscalationsTable.tsx frontend/app/escalations/page.tsx frontend/e2e/escalations.spec.ts
git commit -m "Port Escalations page and EscalationsTable to Tailwind + shadcn"
```

---

## Task 7: Port StatusPanel and Adapter status page

**Files:**
- Modify: `frontend/components/StatusPanel.tsx`
- Modify: `frontend/app/status/page.tsx`
- Modify: `frontend/e2e/status.spec.ts`

**Interfaces:**
- Consumes: `StatCard` (Task 4).
- Produces: `[data-testid="status-card"]`, `[data-testid="status-card-name"]`, `[data-testid="status-dot"]` with a `data-status="healthy"|"degraded"|"down"` attribute — used only within this task's spec.

- [ ] **Step 1: Replace `e2e/status.spec.ts` in full (red)**

```ts
import { test, expect } from './fixtures';

test.describe('Adapter status', () => {
  test('shows orchestrator stats, all 6 adapters, and all 6 circuit breakers', async ({ page }) => {
    await page.goto('/status');

    await expect(page.getByText('Running', { exact: true })).toBeVisible();
    await expect(page.getByText('escalations waiting')).toBeVisible();

    const adapterNames = ['X', 'Reddit', 'Google Play', 'App Store', 'Trustpilot', 'Quora'];
    for (const name of adapterNames) {
      await expect(page.getByTestId('status-card-name').filter({ hasText: name }).first()).toBeVisible();
    }

    await expect(page.getByTestId('status-card')).toHaveCount(12); // 6 adapters + 6 breakers
    await expect(page.locator('[data-testid="status-dot"][data-status="down"]')).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Confirm it fails**

Run: `npm run build && npx playwright test e2e/status.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Rewrite `components/StatusPanel.tsx`**

```tsx
'use client';

import type { AdapterStatusResponse, OrchestratorStatus } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, sourceLabel } from '@/lib/format';
import StatCard from './StatCard';
import { Activity, ListTree, Gauge, Radio } from 'lucide-react';

type StatusKey = 'healthy' | 'degraded' | 'down';

const DOT_CLASSES: Record<StatusKey, string> = {
  healthy: 'bg-success',
  degraded: 'bg-warning',
  down: 'bg-critical',
};

function statusKey(status: string): StatusKey {
  if (status === 'HEALTHY') return 'healthy';
  if (status === 'DEGRADED') return 'degraded';
  return 'down';
}

export default function StatusPanel({
  initialAdapters = null,
  initialOrchestrator = null,
}: {
  initialAdapters?: AdapterStatusResponse | null;
  initialOrchestrator?: OrchestratorStatus | null;
}) {
  const adapters = usePolling<AdapterStatusResponse>('/adapters/status', 10000, initialAdapters);
  const orchestrator = usePolling<OrchestratorStatus>('/orchestrator/status', 10000, initialOrchestrator);

  const adapterEntries = Object.entries(adapters.data?.adapters ?? {});
  const breakerEntries = Object.entries(orchestrator.data?.adapter_circuit_breakers ?? {});

  return (
    <>
      <div className="mb-5 grid grid-cols-4 gap-3.5 max-[760px]:grid-cols-2">
        <StatCard
          label="Orchestrator"
          value={orchestrator.data ? (orchestrator.data.running ? 'Running' : 'Stopped') : '—'}
          sub={orchestrator.data?.global_circuit_open ? 'Global circuit open' : 'All systems normal'}
          icon={<Activity className="h-3 w-3" />}
          iconTone="violet"
        />
        <StatCard
          label="Unacknowledged queue"
          value={orchestrator.data?.queue_depth_unacknowledged ?? '—'}
          sub="escalations waiting"
          icon={<ListTree className="h-3 w-3" />}
          iconTone="critical"
        />
        <StatCard
          label="X API usage"
          value={orchestrator.data ? orchestrator.data.x_monthly_reads.toLocaleString() : '—'}
          sub={`of ${orchestrator.data?.x_monthly_cap.toLocaleString() ?? '—'} monthly reads`}
          icon={<Gauge className="h-3 w-3" />}
          iconTone="teal"
        />
        <StatCard
          label="Adapters reporting"
          value={adapterEntries.length || '—'}
          sub="of 6 configured"
          icon={<Radio className="h-3 w-3" />}
          iconTone="success"
        />
      </div>

      <div className="mb-3 text-[12px] font-semibold text-ink">Feed adapters</div>

      {adapterEntries.length === 0 ? (
        <div data-testid="empty-state" className="p-12 text-center text-muted">
          {adapters.loading ? 'Loading adapter status…' : 'No adapter health reported yet.'}
        </div>
      ) : (
        <div className="mb-6 grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
          {adapterEntries.map(([name, health]) => {
            const key = statusKey(health.status);
            return (
              <div
                key={name}
                data-testid="status-card"
                className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span data-testid="status-card-name" className="text-[13.5px] font-bold capitalize">
                    {sourceLabel(name)}
                  </span>
                  <span
                    data-testid="status-dot"
                    data-status={key}
                    title={health.status}
                    className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASSES[key]}`}
                  />
                </div>
                <div className="text-[11.5px] text-muted">
                  {health.last_successful_fetch
                    ? `Last fetch ${relativeTime(health.last_successful_fetch)}`
                    : 'Never fetched'}
                </div>
                {health.consecutive_errors > 0 && (
                  <div className="mt-0.5 text-[11.5px] text-critical">
                    {health.consecutive_errors} consecutive error{health.consecutive_errors === 1 ? '' : 's'}
                  </div>
                )}
                {health.monthly_cap_limit !== null && health.monthly_cap_used !== null && (
                  <div className="mt-0.5 text-[11.5px] text-muted">
                    {health.monthly_cap_used.toLocaleString()} / {health.monthly_cap_limit.toLocaleString()} monthly
                    cap
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mb-3 text-[12px] font-semibold text-ink">Circuit breakers</div>

      {breakerEntries.length === 0 ? (
        <div data-testid="empty-state" className="p-12 text-center text-muted">
          {orchestrator.loading ? 'Loading circuit breaker state…' : 'No circuit breaker data yet.'}
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
          {breakerEntries.map(([name, breaker]) => {
            const key: StatusKey = breaker.state === 'closed' ? 'healthy' : breaker.state === 'half-open' ? 'degraded' : 'down';
            return (
              <div
                key={name}
                data-testid="status-card"
                className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span data-testid="status-card-name" className="text-[13.5px] font-bold capitalize">
                    {sourceLabel(name)}
                  </span>
                  <span
                    data-testid="status-dot"
                    data-status={key}
                    title={breaker.state}
                    className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASSES[key]}`}
                  />
                </div>
                <div className="text-[11.5px] text-muted">
                  {breaker.state === 'closed'
                    ? 'Closed — passing traffic'
                    : breaker.state === 'half-open'
                      ? 'Half-open — testing recovery'
                      : `Open since ${breaker.opened_at ? relativeTime(breaker.opened_at) : 'unknown'}`}
                </div>
                {breaker.consecutive_errors > 0 && (
                  <div className="mt-0.5 text-[11.5px] text-muted">
                    {breaker.consecutive_errors} consecutive error{breaker.consecutive_errors === 1 ? '' : 's'}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 4: Rewrite `app/status/page.tsx`**

```tsx
import { apiFetch } from '@/lib/api';
import type { AdapterStatusResponse, OrchestratorStatus } from '@/lib/types';
import StatusPanel from '@/components/StatusPanel';

async function getInitialStatus() {
  try {
    const [adapters, orchestrator] = await Promise.all([
      apiFetch<AdapterStatusResponse>('/api/v1/adapters/status'),
      apiFetch<OrchestratorStatus>('/api/v1/orchestrator/status'),
    ]);
    return { adapters, orchestrator };
  } catch {
    return { adapters: null, orchestrator: null };
  }
}

export default async function StatusPage() {
  const { adapters, orchestrator } = await getInitialStatus();

  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Adapter status
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">Feed health, circuit breakers, and orchestrator state</div>
        </div>
      </div>
      <StatusPanel initialAdapters={adapters} initialOrchestrator={orchestrator} />
    </div>
  );
}
```

- [ ] **Step 5: Run the tests again**

Run: `npm run build && npx playwright test e2e/status.spec.ts e2e/a11y.spec.ts -g "Adapter status|/status has no"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/StatusPanel.tsx frontend/app/status/page.tsx frontend/e2e/status.spec.ts
git commit -m "Port Adapter status page and StatusPanel to Tailwind + shadcn"
```

---

## Task 8: Port IngestForm and Send-test-signal page; remove the old icon set

**Files:**
- Modify: `frontend/components/IngestForm.tsx`
- Modify: `frontend/app/ingest/page.tsx`
- Modify: `frontend/e2e/ingest.spec.ts`
- Delete: `frontend/components/icons.tsx`

**Interfaces:**
- Consumes: shadcn `Button`/`Input`/`Textarea`/`Label`/`Select*` (Task 2).
- Produces: `[data-testid="callout-success"]`, `[data-testid="callout-error"]` — consumed only by this task's spec (`SignalDrawer`'s own error callout, added in Task 5, already uses `callout-error` independently — no shared coupling since neither reads the other's testid).

Note: the spec's component-mapping table (§5) lists shadcn's `Form` as an option for form fields. `Form` is a `react-hook-form` + `zod` wrapper — since this form has no schema validation needs beyond "content is non-empty" (already handled by the existing `disabled={submitting || !content}` check), adding `react-hook-form`/`zod` would be a new dependency with no behavior it's needed for. This task uses `Input`/`Textarea`/`Select`/`Label`/`Button` directly with the existing `useState` logic instead, per the spec's own YAGNI framing (§10 — this kind of substitution doesn't change tokens or test strategy, so it doesn't need re-confirmation).

- [ ] **Step 1: Replace `e2e/ingest.spec.ts` in full (red)**

```ts
import { test, expect } from './fixtures';

test.describe('Send test signal', () => {
  test('filling an example and submitting shows a success callout with a link to the queue', async ({
    page,
  }) => {
    await page.goto('/ingest');

    await page.getByRole('button', { name: /Billing dispute \(likely escalates\)/ }).click();
    await expect(page.getByLabel('What they said')).toHaveValue(/Verizon overcharged me AGAIN/);

    await page.getByRole('button', { name: 'Send to the pipeline' }).click();

    const success = page.getByTestId('callout-success');
    await expect(success).toBeVisible();
    await expect(success).toContainText('Queued as');
    await expect(success.getByRole('link', { name: 'signal queue' })).toHaveAttribute('href', '/queue');
  });

  test('submit is disabled until content is filled', async ({ page }) => {
    await page.goto('/ingest');
    await expect(page.getByRole('button', { name: 'Send to the pipeline' })).toBeDisabled();

    await page.getByLabel('What they said').fill('Something is broken.');
    await expect(page.getByRole('button', { name: 'Send to the pipeline' })).toBeEnabled();
  });
});
```

- [ ] **Step 2: Confirm it fails**

Run: `npm run build && npx playwright test e2e/ingest.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Rewrite `components/IngestForm.tsx`**

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { IngestResponse, SignalSource } from '@/lib/types';
import { Check, TriangleAlert, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const SOURCES: { value: SignalSource; label: string }[] = [
  { value: 'x', label: 'X (Twitter)' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'app_store', label: 'App Store review' },
  { value: 'google_play', label: 'Google Play review' },
  { value: 'trustpilot', label: 'Trustpilot review' },
  { value: 'quora', label: 'Quora' },
];

const CARRIERS = [
  { value: '', label: 'Let Sentinel detect it' },
  { value: 'verizon', label: 'Verizon' },
  { value: 'tmobile', label: 'T-Mobile' },
  { value: 'att', label: 'AT&T' },
];

const EXAMPLES = [
  {
    label: 'Billing dispute (likely escalates)',
    source: 'x' as SignalSource,
    author: 'frustrated_customer22',
    content:
      "Verizon overcharged me AGAIN this month, third time in a row. I want a refund or I'm switching carriers.",
    carrier: 'verizon',
  },
  {
    label: 'eSIM activation issue (likely auto-resolves)',
    source: 'app_store' as SignalSource,
    author: 'newuser2026',
    content: "eSIM won't activate on the new plan, tried scanning the QR code 3 times. Please help.",
    carrier: 'tmobile',
  },
  {
    label: 'Positive mention (should stay low priority)',
    source: 'trustpilot' as SignalSource,
    author: 'happy_switcher',
    content: 'Switched to AT&T last week and the support call to set up my new SIM was fast and painless.',
    carrier: 'att',
  },
];

export default function IngestForm() {
  const [source, setSource] = useState<SignalSource>('x');
  const [author, setAuthor] = useState('');
  const [content, setContent] = useState('');
  const [carrier, setCarrier] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function fillExample(example: (typeof EXAMPLES)[number]) {
    setSource(example.source);
    setAuthor(example.author);
    setContent(example.content);
    setCarrier(example.carrier);
    setResult(null);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    const now = new Date().toISOString();
    const sourceId = `demo-${Date.now()}`;

    try {
      const res = await fetch('/api/proxy/signals/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source,
          source_id: sourceId,
          author_handle: author || 'anonymous_demo_user',
          content,
          url: `https://example.com/${source}/${sourceId}`,
          posted_at: now,
          carrier_hint: carrier || undefined,
        }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setResult((await res.json()) as IngestResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingest failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[560px] rounded-2xl border border-border bg-surface p-6 shadow-[var(--shadow-card)]">
      <div className="mb-4">
        <Label className="mb-2 block text-[12.5px] font-bold">Try an example</Label>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <Button
              key={ex.label}
              type="button"
              variant="outline"
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold"
              onClick={() => fillExample(ex)}
            >
              {ex.label}
            </Button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3.5 max-[520px]:grid-cols-1">
          <div>
            <Label htmlFor="source" className="mb-1.5 block text-[12.5px] font-bold">
              Feed source
            </Label>
            <Select value={source} onValueChange={(v) => setSource(v as SignalSource)}>
              <SelectTrigger id="source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="carrier" className="mb-1.5 block text-[12.5px] font-bold">
              Carrier hint
            </Label>
            <Select value={carrier || 'auto'} onValueChange={(v) => setCarrier(v === 'auto' ? '' : v)}>
              <SelectTrigger id="carrier" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CARRIERS.map((c) => (
                  <SelectItem key={c.value || 'auto'} value={c.value || 'auto'}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label htmlFor="author" className="mb-1.5 block text-[12.5px] font-bold">
            Author handle
          </Label>
          <Input
            id="author"
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="anonymous_demo_user"
          />
          <div className="mt-1.5 text-[11.5px] text-muted">
            Hashed with SHA-256 before storage — never kept in the clear.
          </div>
        </div>

        <div>
          <Label htmlFor="content" className="mb-1.5 block text-[12.5px] font-bold">
            What they said
          </Label>
          <Textarea
            id="content"
            required
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write a complaint (or compliment) as if it were a real post…"
            className="min-h-[80px]"
          />
        </div>

        {error && (
          <div
            data-testid="callout-error"
            className="flex items-start gap-2 rounded-[10px] bg-critical-tint px-3.5 py-3 text-[12.5px] text-critical"
          >
            <TriangleAlert className="mt-0.5 h-[15px] w-[15px] shrink-0" />
            <span>Couldn&apos;t send that signal — {error}</span>
          </div>
        )}

        {result && (
          <div
            data-testid="callout-success"
            className="flex items-start gap-2 rounded-[10px] bg-success-tint px-3.5 py-3 text-[12.5px] text-success"
          >
            <Check className="mt-0.5 h-[15px] w-[15px] shrink-0" />
            <span>
              Queued as <span className="font-mono">{result.signal_id.slice(0, 8)}</span>. It&apos;s moving through
              Sentinel → Triage now — check the{' '}
              <Link href="/queue" className="underline">
                signal queue
              </Link>{' '}
              in a few seconds to watch it land.
            </span>
          </div>
        )}

        <Button
          type="submit"
          disabled={submitting || !content}
          className="bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
        >
          {submitting ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              Sending…
            </>
          ) : (
            <>
              <Send className="h-[15px] w-[15px]" />
              Send to the pipeline
            </>
          )}
        </Button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite `app/ingest/page.tsx`**

```tsx
import IngestForm from '@/components/IngestForm';

export default function IngestPage() {
  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Send test signal
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">
            Inject a signal and watch it move through the real pipeline
          </div>
        </div>
      </div>
      <IngestForm />
    </div>
  );
}
```

- [ ] **Step 5: Confirm no component still imports the old icon set, then delete it**

Run: `grep -rn "from './icons'" frontend/components frontend/app`
Expected: no output (AppShell, AgentTrail, QueueTable, SignalDrawer, EscalationsTable, and IngestForm were all converted to `lucide-react` in Tasks 3–8; `StatusPanel` never imported it).

```bash
rm frontend/components/icons.tsx
```

- [ ] **Step 6: Run the full verification suite**

Run: `cd frontend && npm run verify`
Expected: lint, typecheck, vitest, build, and the full Playwright suite (all 6 spec files) all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/IngestForm.tsx frontend/app/ingest/page.tsx frontend/e2e/ingest.spec.ts
git rm frontend/components/icons.tsx
git commit -m "Port Send-test-signal page and IngestForm to Tailwind + shadcn; remove the hand-rolled icon set"
```

---

## Task 9: Final polish and sign-off

**Files:**
- Modify: `frontend/app/layout.tsx`

**Interfaces:** None — this task only updates a metadata value and re-runs verification.

- [ ] **Step 1: Update the browser theme-color to the new brand hex**

In `frontend/app/layout.tsx`, change:
```ts
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#4F46E5',
};
```
to:
```ts
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#2F6FED',
};
```

- [ ] **Step 2: Run full verification one more time**

Run: `cd frontend && npm run verify`
Expected: all green (lint, typecheck, vitest, build, full Playwright suite).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/layout.tsx
git commit -m "Update browser theme-color to the new brand accent"
```

- [ ] **Step 4: Manual review**

Run `npm run dev` inside `frontend/`, open the app, and walk all 5 pages plus the drawer in both light and dark OS appearance settings. This is the checkpoint from spec §8 step 7 — Vinoth reviews the running app before the SignalHarvest follow-up spec is opened.
