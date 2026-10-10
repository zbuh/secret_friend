VENV := .venv
BIN := $(VENV)/bin

$(BIN)/uvicorn: requirements.txt
ifneq ($(shell command -v uv),)
	uv venv -q --allow-existing $(VENV)
	uv pip install -q -p $(VENV) -r requirements.txt pytest httpx
else
	python3 -m venv $(VENV)
	$(BIN)/pip install -q -r requirements.txt pytest httpx
endif
	touch $@

install: $(BIN)/uvicorn

dev: install
	@if [ -z "$$token" ] && ! grep -qs '^token=' .env; then \
		echo "Sem token definido: a usar a password de desenvolvimento 'dev'"; \
		export token=dev; \
	fi; \
	$(BIN)/uvicorn app.main:app --reload --port 8080

test: install
	$(BIN)/python -m pytest -q

image:
	docker build -t secret_friend:latest .

.PHONY: install dev test image
