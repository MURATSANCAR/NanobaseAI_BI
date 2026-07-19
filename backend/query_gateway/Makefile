.PHONY: test test-unit test-corpus test-oracle-corpus install

PYTHON ?= ../.venv/bin/python
export PYTHONPATH := ..

install:
	uv pip install --python $(PYTHON) -r requirements.txt

test-unit:
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) -m pytest tests/unit tests/property -q

test-corpus:
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) tests/security/generate_corpus.py
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) -m pytest tests/security/test_malicious_corpus.py -q

test-oracle-corpus:
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) tests/security/generate_oracle_corpus.py
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) tests/security/generate_oracle_benchmark.py
	QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false $(PYTHON) -m pytest tests/security/test_oracle_malicious_corpus.py tests/unit/oracle -q

test: test-unit test-corpus test-oracle-corpus
