import { apiFetch } from '@/lib/api';
import type { EscalationsResponse } from '@/lib/types';
import EscalationsTable from '@/components/EscalationsTable';

async function getInitialEscalations(): Promise<EscalationsResponse | null> {
  try {
    return await apiFetch<EscalationsResponse>('/api/v1/escalations?acknowledged=false');
  } catch {
    return null;
  }
}

export default async function EscalationsPage() {
  const initialData = await getInitialEscalations();

  return (
    <div className="content">
      <div className="content-head">
        <div>
          <h1 className="page-title display">Escalations</h1>
          <div className="page-sub">Everything routed to a human, live</div>
        </div>
      </div>
      <EscalationsTable initialData={initialData} />
    </div>
  );
}
