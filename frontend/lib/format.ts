export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

const CARRIER_COLORS: Record<string, string> = {
  verizon: '#DC2626',
  tmobile: '#E60000',
  att: '#00A8E0',
};

export function carrierColor(carrier: string | null | undefined): string {
  if (!carrier) return '#6B7280';
  return CARRIER_COLORS[carrier.toLowerCase().replace(/[^a-z]/g, '')] ?? '#6B7280';
}

export function carrierInitial(carrier: string | null | undefined): string {
  if (!carrier) return '?';
  return carrier.charAt(0).toUpperCase();
}

const SOURCE_LABELS: Record<string, string> = {
  x: 'X',
  reddit: 'Reddit',
  google_play: 'Google Play',
  app_store: 'App Store',
  trustpilot: 'Trustpilot',
  quora: 'Quora',
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
