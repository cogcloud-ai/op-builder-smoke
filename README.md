# Builder execution smoke check

Model-free verification of shared Op execution and mapped Cog handoffs, using
a Cog the builder itself produced. This is not the cog-builder workflow. The
second step receives the first tally's `counts` as its `prior_counts`, so the
handoff is a real data dependency between two invocations of one code Cog.

`op.yaml` is the executable spec: identity, declared inputs, the Cog steps
and their Gates, and what the Track records. The runner (`src/op_runner.py`)
sequences those steps, builds each step's request from the spec's mapping
expressions, invokes each Cog only through the usage task that Cog declares,
gates the envelope it gets back, and writes a durable Track. No Python in
this package is Op-specific — `src/` is cog-smith machinery, enforced by
`smith op check`.

## Steps

1. **tally** — Tally the first texts: `openteams/cog-word-tally` task `run`
2. **handoff** — Accumulate the second texts onto the first tally: `openteams/cog-word-tally` task `run`

[cog-word-tally](https://github.com/cogcloud-ai/cog-word-tally) is the first
Cog built end to end through op-cog-builder 0.2.0 with both acceptance Gates;
its README records the build and the digests it was accepted under.

## Run it

From this directory, with Pixi installed and the sibling `cog-word-tally`
checkout available:

```bash
pixi install --manifest-path ../cog-word-tally/pixi.toml
pixi install
pixi run op -- --request examples/request.json --dry-run   # plan only
pixi run op -- --request examples/request.json             # the real run
pixi run test
```

Use the supplied example texts. The first output is the tally of
`first_texts`; the second output preserves every count from the first and adds
`second_texts` on top, with `total_words` the sum of both.

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

This package carries unmodified Op machinery 0.7.1. Eight tests cover the
generated spec/dry-run checks plus actual Cog invocation, mapping and Track
evidence (the handoff request carries the first tally's counts verbatim), a
real contract failure stopping the downstream step (a negative prior count the
Cog's own contract check refuses), injected transport failure followed by
resume, and rejection of a stale spec digest.
The successful invocations are real code-Cog calls; only the transport failure
is injected. No models, external issue data, or protected operations are used.

```bash
cd ../cog-smith
pixi run python src/cogsmith_cli.py op check ../op-builder-smoke --tests --envelope
```

`op-cog-builder` uses this same execution machinery; its
[roadmap](https://github.com/cogcloud-ai/cog-op-builder/blob/main/docs/roadmap.md)
lists the remaining builder work. This smoke Op does not build a Cog; it
exercises one the builder built.

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
