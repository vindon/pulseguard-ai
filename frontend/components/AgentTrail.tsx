import type { SignalLifecycle } from '@/lib/types';
import { CheckIcon, ClockIcon, AlertTriangleIcon } from './icons';

type NodeState = 'done' | 'active' | 'escalated' | 'pending';

function nodeIcon(state: NodeState) {
  if (state === 'done') return <CheckIcon width={10} height={10} />;
  if (state === 'escalated') return <AlertTriangleIcon width={10} height={10} strokeWidth={2.4} />;
  return <ClockIcon width={10} height={10} />;
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
    <div className="agent-trail" title={`Sentinel: ${sentinel} · Triage: ${triage} · Resolver/Escalation: ${final}`}>
      <div className={`agent-node -${sentinel}`}>{nodeIcon(sentinel)}</div>
      <div className={`agent-connector${sentinel === 'done' ? ' -done' : ''}`} />
      <div className={`agent-node -${triage}`}>{nodeIcon(triage)}</div>
      <div className={`agent-connector${triage === 'done' ? ' -done' : ''}`} />
      <div className={`agent-node -${final}`}>{nodeIcon(final)}</div>
    </div>
  );
}
