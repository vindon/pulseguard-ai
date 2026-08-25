import { apiFetch } from '@/lib/api';
import type { PipelineSignalsResponse } from '@/lib/types';
import OverviewStats from '@/components/OverviewStats';
import QueueTable from '@/components/QueueTable';

async function getInitialSignals(): Promise<PipelineSignalsResponse | null> {
  try {
    return await apiFetch<PipelineSignalsResponse>('/api/v1/pipeline/signals?hours=24');
  } catch {
    // The client-side poll in QueueTable/OverviewStats will retry and
    // surface its own error state — a gateway hiccup on first render
    // shouldn't take down the whole page.
    return null;
  }
}

export default async function OverviewPage() {
  const initialData = await getInitialSignals();

  return (
    <div className="content">
      <div className="content-head">
        <div>
          <h1 className="page-title display">Overview</h1>
          <div className="page-sub">Live triage across 6 feeds</div>
        </div>
      </div>

      <OverviewStats initialData={initialData} />

      <div className="content-head" style={{ marginBottom: 12 }}>
        <div className="page-sub" style={{ marginTop: 0, fontWeight: 600, color: 'var(--ink)' }}>
          Recent signals
        </div>
      </div>
      <QueueTable hours={24} limit={8} initialData={initialData} />
    </div>
  );
}
