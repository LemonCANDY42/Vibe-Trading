# Upstream Sync Policy

This policy is a specialized companion to
`wiki/docs/kenny/MAINTENANCE_PARADIGM.md`. Use the maintenance paradigm for the
overall work sequence, then this document for branch and upstream-sync details.

## Branch Roles

This fork keeps upstream and Kenny-specific work separated:

- `main`: tracks `HKUDS/Vibe-Trading` as closely as possible.
- `feat/moirix-event-graph-extension-v0`: current Moirix extension development
  branch.
- future `kenny/main`: intended personal daily-use branch after the V0
  integration is reviewed and merged locally.

Do not use `main` for broad personal customizations.

## Remotes

Expected remotes:

```bash
origin    LemonCANDY42/Vibe-Trading-Kenny
upstream  HKUDS/Vibe-Trading
```

Check with:

```bash
git remote -v
```

## Sync Flow

For a clean fast-forward of the fork baseline:

```bash
git checkout main
git fetch upstream
git merge --ff-only upstream/main
git push origin main
```

For a Kenny integration branch:

```bash
git checkout feat/moirix-event-graph-extension-v0
git fetch upstream
git merge upstream/main
git diff --check
```

Run targeted tests before pushing a Kenny branch:

```bash
uv run --extra dev python -m pytest agent/tests/test_moirix_adapter_tools.py -q
uv run --extra dev python -m pytest \
  agent/tests/test_swarm_presets_packaging.py \
  agent/tests/test_swarm_preset_inspect.py \
  agent/tests/test_skills.py -q
```

## Custom-Code Isolation

Prefer new files under these paths:

```text
wiki/docs/kenny/
wiki/docs/moirix/
agent/src/tools/_moirix_adapter.py
agent/src/tools/moirix_*.py
agent/src/skills/moirix-*/
agent/src/swarm/presets/moirix_*.yaml
agent/tests/test_moirix_*.py
```

Keep edits to upstream-heavy files small and documented. In this branch those
touch points are expected to be limited to registry/count/routing surfaces such
as:

```text
README.md
agent/src/agent/context.py
agent/tests/test_swarm_presets_packaging.py
wiki/docs/content.js
```

## Conflict Policy

When upstream changes conflict with Kenny-specific integration:

- preserve Vibe core behavior first;
- keep Moirix optional and fail-closed;
- avoid moving Moirix code into generic loaders or broker surfaces;
- update `wiki/docs/kenny/CURRENT_GOAL.md` if the implementation scope changes;
- rerun the targeted Moirix and skill/swarm tests before considering the sync
  healthy.

## Authority Boundary

Upstream sync must not weaken these rules:

- no broker submit path is added by the Moirix extension;
- no real-money authority claim is made;
- missing Moirix returns `unavailable` rather than success;
- blocked Moirix coverage is shown as blocked rather than replaced with fake
  PIT evidence;
- ad-hoc web fallback is labelled as ad-hoc web research.
