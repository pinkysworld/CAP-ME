from __future__ import annotations

import unittest

from capme.fso.study import _unit_uniform


class FSOStudyTests(unittest.TestCase):
    def test_common_random_draw_is_stable_and_scoped(self) -> None:
        first = _unit_uniform(4001, 3, "text", 7, "generated-0", "lane")
        second = _unit_uniform(4001, 3, "text", 7, "generated-0", "lane")
        other = _unit_uniform(4001, 3, "text", 7, "ephemeral-0", "lane")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertGreater(first, 0.0)
        self.assertLess(first, 1.0)


if __name__ == "__main__":
    unittest.main()
