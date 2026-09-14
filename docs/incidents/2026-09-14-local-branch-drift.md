# Incident: local `master` 36 commits behind `origin/master`

**Date:** 2026-09-14
**Severity:** Low — no data loss, no prod impact, but a real gap for a few days
**Status:** Resolved

## Summary

The primary local checkout of `pulseguard-ai` (`~/project/pulseguard-ai`, branch
`master`) sat 36 commits behind `origin/master` for four days. All of Phase 0
(drafts review queue, budget guard, eval CI gate, structured decision logger, X
publisher, prompt caching) had already been built and merged to `origin/master`
via a linked worktree — the merge itself was clean and real. The primary
checkout just never pulled it.

## What happened

- Phase 0 was developed in a linked worktree at
  `.claude/worktrees/pulseguard-phase0-copilot-loop`, on branch
  `worktree-pulseguard-phase0-copilot-loop`. That's the right way to isolate a
  big feature from the main tree.
- That branch was pushed and merged into `origin/master` on GitHub — 36
  commits, 2026-09-10 through 2026-09-11.
- The main working copy, also on `master`, was never `git pull`ed afterward.
  It stayed pinned at the pre-Phase-0 commit (`e5003e7`, 2026-09-07).
- Project status was recorded elsewhere as "Phase 0 done, merged to master" —
  which was true of the remote, but that phrasing doesn't distinguish "merged
  upstream" from "the directory you're about to work in has it."
- Found on 2026-09-14 during a routine status check: `git log` on the local
  clone showed only the pre-Phase-0 commit despite the merge having happened
  days earlier. `git status` had been saying "behind by 36 commits" the whole
  time — it just hadn't been read.

## Why it happened

1. **A worktree branch merging upstream doesn't move any other checkout's
   branch pointer.** Using a worktree for Phase 0 was correct practice; the
   gap is that nothing automatically fast-forwards the primary checkout once
   that work lands on the shared branch.
2. **No pull step after the merge.** The push/merge to `origin/master`
   happened from the worktree; nobody ran `git pull` back in the primary
   directory afterward.
3. **Status was tracked by narrative, not verified against the checkout.**
   "Merged to master" got recorded as done without re-running `git log` /
   `git status` in the actual directory that statement referred to.

## The fix

1. `git stash` the one uncommitted local edit (`CLAUDE.md`) so the pull
   wouldn't be blocked.
2. `git pull --ff-only` — clean fast-forward, 36 commits, zero conflicts
   (the local tree had no divergent commits of its own, only an uncommitted
   file).
3. `git stash pop` produced a real conflict in `CLAUDE.md`: upstream had
   *also* edited the same "Non-negotiables" section (a clarifying note about
   the Approve & Send endpoint) while the local stash added "Why" rationale
   lines to those same rules. Resolved by hand, keeping both — the upstream
   clarification and the local rationale merged into one block — then staged
   and dropped the stash.

## Prevention

- **Merging a worktree branch upstream doesn't update sibling checkouts.**
  Every other checkout of that branch — the main directory, other worktrees,
  other machines — needs its own explicit `git pull`.
- **Treat "merged" as a remote-only fact until verified locally.** Before
  recording work as done/merged, run `git fetch && git status` against the
  actual directory being referenced, not just trust the last action taken in
  whatever worktree did the work.
- **Pull the primary checkout right after finishing worktree-based work**,
  rather than letting it drift — the longer it sits behind, the more likely a
  later local edit collides with something that already shipped (as happened
  here with `CLAUDE.md`).
- Generalizes past git: any system with multiple views of shared state
  (checkouts, replicas, cached dashboards, cloned configs) needs an explicit
  sync-and-verify step after a write. A write in one view is not a write
  everywhere.
