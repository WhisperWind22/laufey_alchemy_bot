# -*- coding: utf-8 -*-
"""
effect_suppression.py

Project-level stable wrapper around the current suppression engine.

Historically the repo used `effect_suppression_v4.py` (token-based internal model).
Starting with data pack v5 we use `alchemy_bot_data_v5/effect_suppression_v5.py`,
which resolves either:
- raw effect texts: resolve_effect_texts([...])
- formula selection tokens: resolve_formula_tokens(["AM1", ...])

Keep a small compatibility surface for the rest of the codebase:
- MAX_EFFECTS: max number of final effects allowed
- parse_selection_token(token) -> (code, idx)
- validate_recipe_tokens(tokens) -> None  (5 tokens, no dupes, <=2 per code)
- suppress_effect_texts(effect_texts, ...) -> SuppressionResult
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from typing import List, Optional, Tuple

from alchemy_tools.v5_data import load_v5_data


@dataclass(frozen=True)
class SuppressionResult:
    active_effects: List[str]
    log: List[str]
    effect_count: int
    valid: bool
    violations: List[str]


def _max_effects() -> int:
    v5 = load_v5_data()
    try:
        return int(v5.suppression_cfg.get("max_final_effects", 4))
    except Exception:
        return 4


MAX_EFFECTS = _max_effects()


def parse_selection_token(token: str) -> Tuple[str, int]:
    v5 = load_v5_data()
    return v5.suppression_mod.parse_token(token)


def validate_recipe_tokens(tokens: List[str], formula_size: int = 5) -> None:
    """
    Enforce recipe constraints for selection tokens like ['RK1','RK2','BA3','SZ3','FN2'].

    - Exactly `formula_size` tokens.
    - No exact duplicates.
    - Same ingredient code can be used at most 2 times, and only with different add indices.
    """
    if len(tokens) != int(formula_size):
        raise ValueError(f"Формула должна содержать {formula_size} токенов, получено: {len(tokens)}")

    v5 = load_v5_data()
    v5.suppression_mod.validate_formula_tokens(tokens)

    counts_by_code = Counter()
    indices_by_code: dict[str, set[int]] = {}
    for tok in tokens:
        code, idx = v5.suppression_mod.parse_token(tok)
        counts_by_code[code] += 1
        indices_by_code.setdefault(code, set()).add(int(idx))

    for code, n in counts_by_code.items():
        if n > 2:
            raise ValueError(f"Ингредиент {code} использован {n} раз(а) (лимит 2)")
        if len(indices_by_code[code]) != n:
            raise ValueError(f"Повтор ингредиента {code} возможен только с разными доп. эффектами")


def suppress_effect_texts(
    effect_texts: List[str],
    reverse: bool = False,
    max_effects: Optional[int] = None,
) -> SuppressionResult:
    """
    Resolve suppression from raw effect texts (main + selected additional).

    Note: v5 engine does not implement "reverse brewing" mapping; keep the argument
    for API compatibility and fail fast if used.
    """
    if reverse:
        raise ValueError("reverse=True is not supported in v5 suppression engine")

    v5 = load_v5_data()
    res = v5.suppression_mod.resolve_effect_texts(effect_texts, v5.suppression_cfg, v5.effect_categories)

    limit = int(max_effects if max_effects is not None else v5.suppression_cfg.get("max_final_effects", 999))
    active = list(res.final_effects)
    logs = [f"{l.action}: {l.details}" for l in (res.logs or [])]
    violations = list(res.violations or [])
    valid = (not violations) and (len(active) <= limit)

    return SuppressionResult(
        active_effects=active,
        log=logs,
        effect_count=len(active),
        valid=valid,
        violations=violations,
    )

