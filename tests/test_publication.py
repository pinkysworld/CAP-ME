from __future__ import annotations

import unittest

from capme.publication import classify_public_path, contains_standalone_latex


class PublicationBoundaryTests(unittest.TestCase):
    def test_private_paths_are_rejected(self) -> None:
        self.assertIsNotNone(classify_public_path("paper/main.tex"))
        self.assertIsNotNone(classify_public_path("output/pdf/submission.pdf"))
        self.assertIsNotNone(classify_public_path("private/reviewer-notes.txt"))

    def test_only_artifact_tex_and_pdf_locations_are_allowed(self) -> None:
        self.assertIsNone(classify_public_path("artifacts/generated/main_results.tex"))
        self.assertIsNone(
            classify_public_path("artifacts/generated/figures/survival_curves.pdf")
        )
        self.assertIsNotNone(classify_public_path("docs/supplement.tex"))
        self.assertIsNotNone(classify_public_path("results/manuscript.pdf"))

    def test_standalone_latex_is_distinguished_from_generated_tables(self) -> None:
        self.assertTrue(contains_standalone_latex("\\documentclass{article}"))
        self.assertTrue(contains_standalone_latex("\\begin{abstract} bounded claim"))
        self.assertFalse(contains_standalone_latex("\\begin{tabular}{lr} A & B"))


if __name__ == "__main__":
    unittest.main()
