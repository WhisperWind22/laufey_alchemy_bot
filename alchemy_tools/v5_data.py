from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import importlib.util
import json
import csv


ROOT_DIR = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    # Default to v5 pack under repo root; allow override for deployment.
    override = (Path.cwd() / "alchemy_bot_data_v5")
    env = None
    try:
        import os

        env = os.getenv("ALCHEMY_DATA_DIR")
    except Exception:
        env = None
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    if override.is_dir():
        return override
    return ROOT_DIR / "alchemy_bot_data_v5"


@dataclass(frozen=True)
class V5Data:
    data_dir: Path
    ingredient_db: Dict[str, Dict[str, Any]]
    effect_categories: Dict[str, Dict[str, Any]]
    suppression_cfg: Dict[str, Any]
    suppression_mod: Any


_CACHE: Optional[V5Data] = None


def _import_effect_suppression_v5(data_dir: Path):
    mod_path = data_dir / "effect_suppression_v5.py"
    if not mod_path.exists():
        raise FileNotFoundError(f"Missing {mod_path}")

    spec = importlib.util.spec_from_file_location("effect_suppression_v5_pack", str(mod_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import effect_suppression_v5.py")

    module = importlib.util.module_from_spec(spec)
    # Python 3.13+ dataclasses rely on the module being present in sys.modules
    # during class decoration (see dataclasses._is_type()).
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_v5_data() -> V5Data:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    data_dir = _data_dir()
    mod = _import_effect_suppression_v5(data_dir)

    cfg = json.loads((data_dir / "suppression_rules_v5.json").read_text(encoding="utf-8"))
    ingredients = json.loads((data_dir / "ingredients_v5.json").read_text(encoding="utf-8"))["ingredients"]
    cats = mod.load_effect_categories(str(data_dir / "effect_categories_v5.csv"))

    _CACHE = V5Data(
        data_dir=data_dir,
        ingredient_db=ingredients,
        effect_categories=cats,
        suppression_cfg=cfg,
        suppression_mod=mod,
    )
    return _CACHE


def resolve_tokens(tokens: List[str]):
    v5 = load_v5_data()
    return v5.suppression_mod.resolve_formula_tokens(tokens, v5.ingredient_db, v5.suppression_cfg, v5.effect_categories)


def get_add_effects_for_code(code: str) -> List[str]:
    v5 = load_v5_data()
    ing = v5.ingredient_db.get(code)
    if not ing:
        return []
    return [ing.get("add1", ""), ing.get("add2", ""), ing.get("add3", "")]


def get_main_effect_for_code(code: str) -> str:
    v5 = load_v5_data()
    ing = v5.ingredient_db.get(code)
    if not ing:
        return ""
    return ing.get("main", "") or ""


def search_effect_texts(query: str, limit: int = 12) -> List[str]:
    """
    Search canonical effect texts (v5) for selection UI.
    """
    v5 = load_v5_data()
    q = v5.suppression_mod.normalize_key(query)
    if not q:
        return []

    # We don't store the raw list in memory; scan CSV once and cache would be nice,
    # but 200-300 rows is small.
    path = v5.data_dir / "effect_categories_v5.csv"
    scored: List[Tuple[Tuple[int, int], str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = v5.suppression_mod.normalize_text(row.get("effect_text", ""))
            if not text:
                continue
            tl = v5.suppression_mod.normalize_key(text)
            pos = tl.find(q)
            if pos < 0:
                continue
            scored.append(((pos, len(text)), text))
    scored.sort(key=lambda x: (x[0], x[1].lower()))
    return [t for _s, t in scored[:limit]]


def tokens_producing_effect(effect_text: str, limit: int = 30) -> List[str]:
    """
    Return selection tokens CODE1/2/3 where either main or add matches effect_text.
    """
    v5 = load_v5_data()
    target = v5.suppression_mod.normalize_text(effect_text)
    out: List[str] = []
    for code, ing in v5.ingredient_db.items():
        main = v5.suppression_mod.normalize_text(ing.get("main", ""))
        if main == target:
            out.extend([f"{code}1", f"{code}2", f"{code}3"])
            continue
        for i in (1, 2, 3):
            add = v5.suppression_mod.normalize_text(ing.get(f"add{i}", ""))
            if add == target:
                out.append(f"{code}{i}")
    out.sort()
    return out[:limit]
