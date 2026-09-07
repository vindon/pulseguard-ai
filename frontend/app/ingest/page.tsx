import IngestForm from '@/components/IngestForm';

export default function IngestPage() {
  return (
    <div className="p-7 pb-12">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 data-testid="page-title" className="font-display text-[20px] font-extrabold tracking-tight">
            Send test signal
          </h1>
          <div className="mt-0.5 text-[12px] text-muted">
            Inject a signal and watch it move through the real pipeline
          </div>
        </div>
      </div>
      <IngestForm />
    </div>
  );
}
