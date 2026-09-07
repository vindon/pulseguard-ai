import { Check, TriangleAlert, Circle } from 'lucide-react';
import type { SignalLifecycle } from '@/lib/types';

type NodeState = 'done' | 'active' | 'escalated' | 'pending';

const NODE_CLASSES: Record<NodeState, string> = {
  done: 'border-success bg-success text-white',
  active: 'border-brand bg-brand text-white agent-pulse',
  escalated: 'border-critical bg-critical text-white',
  pending: 'border-border bg-surface text-muted',
};

function nodeIcon(state: NodeState) {
  if (state === 'done') return <Check className="h-2.5 w-2.5" />;
  if (state === 'escalated') return <TriangleAlert className="h-2.5 w-2.5" strokeWidth={2.4} />;
  return <Circle className="h-2.5 w-2.5" />;
}

function deriveStates(signal: SignalLifecycle): [NodeState, NodeState, NodeState] {
  const sentinelDone = Boolean(signal.sentinel);
  const triageDone = Boolean(signal.triage);
  const finalDone = Boolean(signal.resolver) || Boolean(signal.escalation);
  const finalEscalated = Boolean(signal.escalation);

  const sentinel: NodeState = sentinelDone ? 'done' : 'active';
  const triage: NodeState = triageDone ? 'done' : sentinelDone ? 'active' : 'pending';
  const final: NodeState = finalDone
    ? finalEscalated
      ? 'escalated'
      : 'done'
    : triageDone
      ? 'active'
      : 'pending';

  return [sentinel, triage, final];
}

export default function AgentTrail({ signal }: { signal: SignalLifecycle }) {
  const [sentinel, triage, final] = deriveStates(signal);
  return (
    <div
      className="flex items-center"
      title={`Sentinel: ${sentinel} · Triage: ${triage} · Resolver/Escalation: ${final}`}
    >
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[sentinel]}`}
      >
        {nodeIcon(sentinel)}
      </div>
      <div className={`h-0.5 w-3 shrink-0 ${sentinel === 'done' ? 'bg-success' : 'bg-border'}`} />
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[triage]}`}
      >
        {nodeIcon(triage)}
      </div>
      <div className={`h-0.5 w-3 shrink-0 ${triage === 'done' ? 'bg-success' : 'bg-border'}`} />
      <div
        className={`relative z-10 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full border-2 ${NODE_CLASSES[final]}`}
      >
        {nodeIcon(final)}
      </div>
    </div>
  );
}
