import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import csv
import time

from effect_suppression_v4 import (
    EFFECT_CATALOG,
    MAX_EFFECTS,
    categorize_effect_text,
    resolve_tokens,
    validate_recipe_tokens,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
INGREDIENTS_V4_PATH = ROOT_DIR / "ingredients_v4.json"
EFFECT_CATEGORIES_V4_PATH = ROOT_DIR / "effect_categories_v4.csv"


SUPPORT_KINDS = {
    "antidote",
    "restore_energy",
    "mental_protect",
    "mental_cleanse",
    "stop_bleeding",
    "wake",
    "sobriety",
    "tempt_resist",
    "truth",
    "balance",
    "cannot_sleep",
}

HARM_KINDS = {
    "poison",
    "sleep",
    "hallucinations",
    "kleptomania",
    "varvara",
    "lie",
    "intoxication",
    "carefree",
}


@dataclass(frozen=True)
class TokenInfo:
    token: str
    code: str
    add_index: int  # 0..2
    ingredient_name: str
    main_effect: str
    add_effect: str
    internal_tokens: Tuple[str, ...]

    @property
    def effects(self) -> List[str]:
        return [self.main_effect, self.add_effect]


def _norm(s: str) -> str:
    return " ".join((s or "").strip().split())


def _load_effect_texts() -> List[str]:
    texts: List[str] = []
    with EFFECT_CATEGORIES_V4_PATH.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            t = _norm(row.get("effect_text", ""))
            if t:
                texts.append(t)
    return texts


_EFFECT_TEXTS: Optional[List[str]] = None


def search_effect_texts(query: str, limit: int = 12) -> List[str]:
    """
    Search canonical effect texts (v4) and return best matches for UI selection.
    """
    global _EFFECT_TEXTS
    if _EFFECT_TEXTS is None:
        _EFFECT_TEXTS = _load_effect_texts()

    q = _norm(query).lower()
    if not q:
        return []

    scored: List[Tuple[Tuple[int, int, int], str]] = []
    for text in _EFFECT_TEXTS:
        tl = text.lower()
        pos = tl.find(q)
        if pos < 0:
            continue
        # Sort: earlier match, shorter text, stable lexicographic.
        scored.append(((pos, len(text), 0), text))

    scored.sort(key=lambda x: (x[0], x[1].lower()))
    return [t for _score, t in scored[:limit]]


_TOKENS: Optional[Dict[str, TokenInfo]] = None


def _load_tokens() -> Dict[str, TokenInfo]:
    with INGREDIENTS_V4_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

    tokens: Dict[str, TokenInfo] = {}
    for ing in data:
        code = ing["code"].strip()
        name = ing["name"].strip()
        main = _norm(ing["main"])
        adds = ing.get("adds") or []
        for idx, add in enumerate(adds):
            add = _norm(add)
            token = f"{code}{idx + 1}"
            internal = tuple(categorize_effect_text(main) + categorize_effect_text(add))
            tokens[token] = TokenInfo(
                token=token,
                code=code,
                add_index=idx,
                ingredient_name=name,
                main_effect=main,
                add_effect=add,
                internal_tokens=internal,
            )
    return tokens


def get_all_tokens() -> Dict[str, TokenInfo]:
    global _TOKENS
    if _TOKENS is None:
        _TOKENS = _load_tokens()
    return _TOKENS


def find_seed_tokens_for_effect(effect_text: str) -> List[str]:
    """
    Tokens whose main or chosen additional effect exactly equals effect_text.
    """
    target = _norm(effect_text)
    tokens = get_all_tokens()

    out: List[str] = []
    for tok, info in tokens.items():
        if info.add_effect == target or info.main_effect == target:
            out.append(tok)

    # Stable order: prefer direct additional match over main match, then by code.
    def key(t: str) -> Tuple[int, str]:
        info = tokens[t]
        return (0 if info.add_effect == target else 1, t)

    out.sort(key=key)
    return out


def _effect_kind(effect_text: str) -> str:
    kind, _tier = EFFECT_CATALOG.get(_norm(effect_text).lower(), ("raw", ""))
    return kind or "raw"


def _token_support_score(info: TokenInfo) -> int:
    kinds = {_effect_kind(t) for t in info.effects}
    score = 0
    score += 3 * len(kinds & SUPPORT_KINDS)
    score -= 2 * len(kinds & HARM_KINDS)
    return score


def build_token_pool(seed_tokens: Iterable[str], pool_size: int = 40) -> List[str]:
    tokens = get_all_tokens()
    seed_tokens = [t for t in seed_tokens if t in tokens]
    seed_set = set(seed_tokens)

    # Rank non-seed tokens by "supportiness".
    ranked = sorted(
        (t for t in tokens.keys() if t not in seed_set),
        key=lambda t: (_token_support_score(tokens[t]), t),
        reverse=True,
    )

    pool: List[str] = []
    for t in seed_tokens:
        pool.append(t)
    for t in ranked:
        if len(pool) >= pool_size:
            break
        pool.append(t)

    return pool


@dataclass(frozen=True)
class RecipeCandidate:
    tokens: List[str]
    active_effects: List[str]
    log: List[str]
    effect_count: int
    harm: int


def _score_formula(
    tokens: List[str],
    required_tokens: List[str],
    max_effect_count: int,
) -> Optional[RecipeCandidate]:
    token_map = get_all_tokens()
    internal_tokens: List[str] = []
    for t in tokens:
        info = token_map[t]
        internal_tokens.extend(info.internal_tokens)

    res = resolve_tokens(internal_tokens, max_effects=MAX_EFFECTS)
    if not res.valid:
        return None
    if res.effect_count > max_effect_count:
        return None

    active = set(res.active_tokens)
    if any(req not in active for req in required_tokens):
        return None

    # Ranking policy:
    # - strictly prefer fewer resulting effects (effect_count)
    # - tie-break by fewer harmful tokens/effects (harm)
    harm = 0
    for tok in active:
        if tok.startswith("POISON:"):
            harm += 3
        elif tok in {"SLEEP", "HALLUCINATIONS", "ENERGY_DOWN", "BLEEDING", "LIE", "KLEPTOMANIA", "VARVARA", "CAREFREE", "INTOXICATION"}:
            harm += 2

    return RecipeCandidate(
        tokens=list(tokens),
        active_effects=list(res.active_effects),
        log=list(res.log),
        effect_count=res.effect_count,
        harm=harm,
    )


def _trim_candidates(candidates: List[RecipeCandidate], max_keep: int = 500) -> List[RecipeCandidate]:
    if len(candidates) <= max_keep:
        return candidates
    candidates.sort(key=lambda c: (c.effect_count, c.harm, ",".join(c.tokens)))
    return candidates[:max_keep]


def _search_candidates(
    required: List[str],
    seed_tokens: List[str],
    pool_size: int,
    max_effect_count: int,
    eval_budget: int,
    deadline: float,
) -> List[RecipeCandidate]:
    pool = build_token_pool(seed_tokens, pool_size=pool_size)
    candidates: List[RecipeCandidate] = []
    evals = 0

    if seed_tokens:
        for seed in seed_tokens:
            if seed not in pool:
                continue
            rest = [t for t in pool if t != seed]
            for combo in itertools.combinations(rest, 4):
                if time.monotonic() >= deadline:
                    break
                evals += 1
                if evals > eval_budget:
                    break
                formula = [seed, *combo]
                try:
                    validate_recipe_tokens(formula)
                except ValueError:
                    continue
                cand = _score_formula(formula, required, max_effect_count=max_effect_count)
                if cand:
                    candidates.append(cand)
                    if len(candidates) > 2000:
                        candidates = _trim_candidates(candidates, max_keep=500)
            if evals > eval_budget:
                break
            if time.monotonic() >= deadline:
                break
    else:
        for combo in itertools.combinations(pool, 5):
            if time.monotonic() >= deadline:
                break
            evals += 1
            if evals > eval_budget:
                break
            formula = list(combo)
            try:
                validate_recipe_tokens(formula)
            except ValueError:
                continue
            cand = _score_formula(formula, required, max_effect_count=max_effect_count)
            if cand:
                candidates.append(cand)
                if len(candidates) > 2000:
                    candidates = _trim_candidates(candidates, max_keep=500)

    candidates.sort(key=lambda c: (c.effect_count, c.harm, ",".join(c.tokens)))
    return candidates


def find_best_recipes_for_effect(
    effect_text: str,
    pool_size: int = 40,
    max_results: int = 3,
    max_seeds: int = 8,
    time_budget_sec: float = 20.0,
) -> List[RecipeCandidate]:
    """
    Automatic recipe selection (v4):
    - user chooses exact effect_text
    - we require the corresponding internal token(s) to remain active after suppression

    Two-phase search:
    - try to find recipes with 1 resulting effect first
    - if none exist (within the search scope), relax to 2, then 3, then 4
    """
    required = categorize_effect_text(effect_text)
    required_set = set(required)
    min_possible_effects = max(1, len(required_set))
    all_seeds = find_seed_tokens_for_effect(effect_text)

    phases = list(range(min_possible_effects, MAX_EFFECTS + 1))
    if not phases:
        return []

    # Allocate more time to the first phase, but keep time for later phases
    # to avoid "no result" cases when 1-effect recipes are impossible.
    total = max(0.1, float(time_budget_sec))
    if phases[0] == 1:
        phase1 = min(8.0, total * 0.5)
        rest = max(0.0, total - phase1)
        per_rest = rest / max(1, (len(phases) - 1))
        phase_times = [phase1] + [per_rest] * (len(phases) - 1)
    else:
        first = min(6.0, total * 0.4)
        rest = max(0.0, total - first)
        per_rest = rest / max(1, (len(phases) - 1))
        phase_times = [first] + [per_rest] * (len(phases) - 1)

    for max_effect_count, phase_time in zip(phases, phase_times):
        cur_pool_size = pool_size
        cur_max_seeds = max_seeds
        cur_eval_budget = 180_000

        # Spend more effort trying to reach the ideal "1 effect" case.
        if max_effect_count == 1:
            cur_pool_size = max(pool_size, 70)
            cur_max_seeds = max(max_seeds, 16)
            cur_eval_budget = 650_000

        seed_tokens = all_seeds[:cur_max_seeds]
        deadline = time.monotonic() + max(0.1, float(phase_time))
        candidates = _search_candidates(
            required=required,
            seed_tokens=seed_tokens,
            pool_size=cur_pool_size,
            max_effect_count=max_effect_count,
            eval_budget=cur_eval_budget,
            deadline=deadline,
        )
        if candidates:
            return candidates[:max_results]

    return []
