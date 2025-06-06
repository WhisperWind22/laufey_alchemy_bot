import pytest
from alchemy_tools.utils import split_formula

def test_split_formula():
    formula = ["ING0", "HERB2", "POW1"]
    ingredients, orders = split_formula(formula)
    assert ingredients == ["ING", "HERB", "POW"]
    assert orders == [0, 2, 1]
