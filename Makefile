# Common development tasks. Run `make` or `make help` to list them.

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.DEFAULT_GOAL := help

.PHONY: help setup lint fmt typecheck test cov bench build binary image docs docs-serve clean

help: ## List the available targets.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create .venv and install evalkit with the dev and docs extras.
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]" -r docs/requirements.txt
	$(BIN)/pre-commit install

lint: ## Run ruff lint and the format check.
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

fmt: ## Format the code and apply safe lint fixes.
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

typecheck: ## Run mypy in strict mode.
	$(BIN)/mypy

test: ## Run the test suite.
	$(BIN)/pytest

cov: ## Run the test suite with coverage.
	$(BIN)/pytest --cov --cov-report=term

bench: ## Run the benchmarks and compare them with the committed baseline.
	$(BIN)/pytest benchmarks --benchmark-only --benchmark-json=.benchmark.json
	$(BIN)/python scripts/check_benchmarks.py .benchmark.json benchmarks/baseline.json

build: ## Build the wheel and sdist into dist/.
	$(BIN)/python -m pip install --quiet build
	$(BIN)/python -m build

binary: ## Build a standalone executable for this machine into dist/.
	$(BIN)/python -m pip install --quiet pyinstaller
	$(BIN)/python scripts/build_binary.py evalkit-local

image: ## Build the container image as evalkit:local.
	docker build -t evalkit:local .

docs: ## Build the documentation site into site/.
	$(BIN)/mkdocs build --strict

docs-serve: ## Serve the documentation site with live reload.
	$(BIN)/mkdocs serve

clean: ## Remove build output and caches.
	rm -rf build dist site .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml .benchmark.json mutants
