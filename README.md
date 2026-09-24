# Builder execution smoke check

Model-free verification of shared Op execution and mapped Cog handoffs. This is not the cog-builder workflow. The second merge deliberately treats the first findings as a single new detector answer; original provenance remains in the first output.

`op.yaml` is the executable spec: identity, declared inputs, the Cog steps
and their Gates, and what the Track records. The runner (`src/op_runner.py`)
sequences those steps, builds each step's request from the spec's mapping
expressions, invokes each Cog only through the usage task that Cog declares,
gates the envelope it gets back, and writes a durable Track. No Python in
this package is Op-specific — `src/` is cog-smith machinery, enforced by
`smith op check`.

## Steps

1. **merge** — Merge synthetic detector repeats: `openteams/cog-merge-findings-candidate` task `run`
2. **handoff** — Exercise the mapped Cog handoff: `openteams/cog-merge-findings-candidate` task `run`

## Run it

From this directory, with Pixi installed and the sibling
`cog-merge-findings-candidate` checkout available:

```bash
pixi install --manifest-path ../cog-merge-findings-candidate/pixi.toml
pixi install
pixi run op -- --request examples/request.json --dry-run   # plan only
pixi run op -- --request examples/request.json             # the real run
pixi run test
```

Use the supplied synthetic A/B example. This smoke spec is not a general
merge service: the second step deliberately constructs a fresh A/B batch.
It preserves the finding but creates new single-answer provenance; the first
output retains the original repeated-detector provenance.

Each run writes `runs/<run id>/` with the input request, every step request,
every Cog envelope unchanged, and `track.json` — rewritten after every step,
so an interrupted run still leaves a readable Track.

To resume a failed or interrupted run after resolving its cause:

```bash
pixi run op -- --resume runs/<run-id>
```

Passed work is retained under the shared runtime's request/package reuse checks.
Changing the Op spec requires a new run. Exit codes are 0 completed/planned,
1 failed, 2 invalid input, and 3 paused for a human decision (this smoke Op has
no human Gate). Read `track.json` for status; it is not a background service.

## Verification and scope

This package carries unmodified Op machinery 0.6.6. Eight tests cover the
generated spec/dry-run checks plus actual Cog invocation, mapping and Track
evidence, a real contract failure stopping the downstream step, injected
transport failure followed by resume, and rejection of a stale spec digest.
The successful invocations are real code-Cog calls; only the transport failure
is injected. No models, external issue data, or protected operations are used.

```bash
cd ../cog-smith
pixi run python src/cogsmith_cli.py op check ../op-builder-smoke --tests --envelope
```

The local dry run and live run completed successfully. The next product is
`op-cog-builder`, which will use this same execution machinery. Its
[implementation plan](https://github.com/cogcloud-ai/cog-op-builder/blob/main/docs/roadmap.md)
identifies the remaining builder seams, decision Gates and revision cycle.
This smoke Op does not build a Cog or demonstrate those unimplemented features.

## Gate policy

Every step's Gate is `envelope-ok-no-error-problems`: a step fails when the
Cog reports `ok: false` or a contract-check problem with severity `error`.
Warnings produce `pass-with-problems` and the run continues. This is the
Op's policy — a Cog reports, and the Gate decides, never the other way
round. There are no independent Guards in this package; the Track records
that honestly as an empty list.

## Changing this Op

Edit `op.yaml`, then `pixi run test`. Adding a step means adding a Cog and
declaring it; the runner never grows per-Op behaviour. See
[cog-smith's BUILDING_OPS.md](https://github.com/cogcloud-ai/cog-smith/blob/main/BUILDING_OPS.md).

## License

Copyright 2026 OpenTeams. Licensed under the [Apache License 2.0](LICENSE).
Third-party dependencies and external model services retain their own licenses
and terms. Previously published BSD-3-Clause versions remain available under
that license.

## Public preview

See the [suite guide](https://github.com/cogcloud-ai/cog-op-builder/blob/main/docs/repositories.md)
for repository roles, supported setup, and current limitations.
