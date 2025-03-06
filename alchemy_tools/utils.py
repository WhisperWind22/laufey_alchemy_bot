def split_formula(formula):
    return [x[:-1] for x in formula], [int(x[-1]) for x in formula]
