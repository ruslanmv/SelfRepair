.PHONY: install dev test lint format api clean docker-build docker-run

install:
	python -m pip install -U pip
	python -m pip install -e .

dev:
	python -m pip install -U pip
	python -m pip install -e ".[all]"

test:
	pytest

lint:
	ruff check selfrepair backend tests
	mypy selfrepair backend

format:
	ruff check --fix selfrepair backend tests

api:
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info htmlcov .coverage

docker-build:
	docker build -t selfrepair-repo:latest .

docker-run:
	docker run --rm -p 8000:8000 -e DRY_RUN=true selfrepair-repo:latest
