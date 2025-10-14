.PHONY: setup test unit property integration smoke bench golden report ci

setup:
	pip install -U pip
	pip install -r requirements.txt
	pip install hypothesis pyjwt prometheus_client jsonschema

golden:
	GOLDEN_POR_OVERRIDE=true pytest -q tests/property/_golden_build.py
	python -c "import json,sys; from pathlib import Path; data=json.load(Path('assets/golden/golden_expected.json').open()); runs=data.get('runs', []); sys.exit('golden_expected.json must contain at least 30 runs' if len(runs)<30 else 0)"
	python -c "import json,sys; from pathlib import Path; runs=json.load(Path('assets/golden/golden_expected.json').open()).get('runs', []); failed=[r.get('input_id') for r in runs if not r.get('hits') or not r.get('proof_ok')]; sys.exit('golden runs missing proofs: '+', '.join(failed) if failed else 0)"
	python -c "import json; from pathlib import Path; runs=json.load(Path('assets/golden/golden_expected.json').open()).get('runs', []); print(f'golden built with {len(runs)} runs')"

unit:
	pytest -q tests/property/determinism_test.py tests/property/proofs_test.py

property:
	pytest -q tests/property

integration:
	pytest -q tests/integration

smoke:
	pytest -q tests/property/security_smoke_test.py

bench:
	python -u tests/bench/bench_runner.py || { tail -n +1 assets/bench/bench_report.json 2>/dev/null || true; exit 1; }
	jq -e '(.status=="ok")' assets/bench/bench_report.json >/dev/null
	jq -e '(.indexed_points // 0) > 0' assets/bench/bench_report.json >/dev/null
	jq -e '(((.latency_ms // {}) | (.p95 // 0)) > 0)' assets/bench/bench_report.json >/dev/null
	python -u tests/bench/recall_eval.py
	jq -e '(.generated_at != null)' assets/bench/recall_report.json >/dev/null
	jq -e '((.modes|length) >= 2) and ([.modes[].recall] | all(. > 0))' assets/bench/recall_report.json >/dev/null

report:
	python tools/dump_metrics.py || true

test: unit property integration smoke

ci: setup test bench golden report
