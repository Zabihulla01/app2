def risk_score(
    pf,
    sharpe,
    dd
):

    if dd > 30:
        dd_penalty = 30
    elif dd > 20:
        dd_penalty = 15
    elif dd > 10:
        dd_penalty = 5
    else:
        dd_penalty = 0

    score = (
        min(pf * 15, 45)
        +
        min(sharpe * 20, 35)
        +
        ((100 - dd) * 0.20)
        -
        dd_penalty
    )

    score = max(score, 0)

    score = min(score, 100)

    return round(score, 2)
