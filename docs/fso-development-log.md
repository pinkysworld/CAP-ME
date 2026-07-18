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

## Final independent-sample result and canonical policy

The versioned final replay contains 1,497,600 operation decisions. The original
feedback-enabled policy reaches AUAC 0.9123 (95% seed-bootstrap CI
[0.9068, 0.9173]) and byte overhead 1.246. The feedback-off policy reaches
0.9148 [0.9091, 0.9199] at overhead 1.238 and is now canonical FSO. Session
failover reaches 0.8961 [0.8902, 0.9016] at overhead 1.212; canonical FSO minus
session failover is 0.0187 [0.0164, 0.0214].

The ablations retain two results unfavorable to the full mechanism:

- non-semantic two-lane duplication reaches AUAC 0.9270 but overhead 2.000,
  61.5% above canonical FSO; and
- enabling feedback reaches 0.9123, with paired canonical-minus-feedback
  difference 0.0024 [0.0008, 0.0042].

Dynamic plan selection, diversity, and redundancy are beneficial within this
trace; the current feedback rule is not. The next feedback design must be
developed on new data rather than tuned on these confirmation seeds.

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
