# Laufey Alchemy Bot

Laufey Alchemy Bot is a Telegram bot that helps manage alchemical ingredients and craft potions. It stores user data in a local SQLite database and provides helper utilities to evaluate combinations of ingredients.

## Project Status

This repository contains a working prototype with basic command handlers and helper tools. It is not a finished product and some modules are experimental.

## Repository Structure

- **alchemy_tools/** – library with all bot utilities
  - `main.py` – entry point of the Telegram bot with all command handlers
  - `db_setup.py` – creates the SQLite schema and loads default effects
  - `db_fill.py` – fills the database with ingredient information from v4 JSON/CSV
  - `db_wrapper.py` – helper decorator to reuse a SQLite connection
  - `effects_tools.py` – queries for ingredient effects from the database
  - `effects_resolution.py` – resolves potion effects from selected ingredients
  - `evaluate_ingredients.py` – functions for scoring ingredient formulas
  - `find_ingredients.py` – algorithms for searching optimal ingredient sets
  - `utils.py` – small helpers such as `split_formula`
  - `recipes.py` – helper to store and retrieve user potion recipes
  - `user_ingredients.py` – tools to manage a user's ingredient list
- **tests/** – simple tests for individual helpers
  - `test_evaluate.py` – verifies the effect scoring logic
  - `test_utils.py` – checks utilities
- `pyproject.toml` / `poetry.lock` – project dependencies for Poetry
- **analyze_notebooks/** – Jupyter notebooks exploring effect calculation algorithms
- `reset_db.py` – recreate and populate the SQLite database using `ingredients_v4.json` and `effect_categories_v4.csv`
- `ingredients_v4.json` / `effect_categories_v4.csv` – v4 data files used for bot calculations

## Effect Resolution Algorithm (Разрешение эффектов)

The effect resolution logic lives in:

- `alchemy_tools/effects_resolution.py` → `resolve_potion_effects(selections)` where `selections` is a list of `(ingredient_id, add_index)`
- `effect_suppression_v4.py` → v4 suppression rules (MAX_EFFECTS = 4, poison/antidote collapse)

How it works, step by step:

1. For each selected ingredient instance, the main effect and the chosen additional effect are collected.
2. The v4 suppression engine classifies effects by category and applies rule-based cancellation.
3. Poisons/antidotes collapse to the strongest remaining tier.
4. Output includes the remaining active effects, a suppression log, and validity by the MAX_EFFECTS rule.

## Running Tests

Tests expect Python 3.12 and the dependencies listed in `pyproject.toml`. Run:

```bash
poetry install
pytest
```

## Usage

Create the SQLite database using `alchemy_tools/db_setup.py` and then run `alchemy_tools/main.py` with your Telegram API token in the `API_TOKEN` environment variable.
