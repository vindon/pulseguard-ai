import type { ReactNode } from 'react';

type IconTone = 'violet' | 'critical' | 'success' | 'teal';
type SubTone = 'muted' | 'success' | 'critical';

const ICON_TONE_CLASSES: Record<IconTone, string> = {
  violet: 'bg-jewel-violet-tint text-jewel-violet',
  critical: 'bg-critical-tint text-critical',
  success: 'bg-success-tint text-success',
  teal: 'bg-jewel-teal-tint text-jewel-teal',
};

const SUB_TONE_CLASSES: Record<SubTone, string> = {
  muted: 'text-muted',
  success: 'text-success',
  critical: 'text-critical',
};

export default function StatCard({
  label,
  value,
  sub,
  icon,
  iconTone = 'violet',
  subTone = 'muted',
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  iconTone?: IconTone;
  subTone?: SubTone;
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
      {sub && <div className={`mt-0.5 text-[10.5px] font-semibold ${SUB_TONE_CLASSES[subTone]}`}>{sub}</div>}
    </div>
  );
}
