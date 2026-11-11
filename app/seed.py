"""Carga de datos. Uso:
    python -m app.seed --reset            # borra todo y carga catálogo + familias DEMO
    python -m app.seed --reset --sin-demo # borra todo y carga solo el catálogo (piloto real)
"""
import argparse
import json
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import BUDGETS, CATEGORIES, WEEKDAY_CODE, ZONES
from .config import DATA_DIR, BASE_DIR, DEMO, now
from .db import Base, SessionLocal, engine
from .models import Activity, Attendance, Booking, Child, Provider, User
from .recommender import recommend
from .services import log

CATALOGO = BASE_DIR / "app" / "data" / "catalogo.json"
ADMIN_PHONE, DEMO_FAMILY_PHONE = "900000000", "922222222"

NOMBRES_PADRES = ["Rosa", "Carlos", "Mariela", "Jorge", "Lucía", "Víctor", "Karina", "Luis", "Sandra", "Edwin",
                  "Patricia", "Hugo", "Gladys", "Marco", "Elena", "Raúl", "Silvia", "Percy", "Yesenia", "Wilber"]
APELLIDOS = ["Quispe", "Huamán", "Mamani", "Condori", "Ccori", "Flores", "Sinchi", "Challco", "Pumayalli", "Valdez"]
NOMBRES_NINOS = ["Mateo", "Valentina", "Thiago", "Camila", "Diego", "Luciana", "Sebastián", "Antonella",
                 "Gael", "Fernanda", "Joaquín", "Mía", "Andrés", "Renata", "Bruno", "Alessia"]


def load_catalog(db: Session) -> int:
    data = json.loads(CATALOGO.read_text(encoding="utf-8"))
    demo = bool(data.get("demo", True))
    n = 0
    for p in data["proveedores"]:
        user = User(phone=p["phone"], name=p["name"], role="provider", is_demo=demo, consent_at=now())
        prov = Provider(user=user, name=p["name"], kind=p["kind"], zone=p["zone"], address=p["address"],
                        description=p["description"], yape=p.get("yape", ""), verified_at=now(),
                        checks_csv="|".join(p["checks"]))
        for a in p["activities"]:
            prov.activities.append(Activity(
                name=a["name"], category=a["category"], min_age=a["min_age"], max_age=a["max_age"],
                days_csv=a["days"], start=a["start"], end=a["end"], price_month=a["price_month"],
                trial_price=a["trial_price"], capacity=a["capacity"], level=a["level"], safety=a["safety"]))
            n += 1
        db.add(prov)
    db.commit()
    return n


def load_demo_families(db: Session, n: int = 30, seed: int = 42) -> None:
    """Familias FICTICIAS con 5 semanas de historia, para que el panel de métricas no esté vacío.
    Todo queda marcado is_demo=True y se puede excluir en /metricas?reales=1."""
    rng = random.Random(seed)
    t = now()
    for i in range(n):
        phone = DEMO_FAMILY_PHONE if i == 0 else f"96{rng.randrange(10**7):07d}"
        if db.scalar(select(User).where(User.phone == phone)):
            continue
        created = t - timedelta(days=rng.randrange(0, 35), hours=rng.randrange(0, 12), minutes=rng.randrange(60))
        parent = User(phone=phone, name=f"{rng.choice(NOMBRES_PADRES)} {rng.choice(APELLIDOS)}", role="parent",
                      is_demo=True, consent_at=created + timedelta(minutes=1), created_at=created)
        db.add(parent)
        db.flush()
        interests = rng.sample(list(CATEGORIES), rng.randint(1, 3))
        child = Child(parent=parent, name=rng.choice(NOMBRES_NINOS), age=rng.randint(5, 14),
                      interests_csv=",".join(interests),
                      days_csv=",".join(rng.sample(WEEKDAY_CODE, rng.randint(3, 6))),
                      slots_csv=",".join(rng.sample(["manana", "tarde", "noche"], rng.randint(1, 3))),
                      zone=rng.choice(ZONES), budget=rng.choice([b for b, _ in BUDGETS]), created_at=created)
        db.add(child)
        db.flush()
        q0 = created + timedelta(minutes=2)
        q1 = q0 + timedelta(minutes=rng.uniform(1.5, 4))
        log(db, "q_start", parent.id, ts=q0)
        log(db, "q_done", parent.id, ts=q1)
        recos = recommend(db, child)
        if recos:
            log(db, "reco_view", parent.id, ts=q1 + timedelta(seconds=20))
        if not recos or rng.random() > 0.78:
            continue
        act = recos[0].activity
        b_ts = q1 + timedelta(minutes=rng.uniform(2, 11))
        kind = "prueba" if act.trial_price == 0 and rng.random() < 0.7 else "mensual"
        _book(db, parent, child, act, kind, b_ts, t, rng)
        # Prueba -> mensualidad una semana después
        if kind == "prueba" and rng.random() < 0.55 and b_ts + timedelta(days=7) < t:
            _book(db, parent, child, act, "mensual", b_ts + timedelta(days=7), t, rng)
        # Algunas familias repiten con una segunda actividad
        if len(recos) > 1 and rng.random() < 0.3:
            _book(db, parent, child, recos[1].activity, "prueba", b_ts + timedelta(days=rng.randint(2, 6)), t, rng)
    db.commit()


def _book(db, parent, child, act, kind, ts, t, rng) -> None:
    if ts > t:
        return
    amount = act.trial_price if kind == "prueba" else act.price_month
    recent_unpaid = amount > 0 and (t - ts) < timedelta(days=2) and rng.random() < 0.5
    status = "pendiente" if recent_unpaid else "confirmada"
    b = Booking(child=child, activity=act, kind=kind, amount=amount, status=status, created_at=ts)
    db.add(b)
    db.flush()
    log(db, "booking", parent.id, f"{b.id}:{kind}", ts=ts)
    if status != "confirmada":
        return
    log(db, "booking_confirmed", parent.id, str(b.id), ts=ts)
    day = ts.date()
    sessions = 0
    while day < t.date() and sessions < (1 if kind == "prueba" else 40):
        day += timedelta(days=1)
        if day < t.date() and WEEKDAY_CODE[day.weekday()] in act.days:
            present = rng.random() < 0.86
            db.add(Attendance(booking_id=b.id, day=day, present=present))
            if present:
                log(db, "attendance", parent.id, str(b.id), ts=datetime.combine(day, datetime.min.time()))
            sessions += 1


def ensure_seed(db: Session) -> None:
    """Carga inicial idempotente (se ejecuta al arrancar la app)."""
    if not db.scalar(select(User).where(User.role == "admin")):
        db.add(User(phone=ADMIN_PHONE, name="Equipo MIYJO", role="admin", consent_at=now()))
        db.commit()
    if not db.scalar(select(Provider)):
        load_catalog(db)
    if DEMO and not db.scalar(select(User).where(User.is_demo.is_(True), User.role == "parent")):
        load_demo_families(db)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="borra la base de datos antes de cargar")
    ap.add_argument("--sin-demo", action="store_true", help="no crear familias de demostración")
    args = ap.parse_args()
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(User(phone=ADMIN_PHONE, name="Equipo MIYJO", role="admin", consent_at=now())) if not db.scalar(
            select(User).where(User.role == "admin")) else None
        db.commit()
        if not db.scalar(select(Provider)):
            print(f"Actividades cargadas: {load_catalog(db)}")
        if not args.sin_demo:
            load_demo_families(db)
            print("Familias de demostración cargadas.")
    print(f"Base de datos lista en {DATA_DIR}")


if __name__ == "__main__":
    main()
