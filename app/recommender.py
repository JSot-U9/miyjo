"""Motor de recomendación explicable (reglas + puntaje, sin ML).

Puntaje 0-100:  interés 40 · horario 25 (días 15 + franja 10) · zona 20 · presupuesto 15.
Filtros duros: edad, cupos, al menos un día en común, precio no mayor a 130 % del presupuesto.
Cada recomendación devuelve las razones en lenguaje simple: es lo que genera confianza en el padre.
"""
from dataclasses import dataclass, field

from .catalog import ADJACENT, CATEGORIES, DAY_LABEL, ZONE_ANY, slot_of

MIN_SCORE = 35
MAX_PER_CATEGORY = 2


@dataclass
class Reco:
    activity: object
    score: int
    reasons: list[str] = field(default_factory=list)
    spots_left: int = 0


def score_activity(child, act, spots_left: int) -> Reco | None:
    if not (act.min_age <= child.age <= act.max_age) or spots_left <= 0:
        return None
    common = [d for d in act.days if d in child.days]
    if not common:
        return None
    if act.price_month > child.budget * 1.3:
        return None

    score, reasons = 0, [f"Para niños de {act.min_age} a {act.max_age} años"]

    cat = CATEGORIES.get(act.category, {"label": act.category, "group": ""})
    if not child.interests:  # "No sé, muéstrame variedad": puntaje neutro para todas
        score += 20
        reasons.insert(0, f"Para probar algo nuevo: {cat['label'].lower()}")
    elif act.category in child.interests:
        score += 40
        reasons.insert(0, f"Le gusta {cat['label'].lower()}")
    elif any(CATEGORIES.get(i, {}).get("group") == cat["group"] for i in child.interests):
        score += 15
        reasons.insert(0, f"Parecida a lo que le gusta ({cat['label'].lower()})")

    score += round(15 * len(common) / len(act.days))
    days_txt = " · ".join(DAY_LABEL[d] for d in common)
    if not child.slots or slot_of(act.start) in child.slots:
        score += 10
        reasons.append(f"Horario que te sirve: {days_txt} a las {act.start}")
    else:
        reasons.append(f"Días que te sirven: {days_txt} (a las {act.start})")

    zone = act.provider.zone
    if child.zone in ("", ZONE_ANY):
        score += 10
    elif zone == child.zone:
        score += 20
        reasons.append(f"Queda en tu zona ({zone})")
    elif zone in ADJACENT.get(child.zone, ()):
        score += 10
        reasons.append(f"Zona cercana ({zone})")

    if act.price_month <= child.budget:
        score += 15
        reasons.append(f"S/ {act.price_month} al mes, dentro de tu presupuesto")
    else:
        score += 7
        reasons.append(f"S/ {act.price_month} al mes, un poco sobre tu presupuesto")

    if act.trial_price == 0:
        reasons.append("Primera clase de prueba gratis")

    if score < MIN_SCORE:
        return None
    return Reco(activity=act, score=min(score, 100), reasons=reasons, spots_left=spots_left)


def pick_top(scored: list[Reco], k: int = 3) -> list[Reco]:
    """Top-k por puntaje, con variedad: máximo 2 de la misma categoría si hay alternativas."""
    ranked = sorted(scored, key=lambda r: (-r.score, r.activity.price_month, r.activity.id))
    chosen, per_cat = [], {}
    for r in ranked:
        c = r.activity.category
        if per_cat.get(c, 0) < MAX_PER_CATEGORY:
            chosen.append(r)
            per_cat[c] = per_cat.get(c, 0) + 1
        if len(chosen) == k:
            return chosen
    for r in ranked:  # relleno si la variedad dejó menos de k
        if r not in chosen:
            chosen.append(r)
        if len(chosen) == k:
            break
    return chosen


def ranked_all(db, child) -> list[Reco]:
    """Todas las actividades compatibles con el niño, de mayor a menor puntaje."""
    from sqlalchemy import func, select

    from .models import Activity, Booking

    taken = dict(db.execute(
        select(Booking.activity_id, func.count()).where(Booking.status != "cancelada").group_by(Booking.activity_id)
    ).all())
    acts = db.scalars(select(Activity).where(Activity.active.is_(True))).all()
    scored = [r for a in acts if (r := score_activity(child, a, a.capacity - taken.get(a.id, 0)))]
    return sorted(scored, key=lambda r: (-r.score, r.activity.price_month, r.activity.id))


def recommend(db, child, k: int = 3) -> list[Reco]:
    return pick_top(ranked_all(db, child), k)


def more_options(db, child, k: int = 3, n: int = 6) -> tuple[list[Reco], list[Reco]]:
    """(top k con variedad, siguientes n opciones) sin repetir actividades."""
    ranked = ranked_all(db, child)
    top = pick_top(ranked, k)
    ids = {r.activity.id for r in top}
    return top, [r for r in ranked if r.activity.id not in ids][:n]
