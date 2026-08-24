import OverviewStats from '@/components/OverviewStats';
import QueueTable from '@/components/QueueTable';

export default function OverviewPage() {
  return (
    <div className="content">
      <div className="content-head">
        <div>
          <div className="page-title display">Overview</div>
          <div className="page-sub">Live triage across 6 feeds</div>
        </div>
      </div>

      <OverviewStats />

      <div className="content-head" style={{ marginBottom: 12 }}>
        <div className="page-sub" style={{ marginTop: 0, fontWeight: 600, color: 'var(--ink)' }}>
          Recent signals
        </div>
      </div>
      <QueueTable hours={24} limit={8} />
    </div>
  );
}
