from __future__ import annotations

from typing import Iterable, List, Tuple

from alchemy_tools.effects_tools import get_ingredient_code_by_id
from alchemy_tools.v5_data import load_v5_data, resolve_tokens


Selection = Tuple[int, int]


def _normalize_selections(selections: Iterable[Selection]) -> List[Selection]:
    normalized: List[Selection] = []
    for entry in selections:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError("Each selection must be (ingredient_id, add_index)")
        ingredient_id, add_index = entry
        normalized.append((int(ingredient_id), int(add_index)))
    return normalized


def resolve_potion_effects(
    selections: Iterable[Selection],
    reverse: bool = False,
    max_effects: int | None = None,
):
    """Resolve potion effects and return text plus structured details (v5 rules)."""
    selections = _normalize_selections(selections)
    if reverse:
        raise ValueError("reverse=True is not supported in v5 resolver")

    v5 = load_v5_data()
    limit = int(max_effects if max_effects is not None else v5.suppression_cfg.get("max_final_effects", 999))

    tokens: List[str] = []
    for ingredient_id, add_index in selections:
        code = get_ingredient_code_by_id(ingredient_id)
        if not code:
            raise ValueError(f"Unknown ingredient_id: {ingredient_id}")
        idx = int(add_index) + 1
        if idx < 1 or idx > 3:
            raise ValueError(f"Bad add_index={add_index} (expected 0..2)")
        tokens.append(f"{code}{idx}")

    res = resolve_tokens(tokens)
    final_effects = list(res.final_effects or [])
    logs = [f"{l.action}: {l.details}" for l in (res.logs or [])]
    violations = list(res.violations or [])
    valid = (not violations) and (len(final_effects) <= limit)

    lines = ["Итоговые эффекты:"]
    if final_effects:
        for effect in final_effects:
            lines.append(f"- {effect}")
    else:
        lines.append("- Нет")

    if logs:
        lines.append("")
        lines.append("Подавления/правила:")
        for line in logs:
            lines.append(f"- {line}")

    if violations:
        lines.append("")
        lines.append("Нарушения:")
        for v in violations:
            lines.append(f"- {v}")

    lines.append("")
    lines.append(f"Итого эффектов: {len(final_effects)} / {limit}")
    if not valid:
        lines.append("Внимание! Формула нестабильна по правилам v5.")

    text = "\n".join(lines).rstrip()

    return {
        "text": text,
        "final_effects": final_effects,
        "log": logs,
        "violations": violations,
        "effect_count": len(final_effects),
        "max_effects": limit,
        "valid": valid,
        "tokens": tokens,
    }
