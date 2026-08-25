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
    <div className="content">
      <div className="content-head">
        <div>
          <h1 className="page-title display">Signal queue</h1>
          <div className="page-sub">Every signal, full lifecycle, live</div>
        </div>
      </div>
      <QueueTable hours={24} showFilters initialData={initialData} />
    </div>
  );
}
