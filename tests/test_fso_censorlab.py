from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from capme.fso.censorlab import (
    build_ethernet_ipv4_frame,
    parse_censorlab_output,
    run_study,
)


ROOT = Path(__file__).resolve().parents[1]


class FSOCensorLabTests(unittest.TestCase):
    def test_output_parser_handles_actions_and_timing(self) -> None:
        output = "\n".join(
            (
                "1: Ok(Drop)",
                "4: Ok(Reset { src_port: 443 })",
                "7: Err(malformed packet)",
                "Pcap mode took 91us to process the file (123us including I/O)",
            )
        )
        parsed = parse_censorlab_output(output)
        self.assertTrue(parsed.decisions[1].blocked)
        self.assertEqual(parsed.decisions[4].action, "reset")
        self.assertEqual(parsed.errors[7], "malformed packet")
        self.assertEqual(parsed.processing_us, 91)
        self.assertEqual(parsed.total_us, 123)

    def test_frame_builder_is_deterministic_and_nonempty(self) -> None:
        first = build_ethernet_ipv4_frame(
            b"synthetic",
            transport="tcp",
            src_ip="10.0.0.1",
            dst_ip="203.0.113.9",
            src_port=35000,
            dst_port=8443,
            identification=7,
            sequence=11,
        )
        second = build_ethernet_ipv4_frame(
            b"synthetic",
            transport="tcp",
            src_ip="10.0.0.1",
            dst_ip="203.0.113.9",
            src_port=35000,
            dst_port=8443,
            identification=7,
            sequence=11,
        )
        self.assertEqual(first, second)
        self.assertGreater(len(first), len(b"synthetic"))
        self.assertEqual(first[12:14], b"\x08\x00")

    def test_closed_study_reconstructs_messages_and_normalizes_indices(self) -> None:
        source = json.loads(
            (ROOT / "configs" / "fso-censorlab.json").read_text(encoding="utf-8")
        )
        source["epochs"] = 2
        source["operations_per_epoch"] = 5

        def backend(_pcap: Path, labels: Path, _epoch: int) -> str:
            with labels.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            lines = []
            for row in rows:
                should_drop = row["role"] == "calibration" or (
                    row["transport"] == "tcp" and row["server_port"] == "8443"
                )
                if should_drop:
                    # Simulate a CensorLab version whose displayed PCAP index
                    # is one greater than CAP-ME's labels.
                    lines.append(f"{int(row['packet_index']) + 1}: Ok(Drop)")
            lines.append(
                "Pcap mode took 100us to process the file (130us including I/O)"
            )
            return "\n".join(lines) + "\n"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(json.dumps(source), encoding="utf-8")
            first = root / "first"
            second = root / "second"
            first_manifest = run_study(config, first, backend)
            second_manifest = run_study(config, second, backend)

            self.assertEqual(
                (first / "operations.csv").read_bytes(),
                (second / "operations.csv").read_bytes(),
            )
            self.assertEqual(
                (first / "packet-decisions.csv").read_bytes(),
                (second / "packet-decisions.csv").read_bytes(),
            )
            self.assertEqual(
                (first / "traces" / "epoch-00.pcap").read_bytes(),
                (second / "traces" / "epoch-00.pcap").read_bytes(),
            )

        self.assertTrue(first_manifest["closed_world"])
        self.assertTrue(first_manifest["offline_pcap_only"])
        self.assertEqual(first_manifest["external_destinations"], 0)
        self.assertEqual(first_manifest["live_interfaces"], 0)
        self.assertEqual(first_manifest["pcap_index_offsets"], [1])
        self.assertEqual(first_manifest["provider_controlled_attempts"], 0)
        self.assertGreater(first_manifest["censored_packets"], 0)
        self.assertGreater(first_manifest["successful_operations"], 0)
        self.assertEqual(
            first_manifest["operations_sha256"],
            second_manifest["operations_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
