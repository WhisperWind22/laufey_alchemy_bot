from typing import Iterable, List, Tuple

from alchemy_tools.effects_tools import get_all_properties_by_ingredient_id
from effect_suppression_v4 import MAX_EFFECTS, suppress_effect_texts


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
    max_effects: int = MAX_EFFECTS,
):
    """Resolve potion effects and return text plus structured details (v4 rules)."""
    selections = _normalize_selections(selections)
    effect_texts: List[str] = []

    for ingredient_id, add_index in selections:
        main_property, additional_properties = get_all_properties_by_ingredient_id(ingredient_id)
        if main_property:
            effect_texts.append(main_property[1])
        if add_index is not None and 0 <= add_index < len(additional_properties):
            effect_texts.append(additional_properties[add_index][1])

    result = suppress_effect_texts(effect_texts, reverse=reverse, max_effects=max_effects)

    lines = ["Итоговые эффекты:"]
    if result.active_effects:
        for effect in result.active_effects:
            lines.append(f"- {effect}")
    else:
        lines.append("- Нет")

    if result.log:
        lines.append("")
        lines.append("Подавления:")
        for line in result.log:
            lines.append(f"- {line}")

    lines.append("")
    lines.append(f"Итого эффектов: {result.effect_count} / {max_effects}")
    if not result.valid:
        lines.append("Внимание! Слишком много эффектов — формула нестабильна.")

    text = "\n".join(lines).rstrip()

    return {
        "text": text,
        "active_effects": list(result.active_effects),
        "log": list(result.log),
        "effect_count": result.effect_count,
        "max_effects": max_effects,
        "valid": result.valid,
    }
