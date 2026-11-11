"""Reglas de negocio compartidas: OTP, notificaciones, eventos, reservas y fechas."""
import random
import re
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import DAY_FULL, WEEKDAY_CODE
from .config import DEMO, now
from .models import Activity, Attendance, Booking, Child, Event, Notification, Otp, User

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_MAX_PER_15MIN = 5


class ServiceError(Exception):
    """Error de negocio con mensaje apto para mostrar al padre."""


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("51"):
        digits = digits[2:]
    if not re.fullmatch(r"9\d{8}", digits):
        raise ServiceError("Escribe tu celular de 9 dígitos, por ejemplo 987 654 321.")
    return digits


def log(db: Session, type_: str, user_id: int | None = None, data: str = "", ts: datetime | None = None) -> None:
    db.add(Event(type=type_, user_id=user_id, data=data[:200], ts=ts or now()))


def notify(db: Session, phone: str, body: str, ts: datetime | None = None) -> None:
    """Punto único de salida de mensajes. Hoy: bandeja interna (/demo/mensajes).
    Para el piloto real, enviar aquí por la API de WhatsApp Business o por SMS."""
    db.add(Notification(phone=phone, body=body, created_at=ts or now()))


# ---------- OTP ----------
def issue_otp(db: Session, phone: str) -> str:
    recent = db.scalar(select(func.count()).select_from(Otp).where(
        Otp.phone == phone, Otp.created_at > now() - timedelta(minutes=15)))
    if recent >= OTP_MAX_PER_15MIN:
        raise ServiceError("Pediste muchos códigos. Espera unos minutos e inténtalo de nuevo.")
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(Otp(phone=phone, code=code))
    notify(db, phone, f"MIYJO: tu código de ingreso es {code}. Vence en 5 minutos. No lo compartas.")
    db.commit()
    return code


def check_otp(db: Session, phone: str, code: str) -> bool:
    otp = db.scalars(select(Otp).where(Otp.phone == phone, Otp.used.is_(False))
                     .order_by(Otp.id.desc())).first()
    if not otp or now() - otp.created_at > OTP_TTL or otp.attempts >= OTP_MAX_ATTEMPTS:
        return False
    otp.attempts += 1
    ok = secrets.compare_digest(otp.code, (code or "").strip())
    if ok:
        otp.used = True
    db.commit()
    return ok


# ---------- Fechas ----------
def next_session(act: Activity, frm: date | None = None) -> tuple[date, str] | None:
    """Próxima fecha de clase (hoy cuenta). Devuelve (fecha, 'sábado 8 de noviembre')."""
    frm = frm or now().date()
    for i in range(7):
        d = frm + timedelta(days=i)
        if WEEKDAY_CODE[d.weekday()] in act.days:
            return d, f"{DAY_FULL[WEEKDAY_CODE[d.weekday()]]} {d.day}"
    return None


def fmt_date(d: date) -> str:
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{DAY_FULL[WEEKDAY_CODE[d.weekday()]]} {d.day} de {meses[d.month - 1]}"


# ---------- Reservas ----------
def spots_left(db: Session, act: Activity) -> int:
    taken = db.scalar(select(func.count()).select_from(Booking)
                      .where(Booking.activity_id == act.id, Booking.status != "cancelada"))
    return act.capacity - taken


def create_booking(db: Session, child: Child, act: Activity, kind: str) -> Booking:
    if kind not in ("prueba", "mensual"):
        raise ServiceError("Tipo de reserva no válido.")
    if not (act.min_age <= child.age <= act.max_age):
        raise ServiceError(f"Esta actividad es para niños de {act.min_age} a {act.max_age} años.")
    existing = db.scalars(select(Booking).where(
        Booking.child_id == child.id, Booking.activity_id == act.id, Booking.status != "cancelada")).all()
    if any(b.kind == "mensual" for b in existing) or (kind == "prueba" and existing):
        raise ServiceError(f"{child.name} ya tiene una reserva en esta actividad.")
    if spots_left(db, act) <= 0:
        raise ServiceError("Ya no quedan cupos en esta actividad.")

    amount = act.trial_price if kind == "prueba" else act.price_month
    booking = Booking(child=child, activity=act, kind=kind, amount=amount,
                      status="confirmada" if amount == 0 else "pendiente")
    db.add(booking)
    db.flush()
    parent, provider = child.parent, act.provider
    log(db, "booking", parent.id, f"{booking.id}:{kind}")
    if booking.status == "confirmada":
        log(db, "booking_confirmed", parent.id, str(booking.id))
        notify(db, parent.phone, f"MIYJO: ¡reserva confirmada! {child.name} entra a {act.name}. "
                                 f"Detalle en la app, sección Mis reservas.")
    else:
        notify(db, parent.phone, f"MIYJO: reservamos el cupo de {child.name} en {act.name}. Para confirmarlo, "
                                 f"yapea S/ {amount} al {provider.yape or provider.user.phone} ({provider.name}).")
    notify(db, provider.user.phone, f"MIYJO: nueva reserva de {child.name} ({child.age} años) en {act.name} "
                                    f"({'clase de prueba' if kind == 'prueba' else 'mensualidad'}).")
    db.commit()
    return booking


def confirm_booking(db: Session, booking: Booking) -> None:
    if booking.status != "pendiente":
        return
    booking.status = "confirmada"
    log(db, "booking_confirmed", booking.child.parent_id, str(booking.id))
    notify(db, booking.child.parent.phone,
           f"MIYJO: ¡pago recibido! {booking.child.name} ya tiene su cupo en {booking.activity.name}.")
    db.commit()


def cancel_booking(db: Session, booking: Booking) -> None:
    if booking.status == "cancelada":
        return
    booking.status = "cancelada"
    log(db, "booking_cancelled", booking.child.parent_id, str(booking.id))
    notify(db, booking.activity.provider.user.phone,
           f"MIYJO: {booking.child.name} canceló su cupo en {booking.activity.name}.")
    db.commit()


def save_attendance(db: Session, act: Activity, day: date, present_ids: set[int]) -> int:
    """Guarda la asistencia de una clase. Avisa al padre solo cuando el niño pasa a 'presente'."""
    bookings = db.scalars(select(Booking).where(
        Booking.activity_id == act.id, Booking.status == "confirmada")).all()
    changed = 0
    for b in bookings:
        present = b.id in present_ids
        rec = db.scalar(select(Attendance).where(Attendance.booking_id == b.id, Attendance.day == day))
        if rec is None:
            db.add(Attendance(booking_id=b.id, day=day, present=present))
        elif rec.present == present:
            continue
        else:
            rec.present = present
        changed += 1
        if present:
            log(db, "attendance", b.child.parent_id, str(b.id))
            notify(db, b.child.parent.phone, f"MIYJO: {b.child.name} asistió hoy a {act.name}. ¡Buen trabajo!")
        else:
            notify(db, b.child.parent.phone,
                   f"MIYJO: hoy no registramos la asistencia de {b.child.name} a {act.name}.")
    db.commit()
    return changed


def attendance_summary(b: Booking) -> tuple[int, int]:
    total = len(b.attendances)
    return sum(1 for a in b.attendances if a.present), total


def random_phone(rng: random.Random | None = None) -> str:
    r = rng or random
    return "9" + "".join(str(r.randrange(10)) for _ in range(8))
