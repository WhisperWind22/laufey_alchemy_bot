# Repository Guidelines

## Project Structure & Module Organization
- `alchemy_tools/` holds the bot and helpers (database setup/fill, effect lookup, scoring, and search utilities). The main entry point is `alchemy_tools/main.py`.
- `tests/` contains pytest tests for helper modules (e.g., `test_utils.py`).
- `analyze_notebooks/` stores exploratory Jupyter notebooks.
- Data inputs live at the repo root: `young_alchemy.csv` and `all_effects_df.pkl`.
- `reset_db.py` rebuilds the local SQLite database (`alchemy.db`). Dependencies are managed by `pyproject.toml`/`poetry.lock`.

## Build, Test, and Development Commands
Use Poetry for environments and dependencies:

```bash
poetry install              # install runtime + dev dependencies
poetry run pytest           # run tests in ./tests
```

Common local workflows:

```bash
poetry run python alchemy_tools/main.py   # run the Telegram bot (requires API_TOKEN)
poetry run python alchemy_tools/db_setup.py  # create the schema and seed default effects
poetry run python alchemy_tools/db_fill.py   # load ingredient data from CSV
poetry run python reset_db.py             # full rebuild of alchemy.db
```

## Coding Style & Naming Conventions
- Python 3.12. Follow the existing style: 4-space indentation, `snake_case` for functions/variables, and `UPPER_CASE` for constants (e.g., `DB_PATH`).
- Keep helpers small and focused; place shared utilities in `alchemy_tools/utils.py`.
- Prefer descriptive module names matching their responsibility (e.g., `effects_tools.py`, `evaluate_ingredients.py`).

## Testing Guidelines
- Tests use pytest and live in `tests/` with `test_*.py` naming.
- Add or update tests when changing scoring logic, database queries, or utility helpers.
- Run `poetry run pytest` before opening a PR.

## Commit & Pull Request Guidelines
- Recent history shows short, imperative summaries with occasional type prefixes (e.g., `docs: ...`). Match that tone.
- PRs should include a concise summary, testing notes (or “not run” with reason), and call out any data/DB changes.
- If a change affects the bot’s behavior or database schema, document it in the PR description.

## Security & Configuration Tips
- The bot token is read from the `API_TOKEN` environment variable; never commit secrets.
- The SQLite database is stored at `./alchemy.db` by default. If you regenerate it, ensure the data files are present.
