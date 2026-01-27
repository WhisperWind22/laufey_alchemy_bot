# Changes (2026-01-27)

- Added effect search command (`/search_effects`) with main vs. additional effect labeling and order display.
- Added a `/craft_optimal` alias and a menu button for optimal crafting by effect.
- Added global update logging and an error handler; log level set to DEBUG for more detail.
- Ensured users always get all ingredients when crafting, listing, or opening the ingredient keyboard.
- Added settings to cap optimal formula size to 3 or 5 ingredients (`/settings`) and enforced it in `/craft_optimal_from_formula`.
- Added tests for effect search and user settings.
