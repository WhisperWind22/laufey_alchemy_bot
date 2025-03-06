import pandas as pd
from .db_wrapper import db_alchemy_wrapper
from .effects_tools import get_by_ingredients_with_codes


def evaluate_effects(all_effects_df):
    other_effects_df = all_effects_df[all_effects_df["effect_type"].isna()]
    grouped_effects = list(all_effects_df.groupby("effect_type"))
    score = 0
    other_effects_len = other_effects_df.shape[0]
    if other_effects_len > 4:
        score -= 1000
    else:
        pass
        # score -= 100 * other_effects_len

    for effect_type,effect_df in grouped_effects:
        effect_value = effect_df["effect_value"].sum()
        if effect_value>0:
            score+=10
        else:
            score-=100
    return score
@db_alchemy_wrapper
def calculate_score_by_formula(formula,cursor):
    all_effects_df = get_by_ingredients_with_codes(formula,cursor)
    return evaluate_effects(all_effects_df)
