# -*- coding: utf-8 -*-
"""
Alchemy effect suppression / categorization (v4)

Key changes vs v3:
- MAX_EFFECTS reduced to 4 (house rule for the bot/validator).
- In the final result, poisons collapse to ONLY the strongest remaining poison tier (single effect).
- In the final result, antidotes collapse to ONLY the strongest remaining antidote tier (single effect).

This module is standalone: feed it raw effect texts (main effects + selected additional effects)
and it will return:
- remaining effects (as human-readable texts)
- a suppression log
- validity by the MAX_EFFECTS rule

Reverse-brewing support:
- Set reverse=True to invert a subset of well-defined opposite categories.
  (Full opposite mapping for arbitrary RAW effects requires an external table.)
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import csv
import re


MAX_EFFECTS = 4  # v4 rule (bot/validator)


TIER_ORDER = ["weak", "medium", "strong", "deadly"]
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}

TIER_RU = {
    "weak": "Слабый",
    "medium": "Средний",
    "strong": "Сильный",
    "deadly": "Смертельный",
}

# ---------------------------------------------------------------------
# Token model
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SuppressionResult:
    """Result of suppression."""
    active_tokens: List[str]         # internal tokens (deduped)
    active_effects: List[str]        # human-readable effects
    log: List[str]                   # suppression steps
    effect_count: int                # number of active effects (<= MAX_EFFECTS required)
    valid: bool


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _lower(s: str) -> str:
    return _norm(s).lower()

def _load_effect_catalog() -> Dict[str, Tuple[str, str]]:
    """
    Load effect_text -> (kind, tier) mapping from effect_categories_v4.csv.
    """
    path = Path(__file__).resolve().parent / "effect_categories_v4.csv"
    if not path.exists():
        return {}
    catalog: Dict[str, Tuple[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = _norm(row.get("effect_text", ""))
            if not text:
                continue
            kind = (row.get("kind", "") or "").strip()
            tier = (row.get("tier", "") or "").strip()
            catalog[_lower(text)] = (kind, tier)
    return catalog


EFFECT_CATALOG = _load_effect_catalog()

KIND_TO_TOKEN = {
    "balance": "BALANCE",
    "cannot_sleep": "CANNOT_SLEEP",
    "carefree": "CAREFREE",
    "hallucinations": "HALLUCINATIONS",
    "healing_phys": "HEALING_PHYS",
    "intoxication": "INTOXICATION",
    "kleptomania": "KLEPTOMANIA",
    "lie": "LIE",
    "mental_cleanse": "MENTAL_CLEANSE",
    "mental_def_down": "MENTAL_DEF_DOWN",
    "mental_protect": "MENTAL_PROTECT",
    "restore_energy": "RESTORE_ENERGY",
    "sleep": "SLEEP",
    "sobriety": "SOBRIETY",
    "stop_bleeding": "STOP_BLEEDING",
    "tempt_resist": "TEMPT_RESIST",
    "truth": "TRUTH",
    "varvara": "VARVARA",
    "wake": "WAKE",
}


# ---------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------

def detect_poison_tier(text: str) -> Optional[str]:
    t = _lower(text)
    if "яд" not in t:
        return None
    if "противояд" in t:
        return None
    if "смерт" in t:
        return "deadly"
    if "сильн" in t:
        return "strong"
    if "средн" in t:
        return "medium"
    if "слаб" in t:
        return "weak"
    # fallback: treat unspecified "яд" as weak
    return "weak"


def detect_antidote_tier(text: str) -> Optional[str]:
    t = _lower(text)
    if "противояд" not in t:
        return None
    if "смерт" in t:
        return "deadly"
    if "сильн" in t:
        return "strong"
    if "средн" in t:
        return "medium"
    if "слаб" in t:
        return "weak"
    # e.g. "противоядие против средних ядов"
    if "против" in t and "средн" in t:
        return "medium"
    return "weak"


def _is_balance(text: str) -> bool:
    return "уравновеш" in _lower(text)


def _is_carefree(text: str) -> bool:
    return "легкомысли" in _lower(text)


def _is_sobriety(text: str) -> bool:
    t = _lower(text)
    return "отрезв" in t or "выводит из состояния опьянения" in t


def _is_intoxication(text: str) -> bool:
    t = _lower(text)
    if "опьян" in t:
        return True
    if "эйфори" in t and ("опьян" in t or "схож" in t):
        return True
    return False


def _is_sleep(text: str) -> bool:
    t = _lower(text)
    return "снотвор" in t or ("погруж" in t and "сон" in t) or ("вводит" in t and "сон" in t)


def _is_wake(text: str) -> bool:
    t = _lower(text)
    return ("бодрост" in t) or ("бодрит" in t) or ("тониз" in t) or ("пробужда" in t)


def _is_cannot_sleep(text: str) -> bool:
    return "невозможно уснуть" in _lower(text)


def _is_hallucinations(text: str) -> bool:
    t = _lower(text)
    return ("галлюцина" in t) or ("галюцина" in t) or ("кошмары на яву" in t) or ("кошмар" in t and "яву" in t)


def _is_truth(text: str) -> bool:
    t = _lower(text)
    return ("правд" in t) and ("говор" in t or "побуждает" in t or "заставляет" in t)


def _is_lie(text: str) -> bool:
    t = _lower(text)
    return "врать" in t or "врет" in t or "вран" in t


def _is_tempt_resist(text: str) -> bool:
    t = _lower(text)
    return "стойкост" in t and "соблазн" in t


def _is_varvara(text: str) -> bool:
    t = _lower(text)
    return "любопытная" in t and "варвар" in t


def _is_kleptomania(text: str) -> bool:
    t = _lower(text)
    return "клептоман" in t


def _is_mental_cleanse(text: str) -> bool:
    t = _lower(text)
    return ("разрушает наложенное ментальное воздействие" in t) or ("снятие менталь" in t)


def _is_mental_def_down(text: str) -> bool:
    t = _lower(text)
    return "ослабляет ментальную защиту" in t or ("ослабляет" in t and "ментальн" in t and "защит" in t)


def _is_mental_protect(text: str) -> bool:
    t = _lower(text)
    if _is_mental_def_down(text):
        return False
    if "против менталь" in t:
        return True
    if "улучшает ментальную защиту" in t:
        return True
    if "повышает ментальную защиту" in t:
        return True
    if "ментальная защита" in t and ("повыш" in t or "улучш" in t):
        return True
    if "прояснен" in t:
        return True
    return False


def _is_bleeding(text: str) -> bool:
    return "кровотеч" in _lower(text)


def _is_stop_bleeding(text: str) -> bool:
    t = _lower(text)
    return ("кровоостанавливающее" in t) or ("останавливает кровотечение" in t)


def _is_restore_energy(text: str) -> bool:
    return "восстанавливает энергию" in _lower(text)


def _is_energy_down(text: str) -> bool:
    t = _lower(text)
    return ("понижает энергию" in t) or ("энерг" in t and ("пониж" in t or "сниж" in t))


def _is_healing_phys(text: str) -> bool:
    t = _lower(text)
    return (
        "исцеляет физические раны" in t
        or "лечить физические раны" in t
        or "способно лечить физические раны" in t
        or "заживляет раны" in t
        or "восстанавливает хиты" in t
        or "востановления хитов" in t
    )


def categorize_effect_text(text: str) -> List[str]:
    """
    Convert a single effect text into one or more internal tokens.
    Composite effects can produce multiple tokens (e.g. poison + bleeding).
    """
    text = _norm(text)
    if not text:
        return []
    lt = _lower(text)

    catalog_entry = EFFECT_CATALOG.get(lt)
    if catalog_entry:
        kind, tier = catalog_entry
        if kind == "raw" or not kind:
            return [f"RAW:{text}"]
        if kind == "poison":
            tier = tier if tier in TIER_RANK else (detect_poison_tier(text) or "weak")
            toks = [f"POISON:{tier}"]
            if _is_bleeding(text):
                toks.append("BLEEDING")
            if _is_energy_down(text):
                toks.append("ENERGY_DOWN")
            return toks
        if kind == "antidote":
            tier = tier if tier in TIER_RANK else (detect_antidote_tier(text) or "weak")
            return [f"ANTIDOTE:{tier}"]
        mapped = KIND_TO_TOKEN.get(kind)
        if mapped:
            return [mapped]
        return [f"RAW:{text}"]

    # Special / categorical first
    if _is_tempt_resist(text):
        return ["TEMPT_RESIST"]
    if _is_kleptomania(text):
        return ["KLEPTOMANIA"]
    if _is_varvara(text):
        return ["VARVARA"]
    if _is_truth(text):
        return ["TRUTH"]
    if _is_lie(text):
        return ["LIE"]
    if _is_sobriety(text):
        return ["SOBRIETY"]
    if _is_intoxication(text):
        return ["INTOXICATION"]
    if _is_balance(text):
        return ["BALANCE"]
    if _is_carefree(text):
        return ["CAREFREE"]
    if _is_cannot_sleep(text):
        return ["CANNOT_SLEEP"]
    if _is_wake(text):
        return ["WAKE"]
    if _is_sleep(text):
        return ["SLEEP"]
    if _is_hallucinations(text):
        return ["HALLUCINATIONS"]
    if _is_mental_cleanse(text):
        return ["MENTAL_CLEANSE"]
    if _is_mental_def_down(text):
        return ["MENTAL_DEF_DOWN"]
    if _is_mental_protect(text):
        return ["MENTAL_PROTECT"]

    # Antidote / poison + composites
    at = detect_antidote_tier(text)
    if at:
        return [f"ANTIDOTE:{at}"]

    pt = detect_poison_tier(text)
    if pt:
        toks = [f"POISON:{pt}"]
        if _is_bleeding(text):
            toks.append("BLEEDING")
        if _is_energy_down(text):
            toks.append("ENERGY_DOWN")
        return toks

    # Physical / energy / healing
    if _is_stop_bleeding(text):
        return ["STOP_BLEEDING"]
    if _is_bleeding(text):
        return ["BLEEDING"]
    if _is_restore_energy(text):
        return ["RESTORE_ENERGY"]
    if _is_energy_down(text):
        return ["ENERGY_DOWN"]
    if _is_healing_phys(text):
        return ["HEALING_PHYS"]

    return [f"RAW:{text}"]


# ---------------------------------------------------------------------
# Reverse formula support
# ---------------------------------------------------------------------

def invert_token(token: str) -> str:
    """
    Invert a token for reverse-brewing (partial mapping).
    Unknown/RAW tokens are left unchanged.
    """
    if token.startswith("POISON:"):
        return "ANTIDOTE:" + token.split(":", 1)[1]
    if token.startswith("ANTIDOTE:"):
        return "POISON:" + token.split(":", 1)[1]

    mapping = {
        "SLEEP": "WAKE",
        "WAKE": "SLEEP",
        "CANNOT_SLEEP": "SLEEP",
        "TRUTH": "LIE",
        "LIE": "TRUTH",
        "SOBRIETY": "INTOXICATION",
        "INTOXICATION": "SOBRIETY",
        "BALANCE": "CAREFREE",
        "CAREFREE": "BALANCE",
    }
    return mapping.get(token, token)


# ---------------------------------------------------------------------
# Suppression engine
# ---------------------------------------------------------------------

def _max_tier(tiers: List[str]) -> str:
    return max(tiers, key=lambda x: TIER_RANK[x])


def resolve_tokens(tokens: List[str], max_effects: int = MAX_EFFECTS) -> SuppressionResult:
    """
    Core suppression routine (v4).
    Input: internal tokens.
    Output: active effects list (<=max_effects required).
    """
    log: List[str] = []

    c = Counter(tokens)

    # --- poison/antidote extraction
    poison = Counter()
    antidote = Counter()
    for tok in list(c.keys()):
        if tok.startswith("POISON:"):
            tier = tok.split(":", 1)[1]
            poison[tier] += c[tok]
            del c[tok]
        elif tok.startswith("ANTIDOTE:"):
            tier = tok.split(":", 1)[1]
            antidote[tier] += c[tok]
            del c[tok]

    # --- deadly poison vs deadly antidote (1:1)
    use = min(poison.get("deadly", 0), antidote.get("deadly", 0))
    if use:
        poison["deadly"] -= use
        antidote["deadly"] -= use
        log.append(f"Смертельный яд x{use} подавлен противоядием от смертельных ядов x{use}")

    # --- deadly antidote bundles for non-deadly poisons
    bundles: List[Tuple[str, Counter]] = [
        ("2 сильных", Counter({"strong": 2})),
        ("1 сильный + 2 средних", Counter({"strong": 1, "medium": 2})),
        ("3 средних", Counter({"medium": 3})),
        ("4 слабых", Counter({"weak": 4})),
    ]

    def poison_vec(p: Counter) -> Tuple[int, int, int, int]:
        return (p.get("deadly", 0), p.get("strong", 0), p.get("medium", 0), p.get("weak", 0))

    while antidote.get("deadly", 0) > 0:
        best = None
        best_name = None
        best_vec = None
        for name, b in bundles:
            if all(poison.get(k, 0) >= v for k, v in b.items()):
                cand = poison.copy()
                for k, v in b.items():
                    cand[k] -= v
                vec = poison_vec(cand)
                if best is None or vec < best_vec:
                    best = b
                    best_name = name
                    best_vec = vec
        if best is None:
            break
        antidote["deadly"] -= 1
        for k, v in best.items():
            poison[k] -= v
        log.append(f"Противоядие от смертельных ядов (1) подавило пакет: {best_name}")

    # --- resolve non-deadly poisons vs antidotes (strongest-first matching)
    tiers = ["strong", "medium", "weak"]

    def pop_strongest(counter: Counter) -> Optional[str]:
        for t in tiers:
            if counter.get(t, 0) > 0:
                counter[t] -= 1
                return t
        return None

    pnd = Counter({t: poison.get(t, 0) for t in tiers})
    andt = Counter({t: antidote.get(t, 0) for t in tiers})

    while sum(pnd.values()) > 0 and sum(andt.values()) > 0:
        p = pop_strongest(pnd)
        a = pop_strongest(andt)
        if p is None or a is None:
            break
        if p == a:
            log.append(f"Яд {p} подавлен противоядием {a}")
            continue
        if TIER_RANK[p] > TIER_RANK[a]:
            # poison stronger => leftover poison becomes weaker tier (a)
            pnd[a] += 1
            log.append(f"Яд {p} + противоядие {a} => остаток яд {a}")
        else:
            # antidote stronger => leftover antidote becomes weaker tier (p)
            andt[p] += 1
            log.append(f"Яд {p} + противоядие {a} => остаток противоядие {p}")

    poison_final = Counter({t: 0 for t in TIER_ORDER})
    antidote_final = Counter({t: 0 for t in TIER_ORDER})
    poison_final["deadly"] = poison.get("deadly", 0)
    antidote_final["deadly"] = antidote.get("deadly", 0)
    for t in tiers:
        poison_final[t] = pnd.get(t, 0)
        antidote_final[t] = andt.get(t, 0)
    poison = poison_final
    antidote = antidote_final

    # --- generic cancellation helper for non-poison tokens
    def cancel(a_tok: str, b_tok: str, label: str) -> None:
        n = min(c.get(a_tok, 0), c.get(b_tok, 0))
        if n <= 0:
            return
        c[a_tok] -= n
        c[b_tok] -= n
        if c[a_tok] <= 0:
            c.pop(a_tok, None)
        if c[b_tok] <= 0:
            c.pop(b_tok, None)
        log.append(f"{label}: {n}×")

    cancel("TRUTH", "LIE", "Правда ↔ ложь")
    cancel("INTOXICATION", "SOBRIETY", "Опьянение ↔ отрезвление")
    cancel("BALANCE", "CAREFREE", "Уравновешенность ↔ легкомыслие")
    cancel("SLEEP", "WAKE", "Сон ↔ бодрость/тонизирующее")

    # block sleep if any WAKE or CANNOT_SLEEP present
    if c.get("SLEEP", 0) > 0 and (c.get("WAKE", 0) > 0 or c.get("CANNOT_SLEEP", 0) > 0):
        c.pop("SLEEP", None)
        log.append("Сон/снотворное подавлено бодростью/невозможно уснуть")

    # hallucinations blocked by mental protect or cleanse
    if c.get("HALLUCINATIONS", 0) > 0 and (c.get("MENTAL_PROTECT", 0) > 0 or c.get("MENTAL_CLEANSE", 0) > 0):
        c.pop("HALLUCINATIONS", None)
        log.append("Галлюцинации подавлены ментальной защитой/снятием ментального")

    # temptation resist blocks varvara/kleptomania
    if c.get("TEMPT_RESIST", 0) > 0:
        if c.get("VARVARA", 0) > 0:
            c.pop("VARVARA", None)
            log.append('"Любопытная Варвара" подавлена стойкостью к соблазнам')
        if c.get("KLEPTOMANIA", 0) > 0:
            c.pop("KLEPTOMANIA", None)
            log.append("Клептомания подавлена стойкостью к соблазнам")

    # bleeding suppressed
    if c.get("BLEEDING", 0) > 0 and (c.get("STOP_BLEEDING", 0) > 0 or c.get("HEALING_PHYS", 0) > 0):
        c.pop("BLEEDING", None)
        log.append("Кровотечение подавлено кровоостанавливающим/исцелением")

    # energy_down suppressed by restore_energy
    if c.get("ENERGY_DOWN", 0) > 0 and c.get("RESTORE_ENERGY", 0) > 0:
        c.pop("ENERGY_DOWN", None)
        log.append("Понижение энергии подавлено восстановлением энергии")

    # --- final tokens (dedup)
    final_tokens = set(tok for tok, count in c.items() if count > 0)

    # v4: collapse poisons to only strongest remaining poison
    poison_remaining = []
    for tier, count in poison.items():
        if count > 0:
            poison_remaining.extend([tier] * count)
    if poison_remaining:
        strongest = _max_tier(poison_remaining)
        final_tokens.add(f"POISON:{strongest}")

    # v4: collapse antidotes to only strongest remaining antidote
    antidote_remaining = []
    for tier, count in antidote.items():
        if count > 0:
            antidote_remaining.extend([tier] * count)
    if antidote_remaining:
        strongest = _max_tier(antidote_remaining)
        final_tokens.add(f"ANTIDOTE:{strongest}")

    # human-readable mapping
    def token_to_text(tok: str) -> str:
        if tok.startswith("POISON:"):
            tier = tok.split(":", 1)[1]
            return f"{TIER_RU[tier]} яд"
        if tok.startswith("ANTIDOTE:"):
            tier = tok.split(":", 1)[1]
            if tier == "deadly":
                return "Противоядие от смертельных ядов"
            return f"{TIER_RU[tier]}е противоядие"

        mapping = {
            "TEMPT_RESIST": "Стойкость к соблазнам",
            "KLEPTOMANIA": "Клептомания",
            "VARVARA": "Минус «Любопытная Варвара»",
            "TRUTH": "Говорить правду",
            "LIE": "Непрерывная ложь",
            "SOBRIETY": "Отрезвление",
            "INTOXICATION": "Опьянение/эйфория",
            "BALANCE": "Уравновешенность",
            "CAREFREE": "Легкомыслие",
            "CANNOT_SLEEP": "Невозможно уснуть",
            "WAKE": "Бодрость/тонизирующее",
            "SLEEP": "Снотворное/сон",
            "HALLUCINATIONS": "Галлюцинации",
            "MENTAL_CLEANSE": "Снятие ментальных воздействий",
            "MENTAL_PROTECT": "Ментальная защита",
            "MENTAL_DEF_DOWN": "Ослабление ментальной защиты",
            "STOP_BLEEDING": "Кровоостанавливающее",
            "BLEEDING": "Кровотечение",
            "RESTORE_ENERGY": "Восстанавливает энергию",
            "ENERGY_DOWN": "Понижает энергию",
            "HEALING_PHYS": "Исцеление/заживление ран",
        }
        if tok.startswith("RAW:"):
            return tok.split(":", 1)[1]
        return mapping.get(tok, tok)

    active_effects = [token_to_text(t) for t in sorted(final_tokens)]
    effect_count = len(final_tokens)
    valid = effect_count <= max_effects

    return SuppressionResult(
        active_tokens=sorted(final_tokens),
        active_effects=active_effects,
        log=log,
        effect_count=effect_count,
        valid=valid,
    )


def suppress_effect_texts(effect_texts: List[str], reverse: bool = False, max_effects: int = MAX_EFFECTS) -> SuppressionResult:
    """
    Public API:
    - effect_texts: raw texts from ingredients (main + selected additional).
    - reverse: if True, apply partial opposite mapping before suppression.
    """
    tokens: List[str] = []
    for t in effect_texts:
        tokens.extend(categorize_effect_text(t))

    if reverse:
        tokens = [invert_token(tok) for tok in tokens]

    return resolve_tokens(tokens, max_effects=max_effects)


# ---------------------------------------------------------------------
# Recipe token validation helper
# ---------------------------------------------------------------------

_TOKEN_RE = re.compile(r"^(.+?)([1-3])$")

def parse_selection_token(token: str) -> Tuple[str, int]:
    """
    Parse a selection token like 'RK1' -> ('RK', 1)
    """
    token = _norm(token)
    m = _TOKEN_RE.match(token)
    if not m:
        raise ValueError(f"Bad token format: {token!r} (expected like 'RK1', 'SAP2', ...)")
    code = m.group(1)
    add_idx = int(m.group(2))
    return code, add_idx


def validate_recipe_tokens(tokens: List[str]) -> None:
    """
    Enforce recipe constraints for tokens like ['RK1','RK2','BA3','SZ3','FN2']:

    - No exact duplicates ('RK1' twice is forbidden).
    - Repeating the same ingredient code is allowed only with different add indices.
    - Officially, only two copies of a single ingredient are allowed in one recipe; we enforce <=2.
      (If you want to allow up to 3, relax the check below.)
    """
    if len(tokens) != 5:
        raise ValueError(f"Strong formula/cream requires 5 ingredients, got {len(tokens)}")

    if len(set(tokens)) != len(tokens):
        raise ValueError("Recipe contains exact duplicate selection tokens (e.g. 'RK1' twice)")

    counts_by_code = Counter()
    add_indices_by_code: Dict[str, set] = {}
    for tok in tokens:
        code, idx = parse_selection_token(tok)
        counts_by_code[code] += 1
        add_indices_by_code.setdefault(code, set()).add(idx)

    # enforce "same ingredient can be used twice with different additional effects"
    for code, n in counts_by_code.items():
        if n > 2:
            raise ValueError(f"Ingredient {code} is used {n} times (max 2 is allowed by the base rules)")
        if len(add_indices_by_code[code]) != n:
            raise ValueError(f"Ingredient {code} is repeated without changing the additional effect index")
