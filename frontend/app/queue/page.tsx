import QueueTable from '@/components/QueueTable';

export default function QueuePage() {
  return (
    <div className="content">
      <div className="content-head">
        <div>
          <div className="page-title display">Signal queue</div>
          <div className="page-sub">Every signal, full lifecycle, live</div>
        </div>
      </div>
      <QueueTable hours={24} showFilters />
    </div>
  );
}
