import pandas as pd
from alchemy_tools.evaluate_ingredients import evaluate_effects


def test_evaluate_effects_basic():
    df = pd.DataFrame({
        "code": ["A", "B", "C", "D", "E"],
        "description": [
            "Слабый яд",
            "Слабое Противоядие",
            "Снотворное средство",
            "Бодрость (способность находиться в состоянии высокого жизненного тонуса, избытка сил и желания что-либо делать)",
            "Галлюцинации",
        ],
    })
    assert evaluate_effects(df) == 3


def test_evaluate_effects_invalid():
    df = pd.DataFrame({
        "code": list("ABCDE"),
        "description": [
            "Бесстрашие и безрассудство",
            "Барьер Души снижается до 1 единицы",
            "Блокирует магическую силу (сила эликсира = время в минутах)",
            "Вводит в состояние депрессии",
            "В составе эликсира дает магу защиту от различных духов и призраков, защищая от проникновения их в тело.",
        ],
    })
    assert evaluate_effects(df) == -1000
