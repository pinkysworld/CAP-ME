import json
from pathlib import Path

from capme.fso.reviews import build_review_bundle


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = build_review_bundle(root, root / "field" / "review-bundle-manifest.json")
    print(json.dumps(result, sort_keys=True))
