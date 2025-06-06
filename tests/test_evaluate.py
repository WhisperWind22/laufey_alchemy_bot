import pandas as pd
from alchemy_tools.evaluate_ingredients import evaluate_effects


def test_evaluate_effects_basic():
    df = pd.DataFrame({
        "code": ["A", "B", "C", "D", "E"],
        "description": ["d1", "d2", "d3", "d4", "d5"],
        "effect_type": ["good", "bad", None, "good", None],
        "effect_value": [1, -1, 1, 2, -2],
    })
    assert evaluate_effects(df) == -90


def test_evaluate_effects_other_penalty():
    df = pd.DataFrame({
        "code": list("ABCDEF"),
        "description": ["d" + x for x in "ABCDEF"],
        "effect_type": [None, None, None, None, None, "good"],
        "effect_value": [1, 1, 1, 1, 1, 2],
    })
    assert evaluate_effects(df) == -990
