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
