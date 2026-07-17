"""Publication-boundary checks for the public software artifact.

The manuscript is maintained beside this repository for local authoring, but
it is not part of the public artifact.  These checks inspect both the index and
all reachable commits so that adding and later deleting a manuscript does not
silently make it available through Git history.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FORBIDDEN_PREFIXES = ("paper/", "output/pdf/", "private/")
ALLOWED_TEX_PREFIXES = ("artifacts/generated/",)
ALLOWED_PDF_PREFIXES = ("artifacts/generated/figures/",)
IGNORE_SENTINELS = (
    "paper/main.tex",
    "output/pdf/manuscript.pdf",
    "private/author-notes.txt",
)
STANDALONE_LATEX_MARKERS = (
    "\\documentclass",
    "\\begin{document}",
    "\\begin{abstract}",
    "\\maketitle",
)


@dataclass(frozen=True)
class BoundaryFinding:
    source: str
    path: str
    reason: str


def classify_public_path(path: str) -> str | None:
    """Return a rejection reason for a path outside the public boundary."""

    normalized = path.lstrip("./")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return "private manuscript directory"
    if normalized.lower().endswith(".tex") and not any(
        normalized.startswith(prefix) for prefix in ALLOWED_TEX_PREFIXES
    ):
        return "LaTeX source outside generated artifact tables"
    if normalized.lower().endswith(".pdf") and not any(
        normalized.startswith(prefix) for prefix in ALLOWED_PDF_PREFIXES
    ):
        return "PDF outside generated artifact figures"
    return None


def contains_standalone_latex(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in STANDALONE_LATEX_MARKERS)


def _git(root: Path, arguments: Iterable[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def _paths(root: Path, arguments: list[str]) -> list[str]:
    result = _git(root, arguments)
    return [line for line in result.stdout.splitlines() if line]


def _scan_tree(
    root: Path,
    *,
    source: str,
    paths: Iterable[str],
    content_ref: str,
) -> list[BoundaryFinding]:
    findings: list[BoundaryFinding] = []
    for path in paths:
        reason = classify_public_path(path)
        if reason:
            findings.append(BoundaryFinding(source, path, reason))
            continue
        if path.lower().endswith(".tex"):
            shown = _git(root, ["show", f"{content_ref}:{path}"], check=False)
            if shown.returncode == 0 and contains_standalone_latex(shown.stdout):
                findings.append(
                    BoundaryFinding(source, path, "standalone LaTeX manuscript markers")
                )
    return findings


def scan_public_boundary(root: Path) -> list[BoundaryFinding]:
    """Inspect the index, reachable history, and required ignore rules."""

    root = root.resolve()
    findings = _scan_tree(
        root,
        source="index",
        paths=_paths(root, ["ls-files", "--cached"]),
        content_ref="",
    )
    commits = _paths(root, ["rev-list", "--all"])
    for commit in commits:
        findings.extend(
            _scan_tree(
                root,
                source=commit,
                paths=_paths(root, ["ls-tree", "-r", "--name-only", commit]),
                content_ref=commit,
            )
        )
    for sentinel in IGNORE_SENTINELS:
        result = _git(
            root,
            ["check-ignore", "--quiet", "--no-index", sentinel],
            check=False,
        )
        if result.returncode != 0:
            findings.append(
                BoundaryFinding(".gitignore", sentinel, "required private path is not ignored")
            )
    return findings
