.PHONY: vertical-slice corpora security quality e2e acceptance

vertical-slice:
	python3 run_vertical_slice.py --release 1.0.0-rc.1 --freeze

corpora:
	python3 expand_quality_corpora.py
	python3 generate_cross_layer_corpus.py -n 500
	python3 generate_ai_adversarial_corpus.py -n 1000

security:
	python3 run_sql_security_corpus.py
	python3 run_ai_adversarial.py
	python3 run_tenant_isolation.py
	python3 run_bypass_suite.py
	python3 run_data_leakage.py

quality:
	python3 expand_quality_corpora.py
	python3 run_quality_benchmark.py --require-full

e2e:
	python3 run_e2e_suite.py

acceptance:
	python3 generate_final_acceptance.py
