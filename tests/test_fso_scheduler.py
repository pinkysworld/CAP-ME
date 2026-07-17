from __future__ import annotations

import unittest

from capme.fso.scheduler import build_scheduler
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


if __name__ == "__main__":
    unittest.main()
