# FSO prospective development log

## Frozen exploratory design

The first FSO 0.1 replay used the 20 seeds from the completed CAP-ME study and
the function table frozen in `docs/fso-protocol.md`: text 1-of-2, presence
1-of-1, media 2-of-3, file 3-of-5, and real-time 1-of-2 hot standby.

The exploratory result did not support superiority of that fixed policy:

- fixed-code FSO AUAC: 0.730;
- transport-independent session failover AUAC: 0.784;
- non-semantic parallel 1-of-2 AUAC: 0.787;
- generated-only AUAC: 0.708; and
- fixed-code FSO byte overhead: 1.649 versus 1.225 for session failover.

The result is retained as a negative development finding. It shows that erasure
coding is not automatically beneficial when the conservative replay assigns a
whole-operation delivery probability to every shard. Requiring multiple shard
successes can cost more availability than it recovers.

## Revision declared before confirmation

FSO 0.2 keeps the envelope, carrier profiles, feedback, trust rule, outcome
generator, correlation weight, and metrics unchanged. It changes only the local
plan selector. For each function it now chooses among a predeclared set of:

- one carrier;
- two-carrier sequential failover;
- two-carrier parallel duplication;
- primary plus hot standby; and
- 2-of-3 or 3-of-5 coding where eligible.

The utility uses function-specific byte and deadline penalties. This revision
generalizes the strong session-failover baseline rather than assuming coded
plans must always be used.

## Independent confirmation sample

Before generating any confirmation outcome, the 20 seeds in
`configs/fso-confirmation-source.json` were frozen. They are disjoint from the
exploratory CAP-ME seeds. The confirmation experiment uses the same adaptive
mobile scenario, operations, censor parameters, common-random-number method,
and strict-trust policy. Results from these seeds are the independent mechanism
evaluation; the original 20-seed replay remains exploratory. The study was not
externally preregistered, so “independent confirmation sample” does not mean a
confirmatory field trial.

## Confirmation implementation correction

An intermediate run applied a second hard deadline after sampling a CAP-ME
availability value that already included deadline effects. This double-counted
deadline failure. The final pipeline removes the second filter and regenerates
all strategies with the same frozen seeds. The correction changes the replay's
semantics, not a tuned model parameter, but it was made after intermediate
output was inspected and is therefore disclosed here and in the manuscript.

## Superseded pre-audit analysis

The first versioned analysis replayed 13 strategies over 1,497,600 decisions.
It reported canonical feedback-off FSO at AUAC 0.9148, session failover at
0.8961, and a 0.027 contribution from failure-domain diversity. The FSO and
session values were correctly computed for those implementations, but the
mechanism interpretation was incomplete: it lacked a deadline-and-cost-matched
baseline, the `no diversity` variant forced portfolios into the minimum number
of domains, and the remaining component ablations inherited the historical
feedback-enabled default. The 0.027 diversity claim and any inference of FSO-
specific scheduler superiority are therefore superseded.

## July 2026 post-audit correction and final analysis

The correction retained the frozen source trace, seeds, outcome generator, and
canonical FSO definition. It added a matched baseline, made all component
ablations feedback-off, and defined `no diversity` by removing only the domain
discount, penalty, and tie-break. The complete 14-strategy rerun contains
1,612,800 decisions.

Canonical FSO reaches AUAC 0.91476 [0.90946, 0.91971] at byte overhead 1.238.
The deadline-and-cost-matched failover baseline reaches 0.91457 [0.90911,
0.91929] at 1.241; paired FSO minus baseline is +0.00018 [-0.00064, +0.00114].
The older session failover reaches 0.89607, leaving the +0.01869 contrast, but
that contrast now isolates deadline/cost awareness rather than FSO's additional
burn and failure-domain terms.

The clean no-diversity estimate is +0.00127 [-0.00015, +0.00331], so the study
does not identify a diversity benefit. Fixed coding reaches 0.861, no
redundancy 0.792, and unconditional no-semantics duplication 0.928 at overhead
2.000. The current feedback rule remains unsupported. Four-structure replays
also leave every FSO-minus-matched interval crossing zero. A 25-point global
sensitivity design is mixed (52% positive point estimates, 24% wholly positive
intervals, 12% wholly negative), while a separately coded author-designed
trace yields a small positive +0.00259 [+0.00065, +0.00479]. The final claim is
therefore a benchmark and mechanism-boundary result, not general scheduler
superiority.

## Prospectively frozen feedback follow-up

Before generating follow-up outcomes, the repository froze 12 new seeds,
the paired feedback-enabled-minus-no-feedback estimand (under the legacy labels), a two-sided 95% seed-bootstrap
interval, and its decision rule in commit `f4ca7bdb909bdeabbb9b297004846449eab98aa0`.
The evaluation produced AUAC 0.91347 for FSO and 0.91528 without feedback. The
paired difference is -0.00181 with interval [-0.00340, -0.000217]. Its upper
bound is below zero, meeting the frozen directional rule within this declared
synthetic model. The magnitude is negligible and the secondary random sign-flip
diagnostic is p=0.0512. Feedback is therefore disabled by default, and no benefit
claim is retained. The result is not evidence about a deployed censor, population,
or feedback mechanisms generally.

## Current protocol-path execution

The current laboratory prototype does not change the frozen replay, scheduler objective, confirmation
seeds, or reported inferential results. It adds reusable bounded fragmentation,
authenticated ACKs, deadline expiry for incomplete state, and a deterministic
closed-world carrier-adapter harness that executes the actual encrypted
protocol path. The harness injects loss, latency variation, reordering,
duplication, bursts, correlated failure-domain outages, envelope corruption,
ACK loss, ACK corruption, and recovery.

This is an engineering validation matrix, not a preregistered hypothesis test.
The impairment configuration was designed and inspected during implementation;
its 100/125 operation result must therefore remain descriptive. Two clean
executions produced identical observation and manifest hashes. The versioned
run also records 39 corrupted fragments and six corrupted ACKs, with eight
envelope-authentication rejections and six ACK-authentication rejections. The
different counts arise because corruption in an already-incomplete fragment
set never reaches the envelope authenticator.
