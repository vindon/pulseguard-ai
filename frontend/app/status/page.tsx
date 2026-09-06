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
