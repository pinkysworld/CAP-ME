# Artifact evaluation guide

## Claims supported by the artifact

The artifact supports reproducibility of the declared synthetic experiment,
FSO replay, deterministic full-protocol carrier lab, localhost packet
execution, and the pinned offline CensorLab bridge, including architecture
rankings, function-specific AUAC values, paired contrasts, endpoint burn rates,
layer attribution, FSO baselines/ablations, packet-to-message reconstruction,
and safety invariants. It does not support claims about any live country or
commercial service.

## Minimal review (under two minutes after installation)

```bash
make test
make smoke
```

Expected: all unit and integration tests pass; the smoke run writes main and ablation manifests and completes analysis without conservation errors.

## Result inspection without rerunning the full matrix

Review:

- `results/processed/study/analysis_manifest.json`
- `results/processed/study/aggregate_metrics.csv`
- `results/processed/study/paired_contrasts.csv`
- `results/processed/study/shapley_attribution.csv`
- `artifacts/generated/headline_results.json`
- `results/processed/fso/confirmation/study_manifest.json`
- `results/processed/fso/confirmation/aggregate_metrics.csv`
- `results/processed/fso/confirmation/paired_contrasts.csv`
- `results/processed/fso/deterministic-lab/manifest.json`
- `results/processed/fso/loopback/manifest.json`
- `results/processed/fso/censorlab/manifest.json`
- `results/processed/fso/censorlab-campaign/manifest.json`
- `artifacts/generated/fso_headline_results.json`

Then run `make validate`. Validation checks those properties plus FSO counts and hashes, seed disjointness, exact headline values, byte-reproducible carrier-lab results, nonce uniqueness, injected-fault counters, both CensorLab result trees and containment invariants, zero provider-controlled attempts, loopback-only execution, receiver and ACK authentication counters, exact review-bundle hashes, and that the pending external authorization fails while the local record cannot authorize external implementation.

## Full reproduction

`make study analyze artifacts validate`

Expected scale: 1,220 simulation runs and 3,513,600 messaging-operation attempts. Runtime depends on the machine; the reference run completed locally without network access. Raw CSVs occupy about 80 MB and are intentionally excluded from Git.

The FSO confirmation is a separate pipeline because it requires the disjoint CAP-ME source trace:

`make fso-confirmation-source fso-confirmation fso-deterministic-lab fso-loopback artifacts validate`

Expected FSO scale before the optional external-backend run: 100 source runs,
260 strategy-seed runs, 1,497,600 operation decisions, 125 deterministic
full-protocol operations, and 60 localhost packet operations. The CensorLab
studies add two six-epoch closed runs of offline synthetic PCAP processing; their separate
instructions and pinned dependency are in
`testbeds/censorlab/README.md`. No study command requires or permits an
external packet destination.

## Determinism

Random seeds are fixed in `configs/study.json`. Each seed is split into independent substreams. CSV and JSON writers use stable field ordering; manifests record SHA-256 digests. Bootstrap and sign-flip analyses use fixed analysis seeds.

The FSO replay and closed-world carrier lab are deterministic under the same rules. The lab additionally uses an explicitly non-production deterministic entropy source so encrypted envelope, fragment, and ACK behavior can be reproduced byte-for-byte; it checks nonce uniqueness inside each run. For the CensorLab bridge, PCAPs, labels, packet decisions, and application outcomes are deterministic, while processing-time columns and raw log timing depend on the host. The loopback result is not bitwise deterministic because operating-system timing and ephemeral UDP ports are recorded; its manifest authenticates the observed run instead.

## Reusability

New architecture archetypes and network conditions can be added in `src/capme/model.py`; new experiment matrices are JSON configurations. Reviewers should avoid interpreting new parameters as empirical until they are calibrated with ethically obtained measurements.
