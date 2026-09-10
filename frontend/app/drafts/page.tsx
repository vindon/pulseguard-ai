import DraftQueue from '@/components/DraftQueue';

export default function DraftsPage() {
  return (
    <div className="p-6">
      <div data-testid="page-title" className="font-display text-[23px] font-extrabold">
        Drafts
      </div>
      <div className="mt-1 text-[13px] text-muted">Every drafted reply waits here until you approve it.</div>
      <div className="mt-5">
        <DraftQueue />
      </div>
    </div>
  );
}
