# Project Instructions (AGENTS.md)

## Overview

<!-- Describe your project here. What does it do? What are the main components? -->

## Directory Structure

```
.
├── src/          # Source code
├── tests/        # Tests
└── docs/         # Documentation
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Coding Guidelines

- Use clear, descriptive variable names
- Add docstrings to public functions and classes
- Write tests for new functionality
- Keep functions small and focused

## Agent Instructions

- Read relevant files before making changes
- Use edit for small surgical changes, write for new files or complete rewrites
- Run tests after making changes: `bash('uv run pytest -x')`
- Summarize what you did at the end of each task
