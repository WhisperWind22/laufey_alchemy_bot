from effect_suppression_v4 import MAX_EFFECTS, suppress_effect_texts
from .db_wrapper import db_alchemy_wrapper
from .effects_tools import get_by_ingredients_with_codes


def evaluate_effects(all_effects_df):
    effect_texts = all_effects_df["description"].tolist()
    result = suppress_effect_texts(effect_texts, max_effects=MAX_EFFECTS)
    if not result.valid:
        return -1000
    return MAX_EFFECTS - result.effect_count
def calculate_score_by_formula(formula,cursor):
    all_effects_df = get_by_ingredients_with_codes(formula,cursor=cursor)
    return evaluate_effects(all_effects_df)
