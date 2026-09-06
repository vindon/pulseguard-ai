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
