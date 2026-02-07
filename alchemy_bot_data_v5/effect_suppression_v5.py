# -*- coding: utf-8 -*-
"""
effect_suppression_v5.py

Алхимия: подавление/компенсация эффектов (на категориях) + проверка формулы.

Файлы данных (рекомендуемые):
- effect_categories_v5.csv
- ingredients_v5.json
- suppression_rules_v5.json
- ingredient_effect_categories_v5.csv (опционально, для отладки)

Ключевые изменения v5:
- Поддержка "не более 4 итоговых эффектов" (конфиг max_final_effects)
- Схлопывание ядов в 1 итоговый яд (берется самый сильный)
- Схлопывание противоядий в 1 итоговое противоядие (берется самое сильное)
- Валидация повторов: один и тот же ингредиент с тем же выбранным доп. эффектом (CODE1/CODE2/CODE3)
  нельзя брать дважды. Разрешено: один и тот же CODE с разными доп. эффектами.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple, Any
import json
import re
import csv


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class EffectAtom:
    """
    Нормализованный "атом" эффекта.

    Иногда один текст эффекта разворачивается в несколько атомов
    (например, "Средний яд (кровотечение)" => яд + кровотечение).
    """
    kind: str
    text: str
    tier: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ResolveLog:
    action: str
    details: str
    involved: List[str] = field(default_factory=list)


@dataclass
class ResolveResult:
    final_effects: List[str]
    logs: List[ResolveLog]
    violations: List[str] = field(default_factory=list)


# -----------------------------
# Constants
# -----------------------------

_DISPLAY_LABELS = {
    "poison": {
        "weak": "Слабый яд",
        "medium": "Средний яд",
        "strong": "Сильный яд",
        "deadly": "Смертельный яд",
    },
    "antidote": {
        "weak": "Слабое противоядие",
        "medium": "Среднее противоядие",
        "strong": "Сильное противоядие",
        "deadly": "Противоядие от смертельных ядов",
    },
}

_TIER_ORDER = ["weak", "medium", "strong", "deadly"]


# -----------------------------
# Helpers
# -----------------------------

_TOKEN_RE = re.compile(r"^(.+?)([123])$")

def normalize_text(s: str) -> str:
    s = str(s).strip()
    s = s.replace("Ё", "Е").replace("ё", "е")
    s = s.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_key(s: str) -> str:
    s = normalize_text(s).lower()
    # частые опечатки
    s = s.replace("галюцина", "галлюцина")
    s = s.replace("приводик", "приводит")
    s = s.replace("сноведени", "сновидени")
    s = s.replace("эфори", "эйфори")
    return s


def parse_token(token: str) -> Tuple[str, int]:
    """
    token: "KQ1" => ("KQ", 1)
    """
    token = token.strip()
    m = _TOKEN_RE.match(token)
    if not m:
        raise ValueError(f"Bad token format: {token!r} (ожидается CODE1/CODE2/CODE3)")
    code = m.group(1)
    idx = int(m.group(2))
    return code, idx


def validate_formula_tokens(tokens: Sequence[str]) -> None:
    """
    Нельзя повторять один и тот же токен (CODE+цифра).
    Разрешено повторять один и тот же CODE с разными цифрами.
    """
    toks = [t.strip() for t in tokens]
    dup = [t for t, c in Counter(toks).items() if c > 1]
    if dup:
        raise ValueError(f"Повтор одного и того же ингредиента с тем же доп. эффектом запрещён: {dup}")


# -----------------------------
# Loading data
# -----------------------------

def load_effect_categories(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает словарь:
        {
          "эффект как в таблице": {"kind": "...", "tier": "...", "tags": [...]},
          ...
        }

    Важно: ключи должны совпадать с текстами эффектов в ingredients_v5.json (после normalize_text).
    """
    out: Dict[str, Dict[str, Any]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eff = normalize_text(row["effect_text"])
            kind = (row.get("kind") or "raw").strip()
            tier = (row.get("tier") or "").strip() or None
            tags_raw = (row.get("tags") or "").strip()
            tags = [t for t in tags_raw.split(";") if t] if tags_raw else []
            out[eff] = {"kind": kind, "tier": tier, "tags": tags}
    return out


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# Classification (via mapping)
# -----------------------------

def classify_effect_text(effect_text: str, cats: Dict[str, Dict[str, Any]]) -> List[EffectAtom]:
    """
    Берет категорию из effect_categories_v5.csv.
    Если нет — fallback на простую эвристику.
    """
    t = normalize_text(effect_text)
    cat = cats.get(t)
    if not cat:
        # fallback
        tl = normalize_key(t)
        if "противояд" in tl:
            return [EffectAtom(kind="antidote", text=t)]
        if "яд" in tl:
            return [EffectAtom(kind="poison", text=t)]
        return [EffectAtom(kind="raw", text=t)]

    kind = cat["kind"]
    tier = cat.get("tier")
    tags = list(cat.get("tags") or [])

    # Композитные яды разворачиваем на 2 атома:
    # - poison_bleeding => poison(medium) + bleeding
    # - poison_energy_down => poison(weak) + energy_down
    if kind == "poison_bleeding":
        return [
            EffectAtom(kind="poison", tier=tier or "medium", text=t),
            EffectAtom(kind="bleeding", text="Кровотечение"),
        ]
    if kind == "poison_energy_down":
        return [
            EffectAtom(kind="poison", tier=tier or "weak", text=t),
            EffectAtom(kind="energy_down", text="Понижение энергии"),
        ]

    return [EffectAtom(kind=kind, tier=tier, text=t, tags=tags)]


# -----------------------------
# Resolution helpers
# -----------------------------

def _tier_rank(tier: Optional[str], cfg: Dict[str, Any]) -> int:
    if not tier:
        return 0
    return int(cfg["poison_antidote_rules"]["tier_rank"].get(tier, 0))


def _cancel_pairwise(atoms: List[EffectAtom], kind_a: str, kind_b: str, logs: List[ResolveLog]) -> List[EffectAtom]:
    """
    Попарно удаляет по одному эффекту kind_a и kind_b.
    """
    idx_a = [i for i, a in enumerate(atoms) if a.kind == kind_a]
    idx_b = [i for i, a in enumerate(atoms) if a.kind == kind_b]
    n = min(len(idx_a), len(idx_b))
    if n == 0:
        return atoms
    remove = set(idx_a[:n] + idx_b[:n])
    logs.append(ResolveLog(action="cancel", details=f"{kind_a} ↔ {kind_b}: {n}×"))
    return [a for i, a in enumerate(atoms) if i not in remove]


def _block_by_presence(atoms: List[EffectAtom], if_any_of: Sequence[str], then_block: Sequence[str], logs: List[ResolveLog], note: str = "") -> List[EffectAtom]:
    if not any(a.kind in if_any_of for a in atoms):
        return atoms
    removed = [a for a in atoms if a.kind in then_block]
    if removed:
        atoms = [a for a in atoms if a.kind not in then_block]
        logs.append(ResolveLog(
            action="block",
            details=(note or "Block rule") + ": " + ", ".join(r.text for r in removed),
        ))
    return atoms


def _collapse_strongest(atoms: List[EffectAtom], group_kind: str, cfg: Dict[str, Any], logs: List[ResolveLog]) -> List[EffectAtom]:
    """
    Схлопывает несколько эффектов одного вида (poison / antidote) в один — самый сильный по tier.
    """
    group = [a for a in atoms if a.kind == group_kind]
    if len(group) <= 1:
        return atoms

    # выбираем самый сильный по rank; при равенстве — оставляем первый встретившийся
    best = max(group, key=lambda a: _tier_rank(a.tier, cfg))
    atoms = [a for a in atoms if a.kind != group_kind] + [best]
    logs.append(ResolveLog(action="collapse", details=f"{group_kind}: {len(group)} -> 1 (оставлен '{best.text}')"))
    return atoms


def _cancel_same_tier(pois_by: Dict[str, List[EffectAtom]], ant_by: Dict[str, List[EffectAtom]], tier: str, logs: List[ResolveLog]) -> None:
    while pois_by[tier] and ant_by[tier]:
        p = pois_by[tier].pop()
        a = ant_by[tier].pop()
        logs.append(ResolveLog(action="cancel", details=f"{p.text} ↔ {a.text} (оба подавлены)"))


def _reduce_poison(pois_by: Dict[str, List[EffectAtom]], ant_by: Dict[str, List[EffectAtom]],
                   poison_tier: str, antidote_tier: str, result_tier: str, logs: List[ResolveLog], msg: str) -> bool:
    if not (pois_by[poison_tier] and ant_by[antidote_tier]):
        return False
    pois_by[poison_tier].pop()
    ant_by[antidote_tier].pop()
    pois_by[result_tier].append(EffectAtom(kind="poison", tier=result_tier, text=_DISPLAY_LABELS["poison"][result_tier]))
    logs.append(ResolveLog(action="reduce", details=msg))
    return True


def _reduce_antidote(pois_by: Dict[str, List[EffectAtom]], ant_by: Dict[str, List[EffectAtom]],
                     antidote_tier: str, poison_tier: str, result_tier: str, logs: List[ResolveLog], msg: str) -> bool:
    if not (ant_by[antidote_tier] and pois_by[poison_tier]):
        return False
    ant_by[antidote_tier].pop()
    pois_by[poison_tier].pop()
    ant_by[result_tier].append(EffectAtom(kind="antidote", tier=result_tier, text=_DISPLAY_LABELS["antidote"][result_tier]))
    logs.append(ResolveLog(action="reduce", details=msg))
    return True


# -----------------------------
# Main resolver
# -----------------------------

def resolve_effect_texts(effect_texts: Sequence[str], cfg: Dict[str, Any], cats: Dict[str, Dict[str, Any]]) -> ResolveResult:
    logs: List[ResolveLog] = []
    violations: List[str] = []

    # 1) classify
    atoms: List[EffectAtom] = []
    for t in effect_texts:
        atoms.extend(classify_effect_text(t, cats))

    # 2) split poisons/antidotes for tier logic
    pois_by: Dict[str, List[EffectAtom]] = defaultdict(list)
    ant_by: Dict[str, List[EffectAtom]] = defaultdict(list)
    others: List[EffectAtom] = []

    for a in atoms:
        if a.kind == "poison" and a.tier:
            pois_by[a.tier].append(a)
        elif a.kind == "antidote" and a.tier:
            ant_by[a.tier].append(a)
        else:
            others.append(a)

    # 3) deadly poison ↔ deadly antidote (1:1)
    while pois_by["deadly"] and ant_by["deadly"]:
        pois_by["deadly"].pop()
        ant_by["deadly"].pop()
        logs.append(ResolveLog(action="cancel", details="Смертельный яд ↔ противоядие от смертельных ядов"))

    # 4) deadly antidote blocks packages of non-deadly poisons (по правилам)
    while ant_by["deadly"] and (pois_by["strong"] or pois_by["medium"] or pois_by["weak"]):
        ant_by["deadly"].pop()
        cancelled: List[EffectAtom] = []

        if len(pois_by["strong"]) >= 1 and len(pois_by["medium"]) >= 2:
            cancelled += [pois_by["strong"].pop(), pois_by["medium"].pop(), pois_by["medium"].pop()]
        elif len(pois_by["strong"]) >= 2:
            cancelled += [pois_by["strong"].pop(), pois_by["strong"].pop()]
        elif len(pois_by["medium"]) >= 3:
            cancelled += [pois_by["medium"].pop(), pois_by["medium"].pop(), pois_by["medium"].pop()]
        elif len(pois_by["weak"]) >= 4:
            cancelled += [pois_by["weak"].pop() for _ in range(4)]
        else:
            # частичное применение (если нет полного пакета)
            if pois_by["strong"]:
                cancelled += [pois_by["strong"].pop()]
            elif pois_by["medium"]:
                cancelled += [pois_by["medium"].pop()]
            elif pois_by["weak"]:
                cancelled += [pois_by["weak"].pop()]

        logs.append(ResolveLog(
            action="block",
            details="Противоядие от смертельных ядов блокирует: " + ", ".join(c.text for c in cancelled)
        ))

    # 5) same-tier cancellation (strong/medium/weak)
    for tier in ("strong", "medium", "weak"):
        _cancel_same_tier(pois_by, ant_by, tier, logs)

    # 6) cross-tier reductions (ступенчатая модель)
    changed = True
    it = 0
    while changed and it < 50:
        it += 1
        changed = False

        # strong poison + (medium/weak antidote)
        while pois_by["strong"] and (ant_by["medium"] or ant_by["weak"]):
            if ant_by["medium"]:
                changed = _reduce_poison(pois_by, ant_by, "strong", "medium", "medium", logs,
                                        "Сильный яд + среднее противоядие ⇒ остаётся средний яд") or changed
            else:
                changed = _reduce_poison(pois_by, ant_by, "strong", "weak", "weak", logs,
                                        "Сильный яд + слабое противоядие ⇒ остаётся слабый яд") or changed

        # strong antidote + (medium/weak poison)
        while ant_by["strong"] and (pois_by["medium"] or pois_by["weak"]):
            if pois_by["medium"]:
                changed = _reduce_antidote(pois_by, ant_by, "strong", "medium", "medium", logs,
                                          "Сильное противоядие + средний яд ⇒ остаётся среднее противоядие") or changed
            else:
                changed = _reduce_antidote(pois_by, ant_by, "strong", "weak", "weak", logs,
                                          "Сильное противоядие + слабый яд ⇒ остаётся слабое противоядие") or changed

        # medium poison + weak antidote
        while pois_by["medium"] and ant_by["weak"]:
            changed = _reduce_poison(pois_by, ant_by, "medium", "weak", "weak", logs,
                                    "Средний яд + слабое противоядие ⇒ остаётся слабый яд") or changed

        # medium antidote + weak poison
        while ant_by["medium"] and pois_by["weak"]:
            changed = _reduce_antidote(pois_by, ant_by, "medium", "weak", "weak", logs,
                                      "Среднее противоядие + слабый яд ⇒ остаётся слабое противоядие") or changed

        # повторно пробуем same-tier
        for tier in ("strong", "medium", "weak"):
            before = (len(pois_by[tier]), len(ant_by[tier]))
            _cancel_same_tier(pois_by, ant_by, tier, logs)
            after = (len(pois_by[tier]), len(ant_by[tier]))
            if before != after:
                changed = True

    # 7) собрать обратно
    final_atoms: List[EffectAtom] = list(others)
    for tier in ("deadly", "strong", "medium", "weak"):
        final_atoms.extend(pois_by[tier])
    for tier in ("deadly", "strong", "medium", "weak"):
        final_atoms.extend(ant_by[tier])

    # 8) взаимные отмены (truth/lie etc)
    for pair in cfg.get("mutual_exclusive_pairs", []):
        a = pair["a"]; b = pair["b"]
        final_atoms = _cancel_pairwise(final_atoms, a, b, logs)

    # 9) простые блокировки "если есть X, то убрать Y"
    for br in cfg.get("block_rules", []):
        if "then_block" in br:
            final_atoms = _block_by_presence(final_atoms, br["if_any_of"], br["then_block"], logs, br.get("note", ""))

    # 10) спец-правило: gender_toxin блокируется cant_sleep ИЛИ sobriety (упрощенно)
    if any(a.kind == "gender_toxin" for a in final_atoms):
        if any(a.kind in ("cant_sleep", "sobriety") for a in final_atoms):
            final_atoms = [a for a in final_atoms if a.kind != "gender_toxin"]
            logs.append(ResolveLog(action="block", details="Ядовито для женщин... подавлено (есть 'невозможно уснуть' или отрезвление)"))

    # 11) Если мы разворачивали композитные яды:
    # - restore_energy блокирует energy_down
    if any(a.kind == "restore_energy" for a in final_atoms):
        removed = [a for a in final_atoms if a.kind == "energy_down"]
        if removed:
            final_atoms = [a for a in final_atoms if a.kind != "energy_down"]
            logs.append(ResolveLog(action="block", details="Восстановление энергии блокирует понижение энергии"))

    # - stop_bleeding/healing блокируют bleeding
    if any(a.kind in ("stop_bleeding", "healing") for a in final_atoms):
        removed = [a for a in final_atoms if a.kind == "bleeding"]
        if removed:
            final_atoms = [a for a in final_atoms if a.kind != "bleeding"]
            logs.append(ResolveLog(action="block", details="Кровоостанавливающее/исцеление блокирует кровотечение"))

    # 12) схлопываем яды и противоядия (по требованию: в результате остается один, самый сильный)
    final_atoms = _collapse_strongest(final_atoms, "poison", cfg, logs)
    final_atoms = _collapse_strongest(final_atoms, "antidote", cfg, logs)

    # 13) итоговые тексты
    final_texts = [a.text for a in final_atoms]

    # 14) лимит эффектов
    max_eff = int(cfg.get("max_final_effects", 999))
    if len(final_texts) > max_eff:
        violations.append(f"Слишком много итоговых эффектов: {len(final_texts)} (лимит {max_eff})")

    return ResolveResult(final_effects=final_texts, logs=logs, violations=violations)


# -----------------------------
# Token-level helper
# -----------------------------

def resolve_formula_tokens(tokens: Sequence[str], ingredient_db: Dict[str, Dict[str, str]],
                           cfg: Dict[str, Any], cats: Dict[str, Dict[str, Any]]) -> ResolveResult:
    """
    tokens: ["KQ1", "FN2", ...]
    ingredient_db:
        {"KQ": {"main": "...", "add1": "...", "add2": "...", "add3": "..."}, ...}

    1) validate tokens (дубли)
    2) expand into effect texts (main + выбранный add)
    3) resolve suppressions
    """
    validate_formula_tokens(tokens)

    effect_texts: List[str] = []
    for token in tokens:
        code, idx = parse_token(token)
        if code not in ingredient_db:
            raise KeyError(f"Unknown ingredient code: {code}")
        ing = ingredient_db[code]
        main = ing.get("main")
        add = ing.get(f"add{idx}")
        if not isinstance(main, str) or not main.strip():
            raise ValueError(f"Missing main effect for {code}")
        if not isinstance(add, str) or not add.strip():
            raise ValueError(f"Missing add{idx} effect for {code}")
        effect_texts.append(main)
        effect_texts.append(add)

    return resolve_effect_texts(effect_texts, cfg, cats)


# -----------------------------
# Minimal demo
# -----------------------------
if __name__ == "__main__":
    # пример использования (предполагается, что csv/json лежат рядом)
    # effect_categories_v5.csv / suppression_rules_v5.json / ingredients_v5.json
    import os

    base = os.path.dirname(__file__) or "."
    cats = load_effect_categories(os.path.join(base, "effect_categories_v5.csv"))
    cfg = load_json(os.path.join(base, "suppression_rules_v5.json"))
    ing = load_json(os.path.join(base, "ingredients_v5.json"))["ingredients"]

    demo_tokens = ["FS1", "FR1", "KQ1"]  # заменить на свои
    out = resolve_formula_tokens(demo_tokens, ing, cfg, cats)
    print("FINAL:", out.final_effects)
    for l in out.logs:
        print("-", l.action, l.details)
    if out.violations:
        print("VIOLATIONS:", out.violations)
