# Methodology and reproducibility specification

## Unit of analysis

A run is one `(architecture, censor regime, network condition, seed)` tuple. Each of 36 epochs executes 16 operations for each of five messaging functions. The complete main matrix contains 5 architectures × 3 censor regimes × 3 networks × 20 seeds = 900 runs and 2,592,000 attempted operations. The attribution matrix contains 5 architectures × 8 layer subsets × 8 seeds = 320 runs and 921,600 attempted operations.

Seeds are independent simulation replicates. Within a seed, six deterministic random substreams separate classifier training, traffic features, endpoint choice, censor actions, network outcomes, and provider-policy outcomes. Layer ablations reuse the same substreams, implementing common random numbers.

## Architecture archetypes

The five archetypes are declared design points, not named products:

- **Direct E2EE:** small stable endpoint set; content unavailable to the provider in the model.
- **Fixed App Proxy:** small stable proxy set with higher probe confirmation.
- **Generated Transport:** per-deployment protocol diversity and moderate endpoint churn.
- **Ephemeral Relay:** large, rapidly replaced relay population with session recovery.
- **Permitted Platform:** domestically permitted endpoints; provider terminates confidentiality and controls delivery.

All numeric parameters appear in `src/capme/model.py`. Labels describe the modeled control boundary and do not imply empirical equivalence to a commercial service.

## Messaging functions

Text, media, file, presence, and real-time workloads differ in payload size, segmentation, round trips, delivery requirement, and deadline. Availability is successful completion before the workload deadline after all active censor and network stages.

## Censor layers

- **Path:** a diagonal-Gaussian likelihood-ratio detector scores five bounded synthetic features. Its threshold is calibrated on 2,000 benign examples to a target false-positive cap of 0.001. The realized adaptive-model rate is 0.000792--0.000833 across archetypes; the target and observed range are not interchangeable. An adaptive regime retrains every three epochs using the previous protocol generation.
- **Endpoint:** passive discovery, active probing, accumulated reputation, block budget, time-limited blocks, and endpoint replacement.
- **Platform:** a provider that controls delivery may suppress declared policy-triggering operations. The permitted architecture is treated as collateral that the path/endpoint censor will not block.

The classifier is deliberately interpretable and is not represented as a state-of-the-art GFW classifier. Precision is reported at a declared prevalence of 0.001 because ROC-style rates alone can mislead in imbalanced settings.

## Outcomes

For function `f` at epoch `t`, availability is:

`A_f(t) = successful operations / attempted operations`.

Run AUAC is the arithmetic mean of the five function availabilities across all 36 epochs. `T50` is the first epoch beginning three consecutive epochs with overall availability below 0.5; runs without an event are right-censored at the horizon and represented as epoch 36 for summary tables. Endpoint burn rate is blocked endpoint events divided by endpoint-exposure epochs.

The processed survival curves average functions within each run and epoch before bootstrapping across seeds. This prevents functions from being treated as independent replicates.

## Statistics

- 95% percentile bootstrap intervals use 2,000 resamples of seed-level run metrics.
- Adaptive-minus-passive comparisons use paired seed differences.
- Two-sided random sign-flip tests use 30,000 draws.
- Fifteen main comparisons are adjusted with Benjamini-Hochberg.
- The eight possible path/endpoint/platform layer subsets are evaluated for every attribution seed. Exact three-player Shapley values allocate total AUAC loss. Eight attribution seeds were fixed to keep the complete coalition design bounded at 320 runs (921,600 operations), rather than sampling coalitions. Because this is a small replicate set, both seed-level values and seed-bootstrap intervals are published. Zeros for layers disabled by an archetype are structural, not effect estimates.

Intervals quantify Monte Carlo variation under this model only. They are not population intervals for a country, app, or deployed censor.

## Frozen outputs

`results/processed/study/analysis_manifest.json` records source hashes and row counts. `artifacts/generated/generation_manifest.json` records figure and table inputs. Full raw results are deterministic but excluded from Git because of size; a complete rebuild regenerates them from `configs/study.json`.

## FSO mechanism evaluation

### Development split

The fixed-code pilot reused the original CAP-ME seeds. It was inferior to session failover and is retained in `docs/fso-development-log.md`. The next design changed only the local plan selector to choose among predeclared function-specific plans. Twenty new seeds were frozen before generating the second source trace; they are disjoint from the pilot/main-study seeds. The current laboratory prototype adds authenticated acknowledgements, bounded reusable fragmentation, deterministic full-protocol carrier adapters, and a stronger independent-review gate. The canonical policy disables online feedback; the feedback-enabled policy remains an ablation under its historical internal strategy label.

The final replay has:

- 5 adaptive-mobile architecture traces × 20 seeds × 36 epochs × 5 functions = 18,000 trace cells;
- 13 strategies × 20 seeds = 260 strategy-seed runs;
- 32 operations per function and epoch = 1,497,600 operation decisions; and
- 5 mechanism variants relative to canonical feedback-off FSO: feedback enabled, fixed coding, no semantics, no diversity, and no redundancy.

For each `(seed, epoch, function, operation index, lane)`, a stable keyed draw determines the potential lane outcome. Any strategy attempting that lane receives the same draw. A scheduler observes only outcomes for its past attempts; the trace probability, future values, and unattempted-lane outcomes remain hidden. These potential outcomes do not react to the number, timing, or byte volume of a strategy's other attempts. Consequently, the replay prices duplication in bytes but cannot represent a traffic-volume-reactive censor; this can favor redundant strategies and is an explicit validity limit.

The CAP-ME trace probability is already the probability of completion under the workload deadline. The final FSO replay therefore samples it once and does not apply another hard deadline. An intermediate confirmation run did apply the deadline twice; the final pipeline corrected that modeling error and regenerated every output with the frozen seeds. The change is disclosed because it occurred after intermediate output was inspected.

FSO uncertainty uses 2,000 seed bootstraps. Paired FSO-minus-baseline contrasts use 30,000 sign flips and Benjamini-Hochberg adjustment across 12 baselines. Intervals again cover only synthetic seed variation.

### Four-structure all-strategy replay

The same 13-strategy comparison is repeated at the unperturbed base parameters
of each declared censor structure: classifier-dominant, endpoint-discovery,
resource-bounded composed, and adaptive composed. Twenty paired seeds produce
400 source simulations, 72,000 trace cells, 1,040 strategy-seed runs, and
5,990,400 operation decisions. FSO is the feedback-off policy in all four
structures. This check asks whether the primary ordering survives changes in
model composition; it is distinct from the 72-point Latin-hypercube uncertainty
study and does not add traffic-volume coupling.

### Deterministic carrier-adapter execution

The closed-world discrete-event lab runs the real scheduler, MDS codec,
ChaCha20-Poly1305 envelopes, fragmentation and reassembly, receiver state, and
authenticated acknowledgements through simulated carrier adapters. Five frozen
phases inject ordinary loss, latency and reordering; burst and correlated-domain
loss; declared domain outages; duplication; envelope corruption; ACK loss and
ACK corruption; and recovery. Stable keyed draws and laboratory-only
deterministic entropy make both observations and manifests byte-reproducible.
Nonce and message-ID uniqueness are checked within each run, and incomplete
fragment/shard state is expired at operation deadlines. This mode is an
equivalent self-contained failure injector, not an empirical censor model.

The versioned run contains 125 synthetic operations. It is descriptive: the
single frozen impairment matrix is not used for inferential claims, and its
availability must not be compared directly with the trace-replay AUAC.

### Loopback packet execution

The loopback test exercises actual UDP datagrams, controlled loss/latency/jitter, carrier fragmentation, ChaCha20-Poly1305 frames, authenticated acknowledgements, buffering, replay state, decoding, and strict provider trust. Every socket destination must be in `127.0.0.0/8` or `::1`; non-loopback addresses are rejected before use. The versioned run contains 60 synthetic operations and no external traffic.

Loopback timing and ephemeral port numbers are operating-system observations, so this run validates behavior rather than bit-for-bit determinism. Its manifest hashes the exact recorded observations. The trace replay remains the source for statistical comparisons, while the closed-world lab supplies bit-for-bit protocol-path reproducibility.

### Closed multi-host packet execution

The multi-host test separates one sender, six fault-injection carrier adapters,
and one receiver into eight non-root containers. Docker marks their bridge
network internal; no ports are published. Runtime guards reject any carrier or
receiver alias that resolves outside loopback, RFC 1918, or IPv6 unique-local
space. The orchestrator records the image ID, pinned base digest, source hashes,
engine, addresses, containment settings, and zero-port invariant.

Six frozen phases cover a clean start, fixed-endpoint pressure,
generated-transport classifier pressure, correlated relay discovery,
congestion, and recovery. The client records delivery, latency, wire overhead,
CPU time, peak RSS, authenticated ACK outcomes, and an analytic packet-success
probability. The analytic model uses the declared independent per-datagram
loss/corruption rates and a Gaussian-delay approximation. Brier score and
phase-level mean absolute error therefore test implementation concordance, not
external censor calibration. After each phase, deadline-stale fragment and
coded-message state is expired and both in-flight counts must be zero.
The packet-path run uses the no-feedback scheduler so operating-system timing
noise cannot influence later lane selection; online feedback is evaluated only
in the separate frozen audit below.

The complementary no-network scalability benchmark measures the complete
local coding/envelope pipeline over payloads from 64 bytes to 1 MiB and coding
widths from one to five shards. It records wall time, CPU time, median and 95th
percentile operation latency, wire overhead, peak RSS, verified recovery, and
1/2/4-process throughput for a fixed 64-KiB 2-of-3 case. These measurements are
descriptive observations from the environment recorded in the manifest; they
are not hardware-independent performance claims.

### Prospectively frozen feedback audit

The original 20-seed confirmation is treated as development evidence because
online feedback was slightly adverse. Before generating any follow-up outcome,
12 new seeds disjoint from the main study and confirmation were frozen in
`configs/fso-feedback-source.json`. The paired comparison and decision rule
were frozen in `configs/fso-feedback-evaluation.json`. The frozen file retains
legacy internal labels in which “FSO” means feedback-enabled. A benefit is supported
only if the two-sided 95% seed-bootstrap interval for feedback-enabled minus no-feedback
AUAC has a lower bound above zero, while harm is declared only if its upper
bound is below zero. The observed difference is -0.00181 with interval
[-0.00340, -0.000217], so the frozen directional rule classifies the sign as
adverse within this synthetic model. The magnitude is negligible and a secondary
random sign-flip diagnostic is p=0.0512. The supported operational conclusion is
no benefit and a disabled default, not a population, deployment, or general
feedback-harm effect. Secondary resource and function-specific metrics are descriptive.

### CensorLab packet-plane execution

The optional CensorLab bridge generates deterministic Ethernet/IPv4 PCAPs
containing the same ChaCha20-Poly1305 shard envelopes, bounded carrier
fragments, and authenticated acknowledgements used by FSO. Every address is a
private or RFC 5737 documentation address. The PCAPs are processed by the
pinned external CensorLab executable in offline mode inside a no-network,
read-only container with all capabilities dropped; no generated packet is
transmitted.

Each epoch starts with a known blocked documentation-address packet that
calibrates CensorLab's displayed PCAP index. Declared per-lane probes and
application operations then provide packet actions. A shard succeeds only if
all its fragments and its authenticated potential ACK avoid a blocking action
and the declared round-trip latency fits the function deadline. The message
succeeds after its coding threshold of distinct shards succeeds. Only these
locally observable lane outcomes update the survival scheduler before the next
epoch.

The potential ACK trace is a static common-outcome device: analysis ignores an
ACK whenever its data shard is blocked. It does not claim interactive causal
packet generation. The no-censor diagnostic removes packet actions while
holding the observed schedule fixed; it is not a separately adapted policy.
The pinned official `mega_gfw` demo is an educational composite and therefore
provides a software-integration test, not country calibration or external
validity.
