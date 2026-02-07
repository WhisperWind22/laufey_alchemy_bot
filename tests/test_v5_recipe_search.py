from __future__ import annotations

from pathlib import Path

import pytest

from alchemy_tools import v5_data as v5_data_mod
from alchemy_tools import v5_recipe_search


def test_v5_find_best_recipes_prefers_single_effect(monkeypatch, tmp_path: Path):
    # Keep the real v5 suppression module, but replace the ingredient/category/config
    # data with a tiny deterministic fixture.
    real = v5_data_mod.load_v5_data()

    ingredient_db = {
        "A": {"name": "A", "material": "", "main": "JUNK_A", "add1": "REQUIRED", "add2": "JUNK_A2", "add3": "JUNK_A3"},
        "B": {"name": "B", "material": "", "main": "JUNK_B", "add1": "JUNK_B1", "add2": "JUNK_B2", "add3": "JUNK_B3"},
        "C": {"name": "C", "material": "", "main": "JUNK_C", "add1": "JUNK_C1", "add2": "JUNK_C2", "add3": "JUNK_C3"},
    }

    def cat(kind: str):
        return {"kind": kind, "tier": None, "tags": []}

    effect_categories = {k: cat("junk") for k in [
        "JUNK_A", "JUNK_A2", "JUNK_A3",
        "JUNK_B", "JUNK_B1", "JUNK_B2", "JUNK_B3",
        "JUNK_C", "JUNK_C1", "JUNK_C2", "JUNK_C3",
    ]}
    effect_categories["REQUIRED"] = cat("required")

    suppression_cfg = {
        "max_final_effects": 4,
        "poison_antidote_rules": {"tier_rank": {"weak": 1, "medium": 2, "strong": 3, "deadly": 4}},
        "mutual_exclusive_pairs": [],
        "block_rules": [{"if_any_of": ["required"], "then_block": ["junk"], "note": "required suppresses junk"}],
    }

    patched = v5_data_mod.V5Data(
        data_dir=tmp_path,
        ingredient_db=ingredient_db,
        effect_categories=effect_categories,
        suppression_cfg=suppression_cfg,
        suppression_mod=real.suppression_mod,
    )

    monkeypatch.setattr(v5_data_mod, "_CACHE", patched, raising=False)
    monkeypatch.setattr(v5_recipe_search, "_TOKENS", None, raising=False)

    results = v5_recipe_search.find_best_recipes_for_effect(
        "REQUIRED",
        pool_size=20,
        max_seeds=8,
        max_results=3,
        time_budget_sec=1.0,
    )
    assert results
    assert results[0].effect_count == 1
    assert "REQUIRED" in results[0].final_effects

