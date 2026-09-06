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
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Escalations
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">Everything routed to a human, live</div>
        </div>
      </div>
      <EscalationsTable initialData={initialData} />
    </div>
  );
}
