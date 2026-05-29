# ------------------------------------------------------------
# Makefile for finance deploy workflow
# ------------------------------------------------------------

# Select environment: prod (default) or acc
ENV ?= prod

# Environment file (e.g. .env.prod, .env.acc)
ENV_FILE = .env.$(ENV)

# Load environment variables from the env file
include $(ENV_FILE)
export $(shell sed 's/=.*//' $(ENV_FILE))

# Python interpreter
PYTHON = python3

# ------------------------------------------------------------
# Help
# ------------------------------------------------------------

.PHONY: help
help:
    @echo "Available targets:"
    @echo "  make lint            - Run ruff linting and formatting"
    @echo "  make bump            - Bump version"
    @echo "  make build           - Build wheel"
    @echo "  make deploy          - Deploy to environment ($(ENV))"
    @echo "  make acceptance      - Deploy to acceptance environment"
    @echo "  make prod            - Deploy to production environment"
    @echo "  make init-env        - Create environment root + venv"
    @echo "  make systemd         - Install systemd units"

# ------------------------------------------------------------
# Environment selection
# ------------------------------------------------------------

.PHONY: acceptance
acceptance:
    @$(MAKE) deploy ENV=acc

.PHONY: prod
prod:
    @$(MAKE) deploy ENV=prod
	@$(MAKE) systemd ENV=prod

# ------------------------------------------------------------
# Linting
# ------------------------------------------------------------

.PHONY: lint
lint:
    $(PYTHON) -m tools.add_license
    ruff check . --fix
    ruff format .

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

.PHONY: build
build: lint
    $(PYTHON) -m build

# ------------------------------------------------------------
# Environment initialization
# ------------------------------------------------------------

# Create ENV_ROOT directory if missing
$(ENV_ROOT):
    mkdir -p $(ENV_ROOT)

# Create venv if missing
$(ENV_VENV): | $(ENV_ROOT)
    python3 -m venv $(ENV_VENV)
    $(ENV_VENV)/bin/python -m ensurepip
    $(ENV_VENV)/bin/pip install --upgrade pip wheel

.PHONY: init-env
init-env: $(ENV_VENV)
    @echo "Environment initialized at $(ENV_ROOT)"

# ------------------------------------------------------------
# Deployment
# ------------------------------------------------------------

.PHONY: deploy
deploy: build init-env
    ENV_FILE=$(ENV_FILE) scripts/deploy.sh

# ------------------------------------------------------------
# Systemd installation
# ------------------------------------------------------------

.PHONY: systemd
systemd:
    scripts/install_systemd.sh
