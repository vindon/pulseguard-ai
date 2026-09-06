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
              <DropdownMenuTrigger
                aria-label="Notifications"
                className="relative flex h-[30px] w-[30px] items-center justify-center rounded-lg text-muted hover:bg-neutral-tint"
              >
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
