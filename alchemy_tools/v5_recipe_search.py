from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple
import itertools
import random
import time

from alchemy_tools.v5_data import load_v5_data


FORMULA_SIZE = 5
MAX_FINAL_EFFECTS = 4


SUPPORT_KINDS = {
    "antidote",
    "restore_energy",
    "mental_protect",
    "mental_cleanse",
    "mental_clarity",
    "stop_bleeding",
    "wake",
    "sobriety",
    "temptation_resistance",
    "truth",
    "balance",
    "cant_sleep",
    "reason_restore",
}

HARM_KINDS = {
    "poison",
    "poison_bleeding",
    "poison_energy_down",
    "sleep",
    "hallucinations",
    "lie",
    "kleptomania",
    "curious_varvara",
    "intoxication",
    "carefree",
    "reason_clouding",
    "nature_craving",
}


@dataclass(frozen=True)
class TokenInfo:
    token: str
    code: str
    add_index: int  # 1..3
    main_effect: str
    add_effect: str
    kinds: Tuple[str, ...]


@dataclass(frozen=True)
class RecipeCandidate:
    tokens: List[str]
    final_effects: List[str]
    logs: List[Tuple[str, str]]
    violations: List[str]
    effect_count: int
    harm: int


_TOKENS: Optional[Dict[str, TokenInfo]] = None


def _validate_formula_tokens(tokens: Sequence[str]) -> None:
    v5 = load_v5_data()
    if len(tokens) != FORMULA_SIZE:
        raise ValueError(f"Формула должна содержать {FORMULA_SIZE} токенов")
    v5.suppression_mod.validate_formula_tokens(tokens)

    codes = [v5.suppression_mod.parse_token(t)[0] for t in tokens]
    counts = Counter(codes)
    for code, n in counts.items():
        if n > 2:
            raise ValueError(f"Ингредиент {code} использован {n} раз(а) (лимит 2)")


def _effect_kind(effect_text: str) -> str:
    v5 = load_v5_data()
    key = v5.suppression_mod.normalize_text(effect_text)
    cat = v5.effect_categories.get(key)
    if not cat:
        return "raw"
    return (cat.get("kind") or "raw").strip()


def _harm_score(final_effects: List[str]) -> int:
    harm = 0
    for eff in final_effects:
        kind = _effect_kind(eff)
        if kind.startswith("poison"):
            harm += 3
        elif kind in {"sleep", "hallucinations", "lie", "kleptomania", "curious_varvara", "intoxication", "carefree"}:
            harm += 2
    return harm


def _build_tokens() -> Dict[str, TokenInfo]:
    v5 = load_v5_data()
    out: Dict[str, TokenInfo] = {}
    for code, ing in v5.ingredient_db.items():
        main = v5.suppression_mod.normalize_text(ing.get("main", ""))
        if not main:
            continue
        for idx in (1, 2, 3):
            add = v5.suppression_mod.normalize_text(ing.get(f"add{idx}", ""))
            if not add:
                continue
            token = f"{code}{idx}"
            kinds = tuple(sorted({_effect_kind(main), _effect_kind(add)}))
            out[token] = TokenInfo(
                token=token,
                code=code,
                add_index=idx,
                main_effect=main,
                add_effect=add,
                kinds=kinds,
            )
    return out


def _all_tokens() -> Dict[str, TokenInfo]:
    global _TOKENS
    if _TOKENS is None:
        _TOKENS = _build_tokens()
    return _TOKENS


def _token_rank(info: TokenInfo) -> int:
    kinds = set(info.kinds)
    score = 0
    score += 3 * len(kinds & SUPPORT_KINDS)
    score -= 2 * len(kinds & HARM_KINDS)
    return score


def _seed_tokens(effect_text: str, max_seeds: int) -> List[str]:
    v5 = load_v5_data()
    target = v5.suppression_mod.normalize_text(effect_text)
    tokens = _all_tokens()
    out: List[str] = []
    for tok, info in tokens.items():
        if info.main_effect == target:
            out.append(tok)
        elif info.add_effect == target:
            out.append(tok)
    out = sorted(set(out), key=lambda t: (0 if tokens[t].add_effect == target else 1, t))
    return out[:max_seeds]


def _token_pool(seed_tokens: List[str], pool_size: int) -> List[str]:
    tokens = _all_tokens()
    seed_set = set(seed_tokens)
    ranked = sorted(
        (t for t in tokens.keys() if t not in seed_set),
        key=lambda t: (_token_rank(tokens[t]), t),
        reverse=True,
    )
    pool: List[str] = []
    pool.extend(seed_tokens)
    for t in ranked:
        if len(pool) >= pool_size:
            break
        pool.append(t)
    return pool


def _score(tokens: List[str], required_effect: str, max_effect_count: int) -> Optional[RecipeCandidate]:
    v5 = load_v5_data()
    try:
        _validate_formula_tokens(tokens)
        res = v5.suppression_mod.resolve_formula_tokens(tokens, v5.ingredient_db, v5.suppression_cfg, v5.effect_categories)
    except Exception:
        return None

    if res.violations:
        return None
    if len(res.final_effects) > max_effect_count:
        return None

    # Use normalize_key (lowercasing + typo fixes) because the resolver may emit
    # canonicalized poison/antidote labels that differ only by casing from the
    # catalog text (e.g. "Смертельный Яд" vs "Смертельный яд").
    target = v5.suppression_mod.normalize_key(required_effect)
    finals_norm = [v5.suppression_mod.normalize_key(x) for x in res.final_effects]
    if target not in finals_norm:
        return None

    harm = _harm_score(res.final_effects)
    logs = [(l.action, l.details) for l in res.logs]
    return RecipeCandidate(
        tokens=list(tokens),
        final_effects=list(res.final_effects),
        logs=logs,
        violations=list(res.violations),
        effect_count=len(res.final_effects),
        harm=harm,
    )

def _allowed_add(formula: Tuple[str, ...], tok: str) -> bool:
    v5 = load_v5_data()
    if tok in formula:
        return False
    try:
        code, _idx = v5.suppression_mod.parse_token(tok)
    except Exception:
        return False
    codes = [v5.suppression_mod.parse_token(t)[0] for t in formula]
    if Counter(codes).get(code, 0) >= 2:
        return False
    return True


def _partial_metrics(tokens: Tuple[str, ...], required_effect: str) -> Tuple[Tuple[int, int, int, str], Optional[Tuple[List[str], List[Tuple[str, str]], List[str]]]]:
    """
    Return:
      - sort key: (effect_count, missing_required_penalty, violations_penalty, stable_tiebreak)
      - resolved details (final_effects, logs, violations) or None if resolution failed
    """
    v5 = load_v5_data()
    try:
        v5.suppression_mod.validate_formula_tokens(tokens)
        res = v5.suppression_mod.resolve_formula_tokens(tokens, v5.ingredient_db, v5.suppression_cfg, v5.effect_categories)
    except Exception:
        # Keep it sortable; treat as very bad.
        return ((10_000, 10_000, 10_000, ",".join(tokens)), None)

    finals = list(res.final_effects or [])
    finals_norm = [v5.suppression_mod.normalize_text(x) for x in finals]
    target = v5.suppression_mod.normalize_text(required_effect)
    missing_required = 0 if target in finals_norm else 1
    violations_penalty = len(res.violations or [])
    key = (len(finals), missing_required, violations_penalty, ",".join(tokens))
    logs = [(l.action, l.details) for l in (res.logs or [])]
    return key, (finals, logs, list(res.violations or []))


def find_best_recipes_for_effect(
    effect_text: str,
    pool_size: int = 9999,
    max_seeds: int = 24,
    max_results: int = 3,
    time_budget_sec: float = 20.0,
    beam_width: int = 140,
    expand_per_state: int = 25,
) -> List[RecipeCandidate]:
    """
    v5 picker:
    - strict preference: 1 final effect, else 2, else 3, else 4
    - tie-break by harm, then lexicographic tokens
    - search space constrained by a token pool derived from seeds + support-ish tokens
    """
    v5 = load_v5_data()
    effect_text = v5.suppression_mod.normalize_text(effect_text)

    deadline = time.monotonic() + max(0.1, float(time_budget_sec))

    seeds = _seed_tokens(effect_text, max_seeds=max_seeds)
    pool = _token_pool(seeds, pool_size=pool_size)

    if not seeds:
        return []

    # Deterministic ordering for reproducibility.
    pool = list(dict.fromkeys(pool))
    pool_ranked = sorted(pool, key=lambda t: (_token_rank(_all_tokens()[t]), t), reverse=True)

    # Fast randomized search is the best tradeoff for v5: solutions that keep the
    # required effect while staying within <=4 final effects can be very rare.
    rnd = random.Random(0)
    target_norm = v5.suppression_mod.normalize_text(effect_text)

    best: List[RecipeCandidate] = []
    best_seen: set[str] = set()

    # Prefer seeds that match the effect as an add (more flexible than main-only matches).
    seeds_sorted = list(seeds)
    info = _all_tokens()
    seeds_sorted.sort(key=lambda t: (0 if info[t].add_effect == target_norm else 1, t))

    # Main loop: sample formulas, resolve, keep the best few.
    while time.monotonic() < deadline:
        seed = rnd.choice(seeds_sorted)
        formula: List[str] = [seed]
        used = {seed}
        counts = Counter([info[seed].code])

        # Fill remaining slots with a mix of exploration and exploitation.
        attempts = 0
        while len(formula) < FORMULA_SIZE and attempts < 200:
            attempts += 1
            cand_pool = pool_ranked[:90] if rnd.random() < 0.6 else pool_ranked
            tok = rnd.choice(cand_pool)
            if tok in used:
                continue
            code = info[tok].code
            if counts.get(code, 0) >= 2:
                continue
            used.add(tok)
            counts[code] += 1
            formula.append(tok)

        if len(formula) != FORMULA_SIZE:
            continue

        formula = sorted(formula)
        key = ",".join(formula)
        if key in best_seen:
            continue

        cand = _score(formula, effect_text, max_effect_count=MAX_FINAL_EFFECTS)
        if not cand:
            continue

        best_seen.add(key)
        best.append(cand)
        best.sort(key=lambda c: (c.effect_count, c.harm, ",".join(c.tokens)))
        best = best[: max(10, max_results)]

        if best and best[0].effect_count == 1:
            break

    if not best:
        return []

    best.sort(key=lambda c: (c.effect_count, c.harm, ",".join(c.tokens)))
    return best[:max_results]
