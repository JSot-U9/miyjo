from types import SimpleNamespace as NS

from app.recommender import pick_top, score_activity


def child(**kw):
    base = dict(age=8, interests=["futbol"], days=["sab", "mar"], slots=["manana", "tarde"], zone="San Sebastián", budget=100)
    return NS(**{**base, **kw})


def act(id=1, **kw):
    base = dict(id=id, name="Fútbol", category="futbol", min_age=6, max_age=10, days=["sab"], start="09:00",
                price_month=70, trial_price=0, provider=NS(zone="San Sebastián"))
    return NS(**{**base, **kw})


def test_perfect_match_scores_100():
    r = score_activity(child(), act(), spots_left=5)
    assert r and r.score == 100
    assert any("Le gusta" in x for x in r.reasons) and any("tu zona" in x for x in r.reasons)


def test_hard_filters():
    assert score_activity(child(age=12), act(), 5) is None            # edad fuera de rango
    assert score_activity(child(), act(), 0) is None                  # sin cupos
    assert score_activity(child(days=["dom"]), act(), 5) is None      # ningún día en común
    assert score_activity(child(budget=40), act(price_month=80), 5) is None  # >130 % del presupuesto


def test_adjacent_zone_and_budget_penalty():
    r = score_activity(child(zone="Wanchaq"), act(price_month=110), 5)
    assert r and r.score == 40 + 15 + 10 + 10 + 7
    assert any("Zona cercana" in x for x in r.reasons)
    assert any("sobre tu presupuesto" in x for x in r.reasons)


def test_related_interest_gets_partial_credit():
    r = score_activity(child(interests=["basquet"]), act(), 5)  # mismo grupo "equipo"
    assert r and r.score == 100 - 40 + 15


def test_low_score_excluded():
    assert score_activity(child(interests=["natacion"], zone="Santiago", slots=["noche"]),
                          act(price_month=125), 5) is None


def test_pick_top_limits_category_and_orders():
    s = [score_activity(child(), act(id=i, price_month=60 + i), 5) for i in range(1, 5)]
    s.append(score_activity(child(interests=["futbol", "karate"]), act(id=9, category="karate", price_month=70), 5))
    top = pick_top([x for x in s if x], 3)
    assert len(top) == 3
    assert sum(1 for r in top if r.activity.category == "futbol") <= 2
    assert [r.score for r in top] == sorted((r.score for r in top), reverse=True) or top[2].activity.category == "karate"
