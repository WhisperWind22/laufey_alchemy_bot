# Alchemy bot data pack v5

Содержимое:
- `ingredients_v5.json` — база ингредиентов (код -> название, материал, основной эффект + 3 доп. эффекта)
- `ingredient_effects_v5.csv` — эффекты ингредиентов в “длинном” виде
- `effect_categories_v5.csv` — категоризация каждого уникального текста эффекта (kind/tier/tags)
- `ingredient_effect_categories_v5.csv` — эффекты ингредиентов + их категории (для проверки/отладки)
- `suppression_rules_v5.json` — правила подавления/схлопывания эффектов
- `effect_suppression_v5.py` — модуль расчёта подавления

Ключевые правила (v5):
- Дубликаты: один и тот же токен `CODE1/2/3` нельзя использовать дважды. Разрешено повторять `CODE` с разными цифрами.
- Итоговых эффектов (после подавлений и схлопывания яда/противоядия) должно быть **не более 4**.
- Яды в результате: остаётся **один** (самый сильный).
- Противоядия в результате: остаётся **одно** (самое сильное).
- Противоядие от смертельных ядов может блокировать пакеты ядов: 1 смертельный или 2 сильных или 3 средних или 4 слабых или 1 сильный + 2 средних.

Использование:
```python
from effect_suppression_v5 import load_effect_categories, load_json, resolve_formula_tokens

cats = load_effect_categories("effect_categories_v5.csv")
cfg = load_json("suppression_rules_v5.json")
ing = load_json("ingredients_v5.json")["ingredients"]

result = resolve_formula_tokens(["KQ1","FN2","FS3"], ing, cfg, cats)
print(result.final_effects)
print(result.violations)
for log in result.logs:
    print(log.action, log.details)
```
