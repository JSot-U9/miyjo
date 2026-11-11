import re

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, Notification, Otp, User


def otp_for(phone):
    with SessionLocal() as db:
        return db.scalars(select(Otp).where(Otp.phone == phone).order_by(Otp.id.desc())).first().code


def login(c, phone):
    r = c.post("/entrar", data={"celular": phone})
    assert r.url.path == "/codigo", r.text[:300]
    return c.post("/codigo", data={"codigo": otp_for(phone)})


def test_public_pages(fresh):
    assert fresh.get("/").status_code == 200
    assert fresh.get("/entrar").status_code == 200
    assert fresh.get("/manifest.webmanifest").status_code == 200
    assert fresh.get("/sw.js").headers["service-worker-allowed"] == "/"
    assert fresh.get("/no-existe").status_code == 404


def test_phone_validation_and_wrong_otp(fresh):
    r = fresh.post("/entrar", data={"celular": "12345"})
    assert r.status_code == 400 and "9 dígitos" in r.text
    fresh.post("/entrar", data={"celular": "977 000 111"})
    r = fresh.post("/codigo", data={"codigo": "000000" if otp_for("977000111") != "000000" else "111111"})
    assert r.status_code == 400 and "no es correcto" in r.text


def test_protected_routes_redirect(fresh):
    for path in ("/inicio", "/reservas", "/proveedor", "/metricas"):
        assert fresh.get(path).url.path == "/entrar"


def test_full_parent_to_provider_flow(fresh):
    c = fresh
    # --- Padre nuevo: OTP -> consentimiento
    r = login(c, "988111222")
    assert r.url.path == "/consentimiento"
    assert c.post("/consentimiento", data={"nombre": "Ana Prueba"}).status_code == 400  # sin casilla
    r = c.post("/consentimiento", data={"nombre": "Ana Prueba", "acepto": "1"})
    assert r.url.path == "/cuestionario/1"
    # --- Cuestionario con validaciones
    assert c.post("/cuestionario/1", data={"nombre": "Luca", "edad": "99"}).status_code == 400
    c.post("/cuestionario/1", data={"nombre": "Luca", "edad": "8"})
    assert c.post("/cuestionario/2", data={}).status_code == 400
    c.post("/cuestionario/2", data={"intereses": ["futbol", "natacion"]})
    c.post("/cuestionario/3", data={"dias": ["sab", "mar", "jue"], "franjas": ["manana", "tarde"]})
    c.post("/cuestionario/4", data={"zona": "San Sebastián"})
    r = c.post("/cuestionario/5", data={"presupuesto": "100"})
    assert r.url.path.startswith("/recomendaciones/")
    child_id = int(r.url.path.rsplit("/", 1)[1])
    assert "Verificado" in r.text and "Le gusta" in r.text and "Mejor opción" in r.text
    assert len(re.findall(r'class="card reco"', r.text)) <= 3
    # --- Reserva de prueba gratis -> confirmada
    act_id = int(re.search(r"/actividad/(\d+)\?hijo=", r.text).group(1))
    r = c.post("/reservar", data={"hijo": child_id, "actividad": act_id, "tipo": "prueba"})
    assert r.url.path == "/reservas" and "confirmada" in r.text
    # duplicado bloqueado
    r = c.post("/reservar", data={"hijo": child_id, "actividad": act_id, "tipo": "prueba"})
    assert "ya tiene una reserva" in r.text
    # --- Mensualidad -> pendiente de pago
    r = c.post("/reservar", data={"hijo": child_id, "actividad": act_id, "tipo": "mensual"})
    assert "yapea" in r.text.lower()
    with SessionLocal() as db:
        pend = db.scalars(select(Booking).where(Booking.child_id == child_id, Booking.kind == "mensual")).one()
        assert pend.status == "pendiente"
        prov_phone = pend.activity.provider.user.phone
        booking_id, act = pend.id, pend.activity
        days = act.days
    # --- Otro padre no puede ver/cancelar la reserva ni el hijo
    with fresh.__class__(fresh.app) as other:
        login(other, "988333444")
        assert other.get(f"/recomendaciones/{child_id}").status_code == 404
        assert other.post(f"/reservas/{booking_id}/cancelar").status_code == 404
    # --- Proveedor confirma el pago y marca asistencia
    with fresh.__class__(fresh.app) as p:
        r = login(p, prov_phone)
        assert r.url.path == "/proveedor" and "Confirmar pago" in r.text
        r = p.post(f"/proveedor/reservas/{booking_id}/confirmar")
        assert "confirmado" in r.text.lower()
        from datetime import date, timedelta
        d = date.today()
        from app.catalog import WEEKDAY_CODE
        while WEEKDAY_CODE[d.weekday()] not in days:
            d -= timedelta(days=1)
        r = p.post("/proveedor/asistencia", data={"actividad": act.id, "fecha": d.isoformat(), "presente": [booking_id]})
        assert "Asistencia" in r.text
        r = p.get("/metricas")  # un proveedor no ve métricas: vuelve a su panel
        assert r.url.path == "/proveedor" and "Panel para patrocinadores" not in r.text
    with SessionLocal() as db:
        msgs = [n.body for n in db.scalars(select(Notification).where(Notification.phone == "988111222"))]
        assert any("pago recibido" in m for m in msgs) and any("asistió" in m for m in msgs)
    # --- Padre ve asistencia
    r = c.get("/reservas")
    assert "Asistió a 1 de 1" in r.text


def test_admin_metrics_and_csv(fresh):
    r = fresh.post("/demo/entrar/admin")
    assert r.url.path == "/metricas" and "Panel para patrocinadores" in r.text
    assert "datos de demostración" in r.text
    r = fresh.get("/metricas?reales=1")
    assert "solo datos reales" in r.text
    csv = fresh.get("/metricas.csv").text
    assert csv.startswith("metrica,valor") and "familias_registradas" in csv
