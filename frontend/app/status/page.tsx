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
    <div className="content">
      <div className="content-head">
        <div>
          <h1 className="page-title display">Adapter status</h1>
          <div className="page-sub">Feed health, circuit breakers, and orchestrator state</div>
        </div>
      </div>
      <StatusPanel initialAdapters={adapters} initialOrchestrator={orchestrator} />
    </div>
  );
}
