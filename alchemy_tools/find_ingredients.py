import pandas as pd
from .db_wrapper import db_alchemy_wrapper
from .effects_tools import SELECT_ALL_EFFECTS
from .evaluate_ingredients import calculate_score_by_formula
from .utils import split_formula


## where et."type" is not Null


def potential_candidates_codes_generator_by_effect_type(potential_candidates,effect_type,positive_effects=True):
    potential_candidates=potential_candidates[potential_candidates["effect_type"]==effect_type]
    if positive_effects:
        potential_candidates=potential_candidates[potential_candidates["effect_value"]>=0]
    else:
        potential_candidates=potential_candidates[potential_candidates["effect_value"]<0]
    potential_candidates_codes =potential_candidates["code"].unique()
    potential_candidates_codes=[]
    for _,row in potential_candidates.iterrows():
        if row["ingredient_order"]==0:
            potential_candidates_codes.append(row["code"]+"1")
            potential_candidates_codes.append(row["code"]+"2")
            potential_candidates_codes.append(row["code"]+"3")
        else:
            potential_candidates_codes.append(row["code"]+str(row["ingredient_order"]))
    return potential_candidates_codes

def potential_candidates_codes_generator(all_ingredients_effects,formula,positive_effects=True):
    ingredients, ingredients_effects_nums = split_formula(formula)
    current_ingredients_types= []
    for ingredient, ingredient_effect_num in zip(ingredients, ingredients_effects_nums):
        _cur_ingredient_effects = all_ingredients_effects[all_ingredients_effects["code"]==ingredient]
        main_effect_type = _cur_ingredient_effects[_cur_ingredient_effects["ingredient_order"]==0]["effect_type"].values[0]
        if main_effect_type is not None:
            current_ingredients_types.append(main_effect_type)
        minor_effect_type = _cur_ingredient_effects[_cur_ingredient_effects["ingredient_order"]==ingredient_effect_num]["effect_type"].values[0]
        if minor_effect_type is not None:
            current_ingredients_types.append(minor_effect_type)
    current_effects_types = list(set(current_ingredients_types))

    potential_candidates=all_ingredients_effects[~all_ingredients_effects["code"].isin(ingredients)]
    all_candidates = []
    for effect_type in current_effects_types:
        all_candidates.extend(potential_candidates_codes_generator_by_effect_type(potential_candidates,effect_type,positive_effects=positive_effects))
    return all_candidates


@db_alchemy_wrapper
def potential_candidates_with_max_score_one_step(all_ingredients_effects,formula,cursor,only_max_score=True):
    potential_candidates_codes = potential_candidates_codes_generator(all_ingredients_effects,formula)
    potential_candidates_scores=[]
    for potential_candidate_code in potential_candidates_codes:
        potential_candidates_scores.append(calculate_score_by_formula(formula+[potential_candidate_code],cursor))
    potential_candidates_scores_df = pd.DataFrame(data={"code":potential_candidates_codes,"score":potential_candidates_scores})
    potential_candidates_scores_df = potential_candidates_scores_df.sort_values(by="score",ascending=False)
    max_score = potential_candidates_scores_df["score"].max()
    if only_max_score:
        potential_candidates_scores_df=potential_candidates_scores_df[potential_candidates_scores_df["score"]==max_score]
    return potential_candidates_scores_df

@db_alchemy_wrapper
def potential_candidates_with_max_score_several_steps(formula,cursor,steps=1,only_max_score=True, all_ingredients_effects=None):
    if all_ingredients_effects is None:
        cursor.execute(SELECT_ALL_EFFECTS)
        all_ingredients_effects = cursor.fetchall()
        all_ingredients_effects = pd.DataFrame(data=all_ingredients_effects, columns=["code","ingredient_order","description","effect_type","effect_value"])

    result = set()
    step_candidates = potential_candidates_with_max_score_one_step(all_ingredients_effects,formula,only_max_score=only_max_score)["code"].values.tolist()
    formulas = [formula+[x] for x in step_candidates]
    formulas = set([frozenset(x) for x in formulas])
    if steps >1:
        for current_formula in formulas:
            cur_res=potential_candidates_with_max_score_several_steps(list(current_formula),steps-1,only_max_score=only_max_score, all_ingredients_effects=all_ingredients_effects)
            cur_res = set([frozenset(x) for x in cur_res])
            result = result.union(cur_res)
    else:
        result = formulas
    result = [list(x) for x in result]
    return result