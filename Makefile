# Backend tests

.PHONY: test test-unit test-integration eval-retrieval check-citations

test:
	cd backend && pytest -q

test-unit:
	cd backend && pytest -q -m "not integration"

test-integration:
	cd backend && pytest -q -m integration

eval-retrieval:
	cd backend && python scripts/eval_retrieval.py --hybrid --fail-on-miss

check-citations:
	cd backend && python scripts/check_citation_quality.py

check-store-sync:
	cd backend && python scripts/check_store_sync.py
