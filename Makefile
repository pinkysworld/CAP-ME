PYTHON ?= python3
PYTHONPATH := src
RAW := results/raw/study
PROCESSED := results/processed/study
ARTIFACT_GENERATED := artifacts/generated

.PHONY: test smoke study analyze robustness-smoke robustness artifacts fso-confirmation-source fso-confirmation fso-structure-replay fso-feedback-source fso-feedback-evaluation fso-deterministic-lab fso-loopback fso-multihost fso-multihost-repeat fso-scalability field-check public-boundary validate

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

robustness-smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_robustness_study.py --config configs/robustness-smoke.json --output results/raw/robustness-smoke

robustness:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_robustness_study.py --config configs/robustness.json --output results/processed/robustness

artifacts:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_artifacts.py --processed $(PROCESSED) --artifact-generated $(ARTIFACT_GENERATED)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_fso_artifacts.py --processed results/processed/fso/confirmation --loopback results/processed/fso/loopback/manifest.json --lab results/processed/fso/deterministic-lab/manifest.json --artifact-generated $(ARTIFACT_GENERATED)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_robustness_artifacts.py --processed results/processed/robustness --artifact-generated $(ARTIFACT_GENERATED)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_fso_structure_artifacts.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/generate_evidence_manifest.py

fso-confirmation-source:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme run --config configs/fso-confirmation-source.json --output results/raw/fso-confirmation-source
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/prepare_fso_traces.py prepare-traces --source results/raw/fso-confirmation-source/observations.csv --output results/processed/fso/confirmation/lane_trace_probabilities.csv

fso-confirmation:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_study.py run --config configs/fso-confirmation.json --raw results/raw/fso-confirmation --processed results/processed/fso/confirmation

fso-structure-replay:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_structure_replay.py --config configs/fso-structure-replay.json --raw results/raw/fso-structure-replay --processed results/processed/fso/structure-replay

fso-feedback-source:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m capme run --config configs/fso-feedback-source.json --output results/raw/fso-feedback-source
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/prepare_fso_traces.py prepare-traces --source results/raw/fso-feedback-source/observations.csv --output results/processed/fso/feedback-evaluation/lane_trace_probabilities.csv

fso-feedback-evaluation:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_study.py run --config configs/fso-feedback-evaluation.json --raw results/raw/fso-feedback-evaluation --processed results/processed/fso/feedback-evaluation
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/analyze_feedback_evaluation.py

fso-deterministic-lab:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_deterministic_lab.py --config configs/fso-deterministic-lab.json --output results/processed/fso/deterministic-lab

fso-loopback:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_loopback.py --config configs/fso-loopback.json --output results/processed/fso/loopback

fso-multihost:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_multihost.py --config configs/fso-multihost.json --output results/processed/fso/multihost

fso-multihost-repeat:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_multihost.py --config configs/fso-multihost.json --output results/processed/fso/multihost-repeat
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/compare_multihost_runs.py --first results/processed/fso/multihost --second results/processed/fso/multihost-repeat --output results/processed/fso/multihost/repeatability.json

fso-scalability:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/run_fso_scalability.py --config configs/fso-scalability.json --output results/processed/fso/scalability

field-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_field_authorization.py field/loopback-authorization.json

public-boundary:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_public_boundary.py

validate: public-boundary test
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) analysis/validate_artifact.py
