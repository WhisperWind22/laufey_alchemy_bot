# Changes (2026-01-27)

- Added effect search command (`/search_effects`) with main vs. additional effect labeling and order display.
- Added a `/craft_optimal` alias and a menu button for optimal crafting by effect.
- Added global update logging and an error handler; log level set to DEBUG for more detail.
- Ensured users always get all ingredients when crafting, listing, or opening the ingredient keyboard.
- Added settings to cap optimal formula size to 3 or 5 ingredients (`/settings`) and enforced it in `/craft_optimal_from_formula`.
- Added tests for effect search and user settings.

# Changes (2026-02-01)

- Switched effect suppression to catalog-based classification using `ingredient_effect_categories.csv`, keeping heuristics as fallback.
- Updated suppression logic for anti-deadly antidote to only allow specified poison combinations.
- Expanded tag display/order to include newly categorized effect tags (energy, mental, temptation, intoxication).

# Changes (2026-02-02)

- Updated effect resolution to v4 suppression rules with MAX_EFFECTS=4 and poison/antidote collapsing.
- Switched database rebuild to v4 data sources (`ingredients_v4.json`, `effect_categories_v4.csv`).
- Allowed duplicate ingredients with different add effects in the crafting flow.
- Simplified optimal recipe search/scoring to use v4 suppression output.
