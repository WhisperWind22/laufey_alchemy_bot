# Laufey Alchemy Bot

Laufey Alchemy Bot is a Telegram bot that helps manage alchemical ingredients and craft potions. It stores user data in a local SQLite database and provides helper utilities to evaluate combinations of ingredients.

## Project Status

This repository contains a working prototype with basic command handlers and helper tools. It is not a finished product and some modules are experimental.

## Repository Structure

- **alchemy_tools/** – library with all bot utilities
  - `main.py` – entry point of the Telegram bot with all command handlers
  - `db_setup.py` – creates the SQLite schema and loads default effects
  - `db_fill.py` – fills the database with ingredient information from CSV
  - `db_wrapper.py` – helper decorator to reuse a SQLite connection
  - `effects_tools.py` – queries for ingredient effects from the database
  - `evaluate_ingredients.py` – functions for scoring ingredient formulas
  - `find_ingredients.py` – algorithms for searching optimal ingredient sets
  - `utils.py` – small helpers such as `split_formula`
- **tests/** – simple tests for individual helpers
  - `test_evaluate.py` – verifies the effect scoring logic
  - `test_utils.py` – checks utilities
- `pyproject.toml` / `poetry.lock` – project dependencies for Poetry

## Running Tests

Tests expect Python 3.12 and the dependencies listed in `pyproject.toml`. Run:

```bash
poetry install
pytest
```

## Usage

Create the SQLite database using `alchemy_tools/db_setup.py` and then run `alchemy_tools/main.py` with your Telegram API token in the `API_TOKEN` environment variable.

