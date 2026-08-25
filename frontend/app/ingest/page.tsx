import IngestForm from '@/components/IngestForm';

export default function IngestPage() {
  return (
    <div className="content">
      <div className="content-head">
        <div>
          <h1 className="page-title display">Send test signal</h1>
          <div className="page-sub">Inject a signal and watch it move through the real pipeline</div>
        </div>
      </div>
      <IngestForm />
    </div>
  );
}
