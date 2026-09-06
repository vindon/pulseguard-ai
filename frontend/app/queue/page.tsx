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
