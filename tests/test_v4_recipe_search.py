from alchemy_tools.v4_recipe_search import find_best_recipes_for_effect


def test_find_best_recipes_sorted_by_effect_count():
    # Pick a canonical effect that exists in v4 data.
    results = find_best_recipes_for_effect(
        "Восстанавливает энергию",
        max_results=3,
        pool_size=35,
        max_seeds=6,
        time_budget_sec=2.0,
    )
    assert results
    counts = [r.effect_count for r in results]
    assert counts == sorted(counts)
