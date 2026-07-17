from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.fso.deployment import validate_authorization

parser = argparse.ArgumentParser()
parser.add_argument("manifest", type=Path)
args = parser.parse_args()
result = validate_authorization(args.manifest)
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["authorization_complete"] else 2)
