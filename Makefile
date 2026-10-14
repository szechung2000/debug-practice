PY ?= python3
S ?=

.PHONY: help setup list start verify grade reset history test check-key

help:
	@echo "make setup              create .venv and install requirements"
	@echo "make list               list the scenarios"
	@echo "make start   S=01       new attempt: branch, fresh data, incident ticket"
	@echo "make verify  S=01       run the hidden checks (asks for the passphrase)"
	@echo "make grade   S=01       score the fix and your AI interaction"
	@echo "make reset   S=01       restore the scenario to its original state"
	@echo "make history            scores of earlier attempts"
	@echo "make test               visible tests of all scenarios"

setup:
	$(PY) -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	@echo "Activate with: source .venv/bin/activate"

list:
	@$(PY) tools/practice.py list

start:
	@$(PY) tools/practice.py start $(S)

verify:
	@$(PY) tools/practice.py verify $(S)

grade:
	@$(PY) tools/practice.py grade $(S)

reset:
	@$(PY) tools/practice.py reset $(S)

history:
	@$(PY) tools/practice.py history

check-key:
	@$(PY) tools/keyvault.py check

test:
	@for d in scenarios/*/; do \
		echo "== $$d"; \
		(cd $$d && $(PY) data/generate.py >/dev/null && $(PY) -m pytest -q -p no:cacheprovider tests) || exit 1; \
	done
