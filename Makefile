# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: Makefile

.DEFAULT_GOAL := test

# ------------------------------------------------------------
# Makefile for finance deploy workflow
# ------------------------------------------------------------

# Select environment: acc (default) or prod
ENV ?= acc

# Environment file (e.g. .env.prod, .env.acc)
ENV_FILE = .env.$(ENV)

# Load environment variables from the env file
include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

SRC_DIR := src/finance
TEST_DIR := tests
TOOL_DIR := tools
DB_DIR := db
OPS_DIR := ops
ALL_SOURCE_DIRS := $(SRC_DIR) $(TOOL_DIR) $(DB_DIR) $(OPS_DIR)
ALL_DIRS := $(ALL_SOURCE_DIRS) $(TEST_DIR)

# Python interpreter (evaluate on use)
PYTHON = python3

# evaluate once
SYSTEM_PYTHON := $(shell env -i \
	PATH="$(shell getconf PATH)" \
	LANG=C \
	LC_ALL=C \
	sh -c 'command -v python3')
ifeq ($(SYSTEM_PYTHON),)
	$(error Could not find system python3)
endif

# don't use build, it causes a circular depencency due to make's implicit search
CACHE_DIR := .cache
TEST_STAMP := $(CACHE_DIR)/tests-passed.stamp
LINT_STAMP := $(CACHE_DIR)/lint-passed.stamp
BUILD_STAMP := $(CACHE_DIR)/build.stamp

# Ensure the build directory exists
$(CACHE_DIR):
	mkdir -p $(CACHE_DIR)

ENV_VENV = $(ENV_ROOT)/venv

# ------------------------------------------------------------
# Help
# ------------------------------------------------------------

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make lint            - Run ruff linting and formatting"
	@echo "  make test            - Run unit tests"
	@echo "  make bump            - Bump version"
	@echo "  make build           - Build wheel"
	@echo "  make deploy          - Deploy to environment ($(ENV))"
	@echo "  make acceptance      - Deploy to acceptance environment"
	@echo "  make production      - Deploy to production environment (with systemd)"
	@echo "  make init-env        - Create environment root + venv"
	@echo "  make systemd         - Install systemd units"
	@echo "Configuration:"
	@echo "  Env file:            '$(ENV_FILE)'"
	@echo "  System python:       '$(SYSTEM_PYTHON)'"
	@echo "  Python:              '$$(which $(PYTHON))'"
	@echo "  Deploy target:       '$(ENV_ROOT)'"
	@echo "  Source folder:       '$(SRC_DIR)'"
	@echo "  Test folder:         '$(TEST_DIR)'"
	@echo "  Tools folder:        '$(TOOL_DIR)'"
	@echo "  DB folder:           '$(DB_DIR)'"
	@echo "  Ops folder:          '$(OPS_DIR)'"

# ------------------------------------------------------------
# Environment selection
# ------------------------------------------------------------

.PHONY: acceptance
acceptance:
	@$(MAKE) deploy ENV=acc

.PHONY: production
production:
	@$(MAKE) deploy ENV=prod
	@$(MAKE) systemd ENV=prod

# ------------------------------------------------------------
# Linting
# ------------------------------------------------------------

# cache dir is required but should not cause a trigger if changed
$(LINT_STAMP): | $(CACHE_DIR)
$(LINT_STAMP): $(shell find $(ALL_DIRS) -name '*.py')
	$(PYTHON) -m $(TOOL_DIR).add_license
	ruff check . --fix
	ruff format .
	touch $(LINT_STAMP)

lint: $(LINT_STAMP)

# ------------------------------------------------------------
# Testing
# ------------------------------------------------------------

$(TEST_STAMP): | $(CACHE_DIR)
$(TEST_STAMP): $(shell find $(SRC_DIR) $(TOOL_DIR) $(TEST_DIR) -name '*.py')
	$(PYTHON) -m pytest -c pytest.ini -q
	touch $(TEST_STAMP)

test: $(TEST_STAMP)

# ------------------------------------------------------------
# Version bump
# ------------------------------------------------------------

.PHONY: bump
bump:
	@NEW_VERSION=$$(scripts/bump_version.sh); \
	echo "Bumped version to $$NEW_VERSION"

# ------------------------------------------------------------
# Build wheel
# ------------------------------------------------------------

$(BUILD_STAMP): | $(CACHE_DIR)
$(BUILD_STAMP): $(shell find $(SRC_DIR) $(TOOL_DIR) -name '*.py') pyproject.toml
	rm -rf dist
	python -m build
	touch $(BUILD_STAMP)

build: lint test $(BUILD_STAMP)

# ------------------------------------------------------------
# Environment initialization
# ------------------------------------------------------------

# Create ENV_ROOT directory if missing

$(ENV_ROOT):
	mkdir -p $(ENV_ROOT)
	@echo "Target env:  $(ENV_ROOT)"


# Create venv if missing
$(ENV_VENV): | $(ENV_ROOT)
	@echo "Target venv: $(ENV_VENV)"
	@if [ ! -f "$(ENV_VENV)/pyvenv.cfg" ]; then \
		echo "=== Creating venv at $(ENV_VENV) ==="; \
		rm -rf "$(ENV_VENV)"; \
		$(SYSTEM_PYTHON) -m venv $(ENV_VENV); \
		$(ENV_VENV)/bin/python -m ensurepip; \
		$(ENV_VENV)/bin/pip install --upgrade pip wheel; \
	else \
		echo "=== Using existing venv at $(ENV_VENV) ==="; \
	fi

.PHONY: init-env
init-env: $(ENV_VENV)
	@echo "Environment initialized at $(ENV_ROOT)"

# ------------------------------------------------------------
# Deployment
# ------------------------------------------------------------

.PHONY: deploy
deploy: build init-env
	ENV_FILE=$(ENV_FILE) ENV_VENV=$(ENV_VENV) scripts/deploy.sh

# ------------------------------------------------------------
# Systemd installation
# ------------------------------------------------------------

.PHONY: systemd
systemd:
	scripts/install_systemd.sh

# ------------------------------------------------------------
# Clean up
# ------------------------------------------------------------

.PHONY: clean
clean:
	rm -rf .cache dist
