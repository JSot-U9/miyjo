"""Métricas para patrocinadores, calculadas sobre datos reales de la base.
Los datos de demostración (is_demo) se pueden excluir para mostrar solo los del piloto."""
from datetime import timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import COMISION, now
from .models import Attendance, Booking, Event, Provider, User


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def compute(db: Session, solo_reales: bool = False) -> dict:
    t = now()
    users = db.scalars(select(User)).all()
    keep = lambda u: not (solo_reales and u.is_demo)  # noqa: E731
    parents = [u for u in users if u.role == "parent" and keep(u)]
    parent_ids = {u.id for u in parents}
    consented = [u for u in parents if u.consent_at]
    children = [c for u in parents for c in u.children]
    child_ids = {c.id for c in children}

    bookings = [b for b in db.scalars(select(Booking)).all()
                if b.child_id in child_ids and b.status != "cancelada"]
    confirmed = [b for b in bookings if b.status == "confirmada"]
    events = [e for e in db.scalars(select(Event)).all() if e.user_id in parent_ids]
    ev_users = lambda typ: {e.user_id for e in events if e.type == typ}  # noqa: E731

    # --- Embudo ---
    by_parent: dict[int, list[Booking]] = {}
    for b in bookings:
        by_parent.setdefault(b.child.parent_id, []).append(b)
    q_start, q_done, reco = ev_users("q_start"), ev_users("q_done"), ev_users("reco_view")
    booked = set(by_parent)
    # "Repite": 2+ reservas, o pasó de clase de prueba a mensualidad
    repeat = {p for p, bs in by_parent.items() if len(bs) >= 2}
    funnel = [
        ("Se registraron", len(parents)),
        ("Dieron consentimiento", len(consented)),
        ("Completaron el cuestionario", len(q_done)),
        ("Vieron sus recomendaciones", len(reco)),
        ("Hicieron una reserva", len(booked)),
        ("Repitieron (2+ reservas)", len(repeat)),
    ]

    # --- Tiempo hasta la primera reserva ---
    created = {u.id: u.created_at for u in parents}
    mins = [(min(b.created_at for b in bs) - created[p]).total_seconds() / 60
            for p, bs in by_parent.items() if p in created]

    # --- Prueba -> mensual ---
    trial_pairs = {(b.child_id, b.activity_id) for b in bookings if b.kind == "prueba"}
    conv = {(b.child_id, b.activity_id) for b in bookings if b.kind == "mensual"} & trial_pairs

    # --- Proveedores ---
    prov_users = {u.id: u for u in users if u.role == "provider" and keep(u)}
    providers = [p for p in db.scalars(select(Provider)).all() if p.user_id in prov_users]
    cutoff = t - timedelta(days=14)
    active_prov = {b.activity.provider_id for b in bookings if b.created_at >= cutoff}
    atts = [a for a in db.scalars(select(Attendance)).all() if a.booking.child_id in child_ids]
    active_prov |= {a.booking.activity.provider_id for a in atts if a.day >= cutoff.date()}

    # --- Actividad física ---
    cut28 = (t - timedelta(days=28)).date()
    present28 = [a for a in atts if a.present and a.day >= cut28]
    kids_with_booking = {b.child_id for b in confirmed}
    total_minutes = sum(a.booking.activity.session_minutes for a in present28)
    minutes_per_child = round(total_minutes / len(kids_with_booking)) if kids_with_booking else None

    # --- Ingresos ---
    gmv = sum(b.amount for b in confirmed)
    gmv28 = sum(b.amount for b in confirmed if b.created_at >= t - timedelta(days=28))
    monthly = [b for b in confirmed if b.kind == "mensual"]
    fam_monthly = {b.child.parent_id for b in monthly}
    arpu = round(sum(b.amount for b in monthly) / len(fam_monthly), 1) if fam_monthly else 0

    # --- Reservas por semana (últimas 6) ---
    weeks = []
    for i in range(5, -1, -1):
        start = (t - timedelta(days=7 * (i + 1)))
        end = (t - timedelta(days=7 * i))
        weeks.append((end.strftime("%d/%m"), sum(1 for b in bookings if start < b.created_at <= end)))

    return {
        "solo_reales": solo_reales,
        "has_demo": any(u.is_demo for u in users if u.role in ("parent", "provider")),
        "families": len(consented), "children": len(children),
        "funnel": funnel,
        "q_completion": _pct(len(q_done & q_start), len(q_start)),
        "median_minutes_first_booking": round(median(mins), 1) if mins else None,
        "bookings": len(bookings), "confirmed": len(confirmed),
        "repeat_rate": _pct(len(repeat), len(booked)),
        "trial_to_monthly": _pct(len(conv), len(trial_pairs)),
        "providers": len(providers), "providers_active": len(active_prov & {p.id for p in providers}),
        "provider_activity_rate": _pct(len(active_prov & {p.id for p in providers}), len(providers)),
        "minutes_per_child_28d": minutes_per_child,
        "attendance_rate": _pct(sum(a.present for a in atts), len(atts)),
        "gmv": gmv, "gmv28": gmv28, "comision": COMISION,
        "revenue": round(gmv * COMISION), "revenue28": round(gmv28 * COMISION),
        "arpu": arpu, "fam_monthly": len(fam_monthly),
        "weeks": weeks, "weeks_max": max([w[1] for w in weeks] + [1]),
    }


def as_csv_rows(m: dict) -> list[tuple[str, object]]:
    rows = [("familias_registradas", m["families"]), ("ninos", m["children"]),
            ("cuestionario_completado_pct", m["q_completion"]),
            ("minutos_mediana_hasta_primera_reserva", m["median_minutes_first_booking"]),
            ("reservas", m["bookings"]), ("reservas_confirmadas", m["confirmed"]),
            ("familias_que_repiten_pct", m["repeat_rate"]), ("prueba_a_mensual_pct", m["trial_to_monthly"]),
            ("proveedores", m["providers"]), ("proveedores_activos_14d", m["providers_active"]),
            ("minutos_actividad_por_nino_28d", m["minutes_per_child_28d"]),
            ("asistencia_pct", m["attendance_rate"]), ("gmv_pen", m["gmv"]),
            ("ingreso_plataforma_pen", m["revenue"]), ("datos", "solo reales" if m["solo_reales"] else "incluye demo")]
    rows += [(f"embudo_{i + 1}_{n}", v) for i, (n, v) in enumerate(m["funnel"])]
    return rows
