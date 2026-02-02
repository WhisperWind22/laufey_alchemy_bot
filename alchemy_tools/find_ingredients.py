import pandas as pd
from collections import Counter
from .db_wrapper import db_alchemy_wrapper
from .effects_tools import SELECT_ALL_EFFECTS
from .evaluate_ingredients import calculate_score_by_formula
from .utils import split_formula

SELECT_ALL_EFFECTS_BY_USER="""
SELECT
	i.code,
	props.ingredient_order ,
	e.description,
	et."type",
	et.value
FROM
	ingredients AS i
join properties props on
	i.id = props.ingredient_id
join effects e on
	e.id = props.effect_id
left join effects_types et on
	e.id = et.effect_id
join user_ingredients ui on
	ui.ingredient_id = i.id
where
	ui.user_id = {user_id}
"""
## where et."type" is not Null


def _all_tokens(all_ingredients_effects):
    tokens = set()
    for _, row in all_ingredients_effects.iterrows():
        order = int(row["ingredient_order"])
        if order == 0:
            continue
        tokens.add(f"{row['code']}{order}")
    return sorted(tokens)


def _is_candidate_allowed(formula, candidate):
    if candidate in formula:
        return False
    codes, orders = split_formula(formula)
    cand_code, cand_order = candidate[:-1], int(candidate[-1])
    counts = Counter(codes)
    if counts.get(cand_code, 0) >= 2:
        return False
    for code, order in zip(codes, orders):
        if code == cand_code and order == cand_order:
            return False
    if cand_order < 1 or cand_order > 3:
        return False
    return True

def potential_candidates_codes_generator(all_ingredients_effects, formula, positive_effects=True):
    all_tokens = _all_tokens(all_ingredients_effects)
    return [tok for tok in all_tokens if _is_candidate_allowed(formula, tok)]


@db_alchemy_wrapper
def potential_candidates_with_max_score_one_step(all_ingredients_effects,formula,cursor,only_max_score=True):
    potential_candidates_codes = potential_candidates_codes_generator(all_ingredients_effects,formula)
    if len(potential_candidates_codes)==0:
        potential_candidates_codes=_all_tokens(all_ingredients_effects)
    potential_candidates_scores=[]
    for potential_candidate_code in potential_candidates_codes:
        potential_candidates_scores.append(calculate_score_by_formula(formula+[potential_candidate_code],cursor=cursor))
    potential_candidates_scores_df = pd.DataFrame(data={"code":potential_candidates_codes,"score":potential_candidates_scores})
    potential_candidates_scores_df = potential_candidates_scores_df.sort_values(by="score",ascending=False)
    max_score = potential_candidates_scores_df["score"].max()
    if only_max_score:
        potential_candidates_scores_df=potential_candidates_scores_df[potential_candidates_scores_df["score"]==max_score]
    return potential_candidates_scores_df

@db_alchemy_wrapper
def potential_candidates_with_max_score_several_steps(formula,cursor,steps=1,only_max_score=True, all_ingredients_effects=None, user_id=None):
    if all_ingredients_effects is None:
        if user_id is None:
            cursor.execute(SELECT_ALL_EFFECTS)
        else:
            cursor.execute(SELECT_ALL_EFFECTS_BY_USER.format(user_id=user_id))
        all_ingredients_effects = cursor.fetchall()
        all_ingredients_effects = pd.DataFrame(data=all_ingredients_effects, columns=["code","ingredient_order","description","effect_type","effect_value"])

    result = set()
    step_candidates = potential_candidates_with_max_score_one_step(all_ingredients_effects,formula,only_max_score=only_max_score)["code"].values.tolist()
    formulas = [formula+[x] for x in step_candidates]
    formulas = set([frozenset(x) for x in formulas])
    if steps >0:
        for current_formula in formulas:
            cur_res=potential_candidates_with_max_score_several_steps(list(current_formula),cursor=cursor,steps=steps-1,only_max_score=only_max_score, all_ingredients_effects=all_ingredients_effects)
            cur_res = set([frozenset(x) for x in cur_res])
            result = result.union(cur_res)
    else:
        result = formulas
    result = [list(x) for x in result]

    for formula in result:
        validate_formula(formula)
    return result

def validate_formula(formula):
    codes,orders = split_formula(formula)
    if max(orders)>3 or min(orders)<1:
        raise ValueError()
    counts = Counter(codes)
    for code, count in counts.items():
        if count > 2:
            raise ValueError()
    seen = set()
    for code, order in zip(codes, orders):
        token = f"{code}{order}"
        if token in seen:
            raise ValueError()
        seen.add(token)
