import csv
import io
import re
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import metrics as metrics_mod
from . import services as svc
from .catalog import (AGES, ANY_INTEREST, BUDGETS, CATEGORIES, CATEGORY_GROUPS, DAY_LABEL, DAYS, SLOTS, WEEKDAY_CODE,
                      ZONE_ANY, ZONES)
from .config import BASE_DIR, DEMO, SECRET_KEY, SOPORTE_WHATSAPP, now
from .db import Base, SessionLocal, engine, get_db
from .models import Activity, Booking, Child, Notification, Provider, User
from .recommender import more_options, ranked_all
from .seed import ADMIN_PHONE, DEMO_FAMILY_PHONE, ensure_seed

TOTAL_STEPS = 5


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_seed(db)
    yield


app = FastAPI(title="MIYJO", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 30, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
templates.env.globals.update(
    CATEGORIES=CATEGORIES, CATEGORY_GROUPS=CATEGORY_GROUPS, ANY_INTEREST=ANY_INTEREST, DAYS=DAYS, SLOTS=SLOTS, ZONES=ZONES, ZONE_ANY=ZONE_ANY, BUDGETS=BUDGETS, AGES=AGES,
    DAY_LABEL=DAY_LABEL, DEMO=DEMO, SOPORTE=SOPORTE_WHATSAPP, TOTAL_STEPS=TOTAL_STEPS,
    fmt_date=svc.fmt_date, next_session=svc.next_session, att_summary=svc.attendance_summary)
templates.env.filters["days"] = lambda ds: " · ".join(DAY_LABEL[d] for d in ds)


# ---------------------------------------------------------------- utilidades
def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx["flash"] = request.session.pop("flash", [])
    ctx.setdefault("user", ctx.pop("_user", None))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def flash(request: Request, msg: str, kind: str = "ok") -> None:
    request.session["flash"] = request.session.get("flash", []) + [{"kind": kind, "msg": msg}]


def go(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _redirect(url: str):
    return HTTPException(status_code=303, headers={"Location": url})


def get_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None


def need(role: str):
    def dep(user: User | None = Depends(get_user)) -> User:
        if user is None:
            raise _redirect("/entrar")
        if user.role != role:
            raise _redirect("/")
        return user
    return dep


need_parent, need_provider, need_admin = need("parent"), need("provider"), need("admin")


def home_for(user: User) -> str:
    return {"parent": "/inicio", "provider": "/proveedor", "admin": "/metricas"}[user.role]


def own_child(db: Session, user: User, child_id: int) -> Child:
    child = db.get(Child, child_id)
    if not child or child.parent_id != user.id:
        raise HTTPException(404)
    return child


def parent_gate(user: User) -> str | None:
    """Siguiente paso obligatorio para el padre, o None si ya puede usar la app."""
    if not user.consent_at:
        return "/consentimiento"
    if not user.children:
        return "/cuestionario/1"
    return None


@app.exception_handler(404)
async def not_found(request: Request, _):
    return render(request, "error.html", 404, title="No encontramos esa página",
                  msg="Puede que el enlace haya cambiado. Vuelve al inicio e inténtalo de nuevo.")


# ---------------------------------------------------------------- PWA
@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(BASE_DIR / "app/static/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(BASE_DIR / "app/static/sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


# ---------------------------------------------------------------- acceso
@app.get("/", response_class=HTMLResponse)
def landing(request: Request, user: User | None = Depends(get_user)):
    if user:
        return go(home_for(user))
    return render(request, "landing.html")


@app.get("/entrar", response_class=HTMLResponse)
def login_form(request: Request, rol: str = "parent"):
    return render(request, "login.html", rol=rol, error=None, phone="")


@app.post("/entrar")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    raw = str(form.get("celular", ""))
    try:
        phone = svc.normalize_phone(raw)
        code = svc.issue_otp(db, phone)
    except svc.ServiceError as e:
        return render(request, "login.html", 400, rol=form.get("rol", "parent"), error=str(e), phone=raw)
    request.session["pending_phone"] = phone
    request.session["demo_code"] = code if DEMO else None
    return go("/codigo")


@app.get("/codigo", response_class=HTMLResponse)
def code_form(request: Request):
    phone = request.session.get("pending_phone")
    if not phone:
        return go("/entrar")
    return render(request, "code.html", phone=phone, error=None, demo_code=request.session.get("demo_code"))


@app.post("/codigo")
async def code_submit(request: Request, db: Session = Depends(get_db)):
    phone = request.session.get("pending_phone")
    if not phone:
        return go("/entrar")
    form = await request.form()
    if not svc.check_otp(db, phone, str(form.get("codigo", ""))):
        return render(request, "code.html", 400, phone=phone, demo_code=request.session.get("demo_code"),
                      error="Ese código no es correcto o ya venció. Revisa tu WhatsApp o pide uno nuevo.")
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, role="parent")
        db.add(user)
        db.flush()
        svc.log(db, "signup", user.id)
        db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    if user.role == "parent":
        return go(parent_gate(user) or "/inicio")
    return go(home_for(user))


@app.post("/salir")
def logout(request: Request):
    request.session.clear()
    return go("/")


# ---------------------------------------------------------------- consentimiento
@app.get("/consentimiento", response_class=HTMLResponse)
def consent_form(request: Request, user: User = Depends(need_parent)):
    return render(request, "consent.html", _user=user, error=None)


@app.post("/consentimiento")
async def consent_submit(request: Request, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    form = await request.form()
    name = re.sub(r"[^\w\s'.-]", "", str(form.get("nombre", ""))).strip()[:60]
    if len(name) < 2 or not form.get("acepto"):
        return render(request, "consent.html", 400, _user=user,
                      error="Escribe tu nombre y marca la casilla para continuar.")
    user.name, user.consent_at = name, now()
    svc.log(db, "consent", user.id)
    db.commit()
    return go("/cuestionario/1")


# ---------------------------------------------------------------- cuestionario (5 pasos)
def _validate_step(step: int, form) -> tuple[dict, str | None]:
    if step == 1:
        name = re.sub(r"[^\w\s'-]", "", str(form.get("nombre", ""))).strip()[:40]
        age = str(form.get("edad", ""))
        if not name:
            return {}, "Escribe el nombre de tu hijo o hija."
        if not age.isdigit() or int(age) not in AGES:
            return {}, "Elige la edad de tu hijo o hija."
        return {"nombre": name, "edad": int(age)}, None
    if step == 2:
        raw = form.getlist("intereses")
        if ANY_INTEREST in raw:
            return {"intereses": []}, None
        picks = [c for c in raw if c in CATEGORIES]
        if not 1 <= len(picks) <= 3:
            return {}, "Elige de 1 a 3 actividades que le gusten, o marca «No sé, muéstrame variedad»."
        return {"intereses": picks}, None
    if step == 3:
        days = [d for d in form.getlist("dias") if d in DAY_LABEL]
        slots = [s for s in form.getlist("franjas") if s in SLOTS]
        if not days or not slots:
            return {}, "Elige al menos un día y una franja de horario."
        return {"dias": days, "franjas": slots}, None
    if step == 4:
        zone = str(form.get("zona", ""))
        if zone not in ZONES + [ZONE_ANY]:
            return {}, "Elige la zona donde prefieres la actividad."
        return {"zona": zone}, None
    budget = str(form.get("presupuesto", ""))
    if not budget.isdigit() or int(budget) not in {b for b, _ in BUDGETS}:
        return {}, "Elige cuánto te gustaría invertir al mes."
    return {"presupuesto": int(budget)}, None


@app.get("/cuestionario/{step}", response_class=HTMLResponse)
def q_get(request: Request, step: int, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    if not user.consent_at:
        return go("/consentimiento")
    if not 1 <= step <= TOTAL_STEPS:
        raise HTTPException(404)
    q = request.session.setdefault("q", {})
    if step > 1 and "nombre" not in q:
        return go("/cuestionario/1")
    if step == 2 and not q.get("intereses") and q.get("_step2_done"):
        q = {**q, "_any": True}
    if step == 1 and not q.get("_started"):
        q["_started"] = True
        request.session["q"] = q
        svc.log(db, "q_start", user.id)
        db.commit()
    return render(request, "q_step.html", _user=user, step=step, q=q, error=None)


@app.post("/cuestionario/{step}")
async def q_post(request: Request, step: int, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    if not 1 <= step <= TOTAL_STEPS:
        raise HTTPException(404)
    q = dict(request.session.get("q", {}))
    form = await request.form()
    data, error = _validate_step(step, form)
    if error:
        return render(request, "q_step.html", 400, _user=user, step=step, q=q, error=error)
    q.update(data)
    if step == 2:
        q["_step2_done"] = True
    request.session["q"] = q
    if step < TOTAL_STEPS:
        return go(f"/cuestionario/{step + 1}")
    child = Child(parent=user, name=q["nombre"], age=q["edad"], interests_csv=",".join(q.get("intereses", [])),
                  days_csv=",".join(q["dias"]), slots_csv=",".join(q["franjas"]), zone=q["zona"],
                  budget=q["presupuesto"])
    db.add(child)
    svc.log(db, "q_done", user.id)
    db.commit()
    request.session.pop("q", None)
    return go(f"/recomendaciones/{child.id}")


# ---------------------------------------------------------------- padre
@app.get("/inicio", response_class=HTMLResponse)
def parent_home(request: Request, user: User = Depends(need_parent)):
    if gate := parent_gate(user):
        return go(gate)
    return render(request, "home.html", _user=user)


@app.get("/recomendaciones/{child_id}", response_class=HTMLResponse)
def recos(request: Request, child_id: int, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    child = own_child(db, user, child_id)
    results, more = more_options(db, child)
    if results:
        svc.log(db, "reco_view", user.id, str(child.id))
        db.commit()
    return render(request, "recos.html", _user=user, child=child, results=results, more=more)


@app.get("/explorar", response_class=HTMLResponse)
def explore(request: Request, hijo: int | None = None, cat: str = "", zona: str = "", dia: str = "",
            user: User = Depends(need_parent), db: Session = Depends(get_db)):
    """Catálogo completo con filtros simples, para quien quiere ver todas las opciones."""
    if gate := parent_gate(user):
        return go(gate)
    child = own_child(db, user, hijo) if hijo else user.children[0]
    fit = {r.activity.id: r for r in ranked_all(db, child)}
    acts = db.scalars(select(Activity).where(Activity.active.is_(True))).all()
    rows = []
    for a in acts:
        if not (a.min_age <= child.age <= a.max_age):
            continue
        if (cat and a.category != cat) or (zona and a.provider.zone != zona) or (dia and dia not in a.days):
            continue
        left = svc.spots_left(db, a)
        if left > 0:
            rows.append({"act": a, "left": left, "fit": fit.get(a.id)})
    rows.sort(key=lambda r: (-(r["fit"].score if r["fit"] else -1), r["act"].price_month, r["act"].id))
    return render(request, "explore.html", _user=user, child=child, rows=rows, f={"cat": cat, "zona": zona, "dia": dia})


@app.get("/actividad/{act_id}", response_class=HTMLResponse)
def activity_detail(request: Request, act_id: int, hijo: int, user: User = Depends(need_parent),
                    db: Session = Depends(get_db)):
    act, child = db.get(Activity, act_id), own_child(db, user, hijo)
    if not act or not act.active:
        raise HTTPException(404)
    existing = [b for b in child.bookings if b.activity_id == act.id and b.status != "cancelada"]
    return render(request, "activity.html", _user=user, act=act, child=child, left=svc.spots_left(db, act),
                  has_monthly=any(b.kind == "mensual" for b in existing), has_any=bool(existing))


@app.post("/reservar")
async def book(request: Request, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    form = await request.form()
    try:
        child = own_child(db, user, int(form.get("hijo", 0)))
        act = db.get(Activity, int(form.get("actividad", 0)))
    except ValueError:
        raise HTTPException(400)
    if not act:
        raise HTTPException(404)
    try:
        b = svc.create_booking(db, child, act, str(form.get("tipo", "")))
    except svc.ServiceError as e:
        flash(request, str(e), "error")
        return go(f"/actividad/{act.id}?hijo={child.id}")
    return go(f"/reservas?nueva={b.id}")


@app.get("/reservas", response_class=HTMLResponse)
def my_bookings(request: Request, nueva: int | None = None, user: User = Depends(need_parent)):
    if gate := parent_gate(user):
        return go(gate)
    return render(request, "bookings.html", _user=user, nueva=nueva)


@app.post("/reservas/{booking_id}/cancelar")
def cancel(request: Request, booking_id: int, user: User = Depends(need_parent), db: Session = Depends(get_db)):
    b = db.get(Booking, booking_id)
    if not b or b.child.parent_id != user.id:
        raise HTTPException(404)
    svc.cancel_booking(db, b)
    flash(request, "Reserva cancelada.")
    return go("/reservas")


# ---------------------------------------------------------------- proveedor
def _provider(user: User) -> Provider:
    if not user.provider:
        raise HTTPException(404)
    return user.provider


@app.get("/proveedor", response_class=HTMLResponse)
def provider_panel(request: Request, fecha: str | None = None, user: User = Depends(need_provider),
                   db: Session = Depends(get_db)):
    prov = _provider(user)
    try:
        day = date.fromisoformat(fecha) if fecha else now().date()
    except ValueError:
        day = now().date()
    code = WEEKDAY_CODE[day.weekday()]
    rows = []
    for a in prov.activities:
        active = [b for b in a.bookings if b.status != "cancelada"]
        rows.append({"act": a, "taken": len(active), "pending": [b for b in active if b.status == "pendiente"]})
    sessions = []
    for a in prov.activities:
        if code in a.days:
            confirmed = [b for b in a.bookings if b.status == "confirmada"]
            marks = {at.booking_id: at.present for b in confirmed for at in b.attendances if at.day == day}
            sessions.append({"act": a, "students": confirmed, "marks": marks})
    return render(request, "provider.html", _user=user, prov=prov, rows=rows, sessions=sessions, day=day,
                  pending=[b for r in rows for b in r["pending"]],
                  active_students=sum(1 for r in rows for b in r["act"].bookings if b.status == "confirmada"))


@app.post("/proveedor/reservas/{booking_id}/confirmar")
def provider_confirm(request: Request, booking_id: int, user: User = Depends(need_provider),
                     db: Session = Depends(get_db)):
    b = db.get(Booking, booking_id)
    if not b or b.activity.provider_id != _provider(user).id:
        raise HTTPException(404)
    svc.confirm_booking(db, b)
    flash(request, f"Pago de {b.child.name} confirmado. Avisamos a la familia.")
    return go("/proveedor")


@app.post("/proveedor/asistencia")
async def provider_attendance(request: Request, user: User = Depends(need_provider), db: Session = Depends(get_db)):
    form = await request.form()
    try:
        act = db.get(Activity, int(form.get("actividad", 0)))
        day = date.fromisoformat(str(form.get("fecha", "")))
        present = {int(x) for x in form.getlist("presente")}
    except ValueError:
        raise HTTPException(400)
    if not act or act.provider_id != _provider(user).id:
        raise HTTPException(404)
    svc.save_attendance(db, act, day, present)
    flash(request, f"Asistencia de {act.name} guardada. Las familias reciben su aviso.")
    return go(f"/proveedor?fecha={day.isoformat()}")


@app.get("/proveedor/actividades/nueva", response_class=HTMLResponse)
def new_activity_form(request: Request, user: User = Depends(need_provider)):
    return render(request, "provider_new.html", _user=user, error=None, f={})


@app.post("/proveedor/actividades/nueva")
async def new_activity(request: Request, user: User = Depends(need_provider), db: Session = Depends(get_db)):
    prov, form = _provider(user), await request.form()
    f = {k: str(form.get(k, "")).strip() for k in
         ("nombre", "categoria", "edad_min", "edad_max", "inicio", "fin", "precio", "prueba", "cupos", "nivel", "seguridad")}
    days = [d for d in form.getlist("dias") if d in DAY_LABEL]
    hhmm = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
    try:
        amin, amax, price, trial, cap = (int(f[k]) for k in ("edad_min", "edad_max", "precio", "prueba", "cupos"))
        assert f["nombre"] and f["categoria"] in CATEGORIES and days
        assert hhmm.fullmatch(f["inicio"]) and hhmm.fullmatch(f["fin"]) and f["fin"] > f["inicio"]
        assert 3 <= amin <= amax <= 17 and price >= 0 and trial >= 0 and 1 <= cap <= 100
    except (ValueError, AssertionError):
        return render(request, "provider_new.html", 400, _user=user, f=f,
                      error="Revisa los datos: nombre, días, horas (inicio antes que fin), edades y precios.")
    db.add(Activity(provider_id=prov.id, name=f["nombre"][:80], category=f["categoria"], min_age=amin,
                    max_age=amax, days_csv=",".join(d for d, _ in DAYS if d in days), start=f["inicio"],
                    end=f["fin"], price_month=price, trial_price=trial, capacity=cap,
                    level=f["nivel"][:30] or "Todos los niveles", safety=f["seguridad"][:300]))
    db.commit()
    flash(request, "Actividad creada. Ya puede recomendarse a las familias.")
    return go("/proveedor")


# ---------------------------------------------------------------- métricas (patrocinadores)
@app.get("/metricas", response_class=HTMLResponse)
def metrics_page(request: Request, reales: int = 0, user: User = Depends(need_admin), db: Session = Depends(get_db)):
    return render(request, "metrics.html", _user=user, m=metrics_mod.compute(db, bool(reales)))


@app.get("/metricas.csv", include_in_schema=False)
def metrics_csv(reales: int = 0, user: User = Depends(need_admin), db: Session = Depends(get_db)):
    buf = io.StringIO()
    csv.writer(buf).writerows([("metrica", "valor"), *metrics_mod.as_csv_rows(metrics_mod.compute(db, bool(reales)))])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=miyjo_metricas.csv"})


# ---------------------------------------------------------------- demo
def _demo_only():
    if not DEMO:
        raise HTTPException(404)


@app.get("/demo", response_class=HTMLResponse)
def demo_page(request: Request, user: User | None = Depends(get_user)):
    _demo_only()
    return render(request, "demo.html", _user=user)


@app.post("/demo/entrar/{who}")
def demo_login(request: Request, who: str, db: Session = Depends(get_db)):
    _demo_only()
    if who == "nueva":
        user = User(phone=svc.random_phone(), role="parent", is_demo=True)
        db.add(user)
        db.flush()
        svc.log(db, "signup", user.id)
        db.commit()
    else:
        user = {
            "familia": lambda: db.scalar(select(User).where(User.phone == DEMO_FAMILY_PHONE)),
            "proveedor": lambda: db.scalar(select(User).where(User.role == "provider").order_by(User.id)),
            "admin": lambda: db.scalar(select(User).where(User.phone == ADMIN_PHONE)),
        }.get(who, lambda: None)()
    if not user:
        raise HTTPException(404)
    request.session.clear()
    request.session["uid"] = user.id
    return go(parent_gate(user) or home_for(user) if user.role == "parent" else home_for(user))


@app.get("/demo/mensajes", response_class=HTMLResponse)
def demo_outbox(request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_user)):
    _demo_only()
    msgs = db.scalars(select(Notification).order_by(Notification.id.desc()).limit(40)).all()
    return render(request, "outbox.html", _user=user, msgs=msgs)
