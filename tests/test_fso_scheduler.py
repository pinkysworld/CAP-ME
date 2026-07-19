from __future__ import annotations

import unittest

from capme.fso.scheduler import FSOScheduler, build_scheduler
from capme.fso.types import LaneProfile, Operation


def profiles() -> list[LaneProfile]:
    return [
        LaneProfile("generated-0", "generated_transport", "generated", 120, 0.78, 0.72, False),
        LaneProfile("generated-1", "generated_transport", "generated", 130, 0.76, 0.72, False),
        LaneProfile("ephemeral-0", "ephemeral_relay", "ephemeral-a", 150, 0.74, 0.92, False),
        LaneProfile("ephemeral-1", "ephemeral_relay", "ephemeral-b", 160, 0.72, 0.92, False),
        LaneProfile("permitted-0", "platform_controlled", "permitted", 70, 0.98, 0.98, True),
    ]


class FSOSchedulerTests(unittest.TestCase):
    def test_strict_trust_excludes_provider_controlled_lane(self) -> None:
        scheduler = build_scheduler("fso", profiles(), strict_trust=True, seed=4)
        for function, deadline in (("text", 5000), ("file", 30000), ("realtime", 450)):
            decision = scheduler.plan(Operation(function, b"x" * 100, deadline))
            self.assertNotIn("permitted-0", decision.lanes)

    def test_realtime_uses_redundancy(self) -> None:
        scheduler = build_scheduler("fso", profiles(), strict_trust=True, seed=5)
        decision = scheduler.plan(Operation("realtime", b"x" * 100, 450))
        self.assertGreaterEqual(decision.total_shards, 2)
        self.assertIn(decision.dispatch_mode, {"parallel", "hot_standby"})

    def test_no_redundancy_ablation_uses_one_lane(self) -> None:
        scheduler = build_scheduler(
            "fso_no_redundancy", profiles(), strict_trust=True, seed=6
        )
        decision = scheduler.plan(Operation("file", b"x" * 100, 30000))
        self.assertEqual(decision.total_shards, 1)
        self.assertEqual(decision.threshold, 1)

    def test_component_ablations_match_feedback_off_primary(self) -> None:
        for strategy in (
            "fso_fixed_code",
            "fso_no_semantics",
            "fso_no_diversity",
            "fso_no_redundancy",
        ):
            scheduler = build_scheduler(
                strategy, profiles(), strict_trust=True, seed=7
            )
            self.assertIsInstance(scheduler, FSOScheduler)
            self.assertFalse(scheduler.feedback, strategy)

    def test_no_diversity_does_not_force_same_domain_portfolio(self) -> None:
        candidates = [
            LaneProfile("shared-a", "generated_transport", "shared", 100, 0.20, 0.8, False),
            LaneProfile("shared-b", "generated_transport", "shared", 100, 0.20, 0.8, False),
            LaneProfile("independent", "ephemeral_relay", "independent", 100, 0.95, 0.8, False),
        ]
        scheduler = FSOScheduler(
            candidates,
            strict_trust=True,
            seed=8,
            diversity=False,
            feedback=False,
            adaptive_modes=False,
            cost_weights={function: 0.0 for function in ("text", "presence", "media", "file", "realtime")},
            latency_weights={function: 0.0 for function in ("text", "presence", "media", "file", "realtime")},
            burn_weight=0.0,
            correlation_penalty_weight=0.0,
        )
        decision = scheduler.plan(Operation("realtime", b"x", 450))
        domains = {scheduler.states[name].profile.failure_domain for name in decision.lanes}
        self.assertIn("independent", decision.lanes)
        self.assertEqual(len(domains), 2)

    def test_deadline_cost_baseline_matches_objective_inputs(self) -> None:
        scheduler = build_scheduler(
            "deadline_cost_failover", profiles(), strict_trust=True, seed=9
        )
        self.assertFalse(scheduler.feedback)
        self.assertFalse(scheduler.diversity)
        self.assertEqual(scheduler.burn_weight, 0.0)
        decision = scheduler.plan(Operation("realtime", b"x" * 100, 450))
        self.assertEqual(decision.strategy, "deadline_cost_failover")
        self.assertNotIn("permitted-0", decision.lanes)
        self.assertLessEqual(decision.total_shards, 2)


if __name__ == "__main__":
    unittest.main()
