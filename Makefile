SHELL := /bin/bash

# =============================================================================
# Configuration and Environment Variables
# =============================================================================

.DEFAULT_GOAL := help
.ONESHELL:
.EXPORT_ALL_VARIABLES:
MAKEFLAGS += --no-print-directory

# -----------------------------------------------------------------------------
# Display Formatting and Colors
# -----------------------------------------------------------------------------
BLUE := $(shell printf "\033[1;34m")
GREEN := $(shell printf "\033[1;32m")
RED := $(shell printf "\033[1;31m")
YELLOW := $(shell printf "\033[1;33m")
NC := $(shell printf "\033[0m")
INFO := $(shell printf "$(BLUE)ℹ$(NC)")
OK := $(shell printf "$(GREEN)✓$(NC)")
WARN := $(shell printf "$(YELLOW)⚠$(NC)")
ERROR := $(shell printf "$(RED)✖$(NC)")

# =============================================================================
# Help and Documentation
# =============================================================================

.PHONY: help
help:                                               ## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# =============================================================================
# Installation and Environment Setup
# =============================================================================

.PHONY: install-uv
install-uv:                                         ## Install latest version of uv
	@echo "${INFO} Installing uv..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
	@echo "${OK} UV installed successfully"

.PHONY: install
install: destroy clean                              ## Install the project and all dependencies
	@echo "${INFO} Starting fresh installation..."
	@uv python pin 3.10 >/dev/null 2>&1
	@uv venv >/dev/null 2>&1
	@uv sync --all-extras --dev
	@echo "${OK} Installation complete!"

.PHONY: destroy
destroy:                                            ## Destroy the virtual environment
	@echo "${INFO} Destroying virtual environment..."
	@rm -rf .venv
	@echo "${OK} Virtual environment destroyed"

# =============================================================================
# Dependency Management
# =============================================================================

.PHONY: upgrade
upgrade:                                            ## Upgrade all dependencies to latest stable versions
	@echo "${INFO} Updating all dependencies..."
	@uv lock --upgrade
	@echo "${OK} Dependencies updated"

.PHONY: lock
lock:                                               ## Rebuild lockfiles from scratch
	@echo "${INFO} Rebuilding lockfiles..."
	@uv lock --upgrade >/dev/null 2>&1
	@echo "${OK} Lockfiles updated"

# =============================================================================
# Build and Release
# =============================================================================

.PHONY: build
build:                                              ## Build the package
	@echo "${INFO} Building package..."
	@uv build >/dev/null 2>&1
	@echo "${OK} Package build complete"

.PHONY: release
release:                                            ## Bump version and create release tag
	@echo "${INFO} Preparing for release..."
	@make clean
	@make build
	@uv run bump-my-version bump $(bump)
	@uv lock --upgrade-package hatch-mojo >/dev/null 2>&1
	@echo "${OK} Release complete"

# =============================================================================
# Cleaning and Maintenance
# =============================================================================

.PHONY: clean
clean:                                              ## Cleanup temporary build artifacts
	@echo "${INFO} Cleaning working directory..."
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ dist/ .eggs/ .coverage coverage.xml coverage.json htmlcov/ .mypy_cache .hatch_mojo >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -name '*.egg-info' -exec rm -rf {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -type f -name '*.egg' -exec rm -f {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -name '*.pyc' -exec rm -f {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -name '*.pyo' -exec rm -f {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -name '*~' -exec rm -f {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git \) -prune -o -type d -name '__pycache__' -exec rm -rf {} + >/dev/null 2>&1
	@echo "${OK} Working directory cleaned"

# =============================================================================
# Testing and Quality Checks
# =============================================================================

.PHONY: test
test:                                               ## Run the tests
	@echo "${INFO} Running test cases..."
	@uv run pytest tests
	@echo "${OK} Tests complete"

.PHONY: coverage
coverage:                                           ## Run tests with coverage report
	@echo "${INFO} Running tests with coverage..."
	@uv run pytest --cov --quiet
	@uv run coverage html >/dev/null 2>&1
	@uv run coverage xml >/dev/null 2>&1
	@echo "${OK} Coverage report generated"

# -----------------------------------------------------------------------------
# Type Checking
# -----------------------------------------------------------------------------

.PHONY: mypy
mypy:                                               ## Run mypy
	@echo "${INFO} Running mypy..."
	@uv run mypy
	@echo "${OK} Mypy checks passed"

.PHONY: pyright
pyright:                                            ## Run pyright
	@echo "${INFO} Running pyright..."
	@uv run pyright
	@echo "${OK} Pyright checks passed"

.PHONY: type-check
type-check: mypy pyright                            ## Run all type checking

# -----------------------------------------------------------------------------
# Linting and Formatting
# -----------------------------------------------------------------------------

.PHONY: slotscheck
slotscheck:                                         ## Run slotscheck
	@echo "${INFO} Running slotscheck..."
	@uv run slotscheck hatch_mojo
	@echo "${OK} Slotscheck complete"

.PHONY: fix
fix:                                                ## Run code formatters
	@echo "${INFO} Running code formatters..."
	@uv run ruff check --fix --unsafe-fixes
	@uv run ruff format .
	@echo "${OK} Code formatting complete"

.PHONY: lint
lint: fix type-check slotscheck                     ## Run all linting checks
	@echo "${OK} All linting checks passed"

.PHONY: check-all
check-all: lint test coverage                       ## Run all checks (lint, test, coverage)
	@echo "${OK} All checks passed"

# =============================================================================
# End of Makefile
# =============================================================================
