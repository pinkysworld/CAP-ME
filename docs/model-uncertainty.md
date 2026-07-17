# Structural model uncertainty and global sensitivity

The main CAP-ME intervals quantify random-seed variation while holding all
declared architecture, censor, and network assumptions fixed. That is useful
for Monte Carlo precision, but it does not quantify uncertainty about those
assumptions. This study adds a separate, explicitly synthetic model ensemble.

## Design

The frozen configuration in `configs/robustness.json` crosses:

- 72 points from a deterministic stratified Latin-hypercube design;
- 16 architecture, censor, and network parameters;
- four structurally distinct declared censor models;
- five architecture archetypes; and
- three common replicate seeds.

This produces 4,320 runs. The same parameter point and seed are reused across
architectures and censor structures to preserve paired comparisons.

The four censor structures are:

1. a classifier-dominant path model with no endpoint or platform action;
2. an endpoint-discovery model with no path or platform action;
3. a resource-bounded composed path/endpoint/platform model; and
4. a more aggressive adaptive composed model.

These are independently specified rule structures inside the same CAP-ME
simulator. They are not independent implementations, measurements, or models
contributed by separate research teams.

The sampled dimensions cover passive separability, discovery, probe
confirmation, endpoint-pool size, rotation speed, protocol diversity,
transport overhead, detector false-positive cap, path enforcement, censor
budgets, block duration, retraining interval, platform filtering, latency,
loss, and bandwidth. The exact ranges and transformations are part of the JSON
configuration rather than hidden in analysis code.

## Analysis

For each model draw and architecture, the analysis first averages the three
common-seed replicates. It then reports model-ensemble quantiles, pairwise
ordering frequencies, and ranking stability. Rankings are reported both over
all archetypes and over the subset whose provider does not control delivery;
the latter prevents network availability on the permitted-platform archetype
from being mistaken for a confidentiality-preserving result.

Partial rank correlation coefficients (PRCCs) measure monotonic global
sensitivity after conditioning on the other structurally active sampled
dimensions. Inactive dimensions are recorded as inactive and receive no
coefficient. Deterministic bootstrap resampling of design points supplies the
reported PRCC intervals.

A balanced method-of-moments decomposition separates within-design seed
variance from between-design model variance. It is descriptive of this model
ensemble and should not be read as a population variance decomposition for a
real censor.

## Result boundary

Across the 20 censor-model/architecture cells, the model component accounts
for 0.819 to 0.981 of the decomposed variance. Thus, under these declared
ranges, uncertainty about assumptions is much larger than random-seed noise.
This is a reason to widen the paper's uncertainty claims, not evidence that the
chosen parameter ranges describe any country.

Generated Transport has median trust-eligible rank one in all four censor
structures, but its fraction of first-place model draws ranges from 0.556 to
0.764. The ordering is therefore materially less absolute than the original
fixed-parameter comparison suggests.

This is an exploratory robustness study. It was not externally preregistered,
and the model families remain author-declared. A confirmatory follow-up should
freeze a new design before execution and include independently implemented or
empirically calibrated censor models.

## Reproduction

Run the short integration matrix:

```bash
make robustness-smoke
```

Rebuild the complete study:

```bash
make robustness
make validate
```

The versioned results and their exact hashes are in
`results/processed/robustness/`.
