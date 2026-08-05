.PHONY: help requirements test quality install

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

install:  ## Install the plugin in editable mode
	pip install -e .

requirements:  ## Install test/dev requirements
	pip install -r requirements/test.in
	pip install -e .

test:  ## Run the test suite
	pytest

quality:  ## Run linters
	isort --check-only admin_portal
	pylint admin_portal || true
