'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { EscalationsResponse } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import {
  OverviewIcon,
  QueueIcon,
  AlertIcon,
  PulseIcon,
  SendIcon,
  SearchIcon,
  BellIcon,
  ShieldIcon,
} from './icons';

const NAV_ITEMS = [
  { href: '/', label: 'Overview', icon: OverviewIcon },
  { href: '/queue', label: 'Signal queue', icon: QueueIcon },
  { href: '/escalations', label: 'Escalations', icon: AlertIcon, badgeKey: 'escalations' as const },
  { href: '/status', label: 'Adapter status', icon: PulseIcon },
  { href: '/ingest', label: 'Send test signal', icon: SendIcon },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data } = usePolling<EscalationsResponse>('/escalations?acknowledged=false', 20000);
  const unacknowledged = data?.count ?? 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">
            <ShieldIcon width={18} height={18} />
          </div>
          <div>
            <div className="sidebar-brand-name">PulseGuard</div>
            <div className="sidebar-brand-tag">Telecom CX triage</div>
          </div>
        </div>

        <div className="nav-section-label">Workspace</div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className={`nav-item${active ? ' active' : ''}`}>
              <Icon />
              <span className="nav-label">{item.label}</span>
              {item.badgeKey === 'escalations' && unacknowledged > 0 && (
                <span className="nav-badge">{unacknowledged}</span>
              )}
            </Link>
          );
        })}

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="avatar">VN</div>
            <div>
              <div className="user-name">Vinoth N.</div>
              <div className="user-role">CX Operations</div>
            </div>
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="search">
            <SearchIcon />
            Search signals, carriers, categories…
          </div>
          <div className="topbar-actions">
            <div className="icon-btn">
              <BellIcon />
              {unacknowledged > 0 && <span className="dot-alert" />}
            </div>
          </div>
        </div>

        {children}
      </div>
    </div>
  );
}
