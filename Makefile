PYTHON ?= python3
PYTHONPATH := src
RAW := results/raw/study
PROCESSED := results/processed/study
ARTIFACT_GENERATED := artifacts/generated

.PHONY: test smoke study analyze artifacts fso-confirmation-source fso-confirmation fso-deterministic-lab fso-loopback field-check public-boundary validate

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme run --config configs/smoke.json --output results/raw/smoke
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme ablate --config configs/smoke.json --output results/raw/smoke
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_analysis.py --raw results/raw/smoke --processed results/processed/smoke

study:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme run --config configs/study.json --output $(RAW)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme ablate --config configs/study.json --output $(RAW)

analyze:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_analysis.py --raw $(RAW) --processed $(PROCESSED)

artifacts:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_artifacts.py --processed $(PROCESSED) --artifact-generated $(ARTIFACT_GENERATED)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_fso_artifacts.py --processed results/processed/fso/confirmation --loopback results/processed/fso/loopback/manifest.json --lab results/processed/fso/deterministic-lab/manifest.json --artifact-generated $(ARTIFACT_GENERATED)

fso-confirmation-source:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme run --config configs/fso-confirmation-source.json --output results/raw/fso-confirmation-source
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/prepare_fso_traces.py prepare-traces --source results/raw/fso-confirmation-source/observations.csv --output results/processed/fso/confirmation/lane_trace_probabilities.csv

fso-confirmation:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_study.py run --config configs/fso-confirmation.json --raw results/raw/fso-confirmation --processed results/processed/fso/confirmation

fso-deterministic-lab:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_deterministic_lab.py --config configs/fso-deterministic-lab.json --output results/processed/fso/deterministic-lab

fso-loopback:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_loopback.py --config configs/fso-loopback.json --output results/processed/fso/loopback

field-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_field_authorization.py field/loopback-authorization.json

public-boundary:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_public_boundary.py

validate: public-boundary test
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_artifact.py
