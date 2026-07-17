from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from capme.fso.lab import run_lab


ROOT = Path(__file__).resolve().parents[1]


class FSODeterministicLabTests(unittest.TestCase):
    def test_complete_protocol_path_is_byte_reproducible(self) -> None:
        config = ROOT / "configs" / "fso-deterministic-lab.json"
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first_manifest = run_lab(config, first)
            second_manifest = run_lab(config, second)
            self.assertEqual(
                (first / "observations.csv").read_bytes(),
                (second / "observations.csv").read_bytes(),
            )
            self.assertEqual(
                (first / "manifest.json").read_bytes(),
                (second / "manifest.json").read_bytes(),
            )
        self.assertEqual(first_manifest, second_manifest)
        self.assertTrue(first_manifest["deterministic"])
        self.assertTrue(first_manifest["closed_world"])
        self.assertEqual(first_manifest["external_destinations"], 0)
        self.assertEqual(first_manifest["provider_controlled_attempts"], 0)
        self.assertEqual(
            first_manifest["envelopes"], first_manifest["unique_nonces"]
        )
        self.assertEqual(first_manifest["fragment_reassembly_inflight_at_end"], 0)
        failures = first_manifest["failure_injection"]
        self.assertGreater(failures["dropped_fragments"], 0)
        self.assertGreater(failures["data_auth_rejections"], 0)
        self.assertGreater(failures["ack_auth_rejections"], 0)

    def test_packets_arriving_after_function_deadlines_do_not_succeed(self) -> None:
        config = json.loads(
            (ROOT / "configs" / "fso-deterministic-lab.json").read_text(
                encoding="utf-8"
            )
        )
        config["operations_per_phase"] = 5
        config["phases"] = [config["phases"][0]]
        for lane in config["lanes"]:
            lane["latency_ms"] = 100_000
            lane["jitter_ms"] = 0
            lane["loss_rate"] = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "late.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            manifest = run_lab(config_path, root / "result")
        self.assertEqual(manifest["successful_operations"], 0)


if __name__ == "__main__":
    unittest.main()
