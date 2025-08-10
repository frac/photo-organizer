.PHONY: help install install-user install-global test format lint clean dev

# Default target
help:
	@echo "Photo Organizer - Available Commands:"
	@echo ""
	@echo "  install-user   Install to ~/.local/bin (recommended)"
	@echo "  install-global Install to /usr/local/bin (requires sudo)"
	@echo "  test          Run all tests"
	@echo "  format        Format code with black"
	@echo "  lint          Run linting checks"
	@echo "  clean         Clean build artifacts"
	@echo "  dev           Install for development"
	@echo ""
	@echo "Examples:"
	@echo "  make install-user"
	@echo "  make test"
	@echo "  make format lint"

# Installation targets
install: install-user

install-user:
	@echo "Installing photo-organizer for current user..."
	./install.sh --user

install-global:
	@echo "Installing photo-organizer globally..."
	./install.sh --global

# Development targets
dev:
	@echo "Setting up development environment..."
	uv sync --dev

test:
	@echo "Running tests..."
	uv run pytest -v

test-coverage:
	@echo "Running tests with coverage..."
	uv run pytest --cov=photo_organizer --cov-report=term-missing --cov-report=html

# Code quality
format:
	@echo "Formatting code..."
	uv run black .

lint:
	@echo "Running linting checks..."
	uv run ruff check .
	uv run black --check .

fix:
	@echo "Auto-fixing code issues..."
	uv run ruff check --fix .
	uv run black .

# Cleanup
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build
build:
	@echo "Building package..."
	uv build

# Show project info
info:
	@echo "Photo Organizer Project Information:"
	@echo "  Python version: $(shell python --version)"
	@echo "  uv version: $(shell uv --version)"
	@echo "  Project path: $(shell pwd)"
	@echo ""
	@echo "Dependencies:"
	@uv tree --depth 1