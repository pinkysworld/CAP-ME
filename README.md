# CAP-ME + FSO

CAP-ME is a research artifact for **application-semantics-aware survival benchmarking under adaptive censorship**. FSO (Function-Survival Overlay) is the bounded technology developed from its results: an encrypted logical messaging session that chooses among replaceable carrier instances according to function deadlines, delivery survival, failure domains, byte cost, endpoint risk, and a hard provider-control policy.

This is the public **software and reproducibility artifact only**. The manuscript
and rendered paper are intentionally private and excluded from Git history and
releases; see [`docs/manuscript-policy.md`](docs/manuscript-policy.md).

This repository contains:

- a deterministic, synthetic event simulator;
- five explicit architecture archetypes and three network conditions;
- an adaptive but interpretable traffic detector;
- exact path/endpoint/platform ablations with Shapley attribution;
- 900 main runs, 320 ablation runs, processed data, figures, and statistical analyses;
- a working FSO envelope, MDS codec, scheduler, receiver, authenticated acknowledgements, and comparison baselines;
- a 1,497,600-decision independent replay with five FSO ablations;
- a byte-reproducible closed-world carrier-adapter lab with loss, delay,
  reordering, duplication, burst, correlated-outage, tamper, and ACK faults;
- an encrypted UDP loopback testbed with controlled loss, latency, and jitter;
- a closed eight-container packet testbed with an internal-only network,
  per-carrier fault adapters, congestion/recovery phases, and resource metrics;
- an external-backend CensorLab bridge that maps real FSO envelopes,
  fragmentation, and authenticated ACKs to offline packet decisions and then
  reconstructs longitudinal function-level survival;
- a gated field-study package with authorization and stop-rule validation; and
- a verified reference audit and generated evidence ledger.

The executable packet tests are restricted to loopback or an
orchestrator-created internal Docker network whose destinations are private
addresses. They do **not** probe live networks, contact third-party services,
process user traffic, discover relays, disguise traffic, or connect to an
external host. FSO is a laboratory prototype, not a safety-reviewed
censorship-circumvention product.

## Status and claim boundary

The current evidence is a controlled simulation study, not a field measurement. Numeric architecture parameters are declared experimental assumptions and are not measurements of the Great Firewall of China, WhatsApp, Signal, WeChat, or any other named system. External factual claims are logged against verified primary sources; quantitative claims are tied to generated result files.

The strongest defensible novelty claim is the combination of:

1. function-specific messaging availability over time;
2. a composed path/endpoint/platform adversary;
3. exact interventional layer attribution under paired randomness; and
4. explicit separation of network availability from provider trust.

For FSO, the dated search found no prior system jointly applying messaging-function deadlines, longitudinal censorship-survival estimates, a hard provider-control constraint, and cross-carrier failure-domain discounts to carrier-portfolio selection. This is a defeasible search result, not proof of priority. Transport-independent sessions, multipath splitting, disruption-tolerant message overlays, traffic-class-aware scheduling, erasure coding, and AEAD are all acknowledged prior art.

That claim is qualified by the structured literature audit in [`docs/novelty-audit.md`](docs/novelty-audit.md). No artifact can guarantee acceptance at a top venue; field validation and independent replication remain necessary for strong external-validity claims.

## Structural model uncertainty

The original seed intervals hold every declared model assumption fixed. The
additional robustness study crosses 72 stratified parameter points, 16 sampled
dimensions, four structurally distinct censor models, five architectures, and
three common seeds: 4,320 synthetic runs in total. It reports model-ensemble
quantiles, pairwise ordering frequencies, trust-eligible ranks, global partial
rank sensitivities, and separate model-versus-seed variance components.

Across its 20 model/architecture cells, the declared model component accounts
for 0.819--0.981 of the decomposed variance. Generated Transport has median
trust-eligible rank one in all four censor structures, but is first in only
0.556--0.764 of their parameter draws. This weakens any interpretation of the
fixed-parameter ranking as universal. The ranges are author-declared and do not
represent a confidence distribution for a real censor. See
[`docs/model-uncertainty.md`](docs/model-uncertainty.md) and
[`results/processed/robustness`](results/processed/robustness).

## Headline controlled-study result

Under the declared mobile-like scenario, adaptive cross-layer control reduced mean area under the availability curve (AUAC) from 0.827 to 0.266 for Direct E2EE and from 0.735 to 0.113 for a Fixed App Proxy. Generated Transport retained 0.815 AUAC and Ephemeral Relay 0.771. The Permitted Platform archetype retained 0.885 network/service availability, but that value does not imply content confidentiality from its provider.

Exact three-layer ablations attributed 0.585 AUAC loss to endpoint control for Direct E2EE and 0.697 for Fixed App Proxy. For Ephemeral Relay, path control (0.089) exceeded endpoint control (0.016). The rich-media hypothesis was only partly supported: real-time and file operations were most fragile, while media was not uniformly worse than text.

All values above are simulation estimates. Confidence intervals quantify variation across declared random seeds, not uncertainty about a national network.

## FSO confirmation result

On 20 disjoint synthetic seeds, FSO reaches AUAC 0.912 (95% seed-bootstrap CI [0.907, 0.917]) at 1.246 transmitted bytes per payload byte. Transport-independent session failover reaches 0.896 [0.890, 0.902] at overhead 1.212; the paired difference is 0.016 [0.014, 0.018]. Generated-only delivery reaches 0.802.

The ablations are part of the result, including findings unfavorable to the mechanism:

- unconditional two-lane duplication reaches higher AUAC (0.927) but costs 2.000 bytes per payload byte, 60.5% more than FSO;
- disabling feedback reaches 0.915 AUAC, slightly above full FSO;
- fixed coding reaches 0.857 at overhead 1.649; and
- removing failure-domain diversity reduces AUAC to 0.888.

The deterministic full-protocol lab completes 100/125 operations across five
failure phases. Its two clean rebuilds produce identical observation and
manifest hashes. It injects 318 fragment drops, 39 fragment corruptions, 57
duplicates, two ACK drops, and six ACK corruptions; all corrupted envelopes and
ACKs that reach their authenticators are rejected. The 0.800 availability and
2.037 byte overhead characterize this declared laboratory matrix only.

The actual encrypted UDP implementation completes 57/60 synthetic operations on `127.0.0.1` under declared impairment, with zero external destinations, zero provider-controlled attempts, and zero receiver or acknowledgement authentication failures. This validates the implementation path only; it is not a measurement of censorship resistance.

The separate multi-host implementation runs one sender, six carrier-fault
adapters, and one receiver on a Docker network marked internal, with no
published ports. Its frozen 90-operation run records 68 acknowledged
completions and 71 receiver completions; the three-operation difference is
explained by lost acknowledgements. Phase-level analytic-versus-observed
availability has mean absolute error 0.0780 and Brier score 0.0594. All 41
incomplete fragment sets are expired at phase deadlines, leaving zero fragment
or coded-message state. These are implementation and recovery measurements
under declared faults, not censorship-resistance estimates.
Two independent executions produced identical delivery decisions, lane
choices, wire counts, injected-fault counters, and recovery counts after
excluding measured timing, CPU, and RSS fields.

A separate no-network pipeline benchmark spans 64-byte to 1-MiB payloads and
1-, 2-, 3-, and 5-shard plans on the recorded Apple-arm64 host. At 1 MiB, the
median local encode/encrypt/fragment/reassemble/decrypt latency is 226 ms for a
single shard, 373 ms for 2-of-3 coding, and 477 ms for 3-of-5 coding; measured
wire overheads are 1.003, 1.505, and 1.672. For 64-KiB 2-of-3 operations, four
worker processes reach 1.94x the one-worker throughput (0.49 parallel
efficiency). These are descriptive prototype costs on one machine, not
production targets or censor measurements.

The earlier confirmation found online feedback slightly adverse. A second,
prospectively frozen 12-seed evaluation is versioned separately. Its decision
rule permits a benefit claim only if the paired 95% interval lies wholly above
zero; otherwise feedback remains uncredited and disabled is the recommended
default. The frozen plan is in
[`configs/fso-feedback-evaluation.json`](configs/fso-feedback-evaluation.json).

## Closed CensorLab result

The pinned official CensorLab `mega_gfw` composite censored 127 of 654
synthetic packets, while CAP-ME reconstructed 60/60 application operations as
successful. After two feedback epochs, the scheduler selected only the two
declared UDP relay lanes. This shows that the packet-to-message bridge and
feedback loop execute end to end; it does not show effectiveness against the
deployed Great Firewall. In particular, this official demonstration's
fully-encrypted-traffic rule inspects TCP rather than both transports used in
the experiment.

The deliberately stricter, transparent campaign scenario applies the same
declared encrypted-payload heuristic to TCP and UDP and quarantines an endpoint
after three suspicious outbound packets. It censored 436 of 654 packets and
only 13/60 application operations succeeded (availability 0.217): text 0.667,
presence 0.250, media 0.083, realtime 0.083, and file 0.000. This retained
negative result is important: scheduling, fragmentation, encryption, and
redundancy alone are not a universal censorship bypass. Survival depends on
carrier instances that actually fail independently under the tested censor
model.

Both scenarios are deterministic in their PCAPs, labels, packet decisions, and
application outcomes. CensorLab processing times and raw log timing are
machine-dependent. Neither scenario models or measures contemporary China.

## Reproduce

Requirements: Python 3.11 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[artifact,dev]'
python3 -m unittest discover -s tests -v
python3 -m build
```

Run the small smoke matrix:

```bash
python3 -m capme run --config configs/smoke.json --output results/raw/smoke
python3 -m capme ablate --config configs/smoke.json --output results/raw/smoke
python3 analysis/run_analysis.py --raw results/raw/smoke --processed results/processed/smoke
```

Run the model-uncertainty smoke matrix or the complete frozen design:

```bash
make robustness-smoke
make robustness
```

Rebuild the complete study:

```bash
python3 -m capme run --config configs/study.json --output results/raw/study
python3 -m capme ablate --config configs/study.json --output results/raw/study
python3 analysis/run_analysis.py --raw results/raw/study --processed results/processed/study
python3 analysis/generate_artifacts.py --processed results/processed/study --artifact-generated artifacts/generated
```

Rebuild the FSO confirmation sample after generating its disjoint source trace:

```bash
make fso-confirmation-source
make fso-confirmation
python3 analysis/generate_fso_artifacts.py
```

Run the network-restricted packet test and authorization check:

```bash
make fso-deterministic-lab
make fso-loopback
make fso-multihost
make fso-scalability
make field-check
```

Run the closed, no-network CensorLab packet-plane study after building the
pinned external CensorLab image:

```bash
PYTHONPATH=src python3 analysis/run_censorlab_study.py \
  --config configs/fso-censorlab.json \
  --output results/processed/fso/censorlab \
  --censorlab-repo /path/to/censorlab
```

Run the stricter cross-transport campaign scenario with the same image:

```bash
PYTHONPATH=src python3 analysis/run_censorlab_study.py \
  --config configs/fso-censorlab-campaign.json \
  --output results/processed/fso/censorlab-campaign \
  --censorlab-repo /path/to/censorlab
```

See [`testbeds/censorlab/README.md`](testbeds/censorlab/README.md) for the pinned
source build, containment controls, licensing boundary, and interpretation
rule. CensorLab already supplies a `mega_gfw` demonstration; CAP-ME’s added
technology is the packet-to-message lifecycle and adaptive-scheduler bridge,
not another generic GFW emulator.

`field-check` validates documentation completeness only. The supplied approved manifest is loopback-only and returns `ready_for_external_implementation: false`. The external template is intentionally pending. There is no external carrier connector in this release.

Build the exact package that independent security, ethics, and legal reviewers
must sign off on before any external implementation:

```bash
PYTHONPATH=src python3 analysis/build_review_bundle.py
```

The three records in `field/reviews/` remain deliberately pending. The external
gate additionally checks the bundle hashes, three distinct reviewer identities,
review dates and expiry, bundle identity, conflicts, and unresolved findings.

Validate the public artifact:

```bash
make validate
```

The versioned processed results live in [`results/processed/study`](results/processed/study). Full raw CSVs are about 80 MB and are deliberately ignored by Git; the commands above regenerate them deterministically from the recorded configuration and seeds.

## Repository map

- `src/capme/`: simulator, classifier, analysis, and vector-figure code
- `src/capme/fso/`: FSO protocol, coding, cryptography, framing, deterministic carriers, schedulers, replay, loopback testbed, and deployment gate
- `configs/`: smoke and complete experiment definitions
- `tests/`: deterministic unit and invariant tests
- `analysis/`: analysis, artifact generation, and validation entry points
- `results/processed/study/`: compact reviewable results
- `results/processed/robustness/`: structural model-uncertainty results and sensitivity estimates
- `results/processed/fso/`: confirmation and loopback results with manifests
- `testbeds/censorlab/`: minimal external-source build and closed-testbed guide
- `testbeds/multihost/`: internal-network Docker testbed and containment guide
- `field/`: exact review bundle, independent-review templates, future-study authorization template, local-only manifest, protocol, and stop rules
- `docs/`: methodology, ethics, novelty, and claim ledgers
- `artifacts/generated/`: generated tables, figures, and evidence manifests
- `artifacts/references.bib`: verified reference metadata used by the research
- `artifacts/reference-validation.json`: source-by-source verification record

## Responsible use

The repository evaluates abstract defenses in simulation, offline synthetic
PCAPs, and localhost traffic. It intentionally excludes live scanner code,
target acquisition, protocol impersonation, external endpoints, and
operational evasion instructions. See [`docs/ethics.md`](docs/ethics.md),
[`field/study-protocol.md`](field/study-protocol.md), and
[`field/stop-rules.md`](field/stop-rules.md) before proposing any real-world
data collection.

## License and citation

Code and public artifact materials are licensed under Apache-2.0. See [`CITATION.cff`](CITATION.cff); replace the anonymous software author before a non-anonymous artifact release.
