"""El catálogo debe alimentar al padre con opciones reales para cualquier edad y disponibilidad típica."""
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.catalog import CATEGORIES
from app.db import SessionLocal
from app.models import Activity, Provider
from app.recommender import more_options, ranked_all
from .test_flow import login

DISPONIBILIDADES = {
    "solo sábado": ["sab"], "fin de semana": ["sab", "dom"], "tardes de semana": ["lun", "mar", "mie", "jue", "vie"],
    "martes y jueves": ["mar", "jue"], "todos": ["lun", "mar", "mie", "jue", "vie", "sab", "dom"],
}


def kid(age, days, interests=(), zone="Cualquier zona", budget=150):
    return NS(age=age, days=days, interests=list(interests), slots=["manana", "tarde", "noche"], zone=zone, budget=budget)


def test_catalog_size_and_variety(client):
    with SessionLocal() as db:
        cats = {a.category for a in db.scalars(select(Activity))}
        assert len(db.scalars(select(Provider)).all()) >= 15
        assert len(cats) == len(CATEGORIES), f"Faltan actividades de: {set(CATEGORIES) - cats}"


@pytest.mark.parametrize("age", range(4, 18))
@pytest.mark.parametrize("name", ["solo sábado", "martes y jueves", "todos"])
def test_every_age_gets_at_least_three_options(client, age, name):
    with SessionLocal() as db:
        assert len(ranked_all(db, kid(age, DISPONIBILIDADES[name]))) >= 3


def test_variety_mode_and_more_options(client):
    with SessionLocal() as db:
        top, more = more_options(db, kid(8, DISPONIBILIDADES["todos"], interests=[]))
        assert len(top) == 3 and len(more) >= 3
        assert not {r.activity.id for r in top} & {r.activity.id for r in more}
        assert any("probar algo nuevo" in x.lower() for x in top[0].reasons)


def test_ui_more_options_explore_and_variety(fresh):
    c = fresh
    login(c, "988555666")
    c.post("/consentimiento", data={"nombre": "Eva Prueba", "acepto": "1"})
    c.post("/cuestionario/1", data={"nombre": "Noa", "edad": "7"})
    # "No sé" excluye el resto de gustos
    assert c.post("/cuestionario/2", data={"intereses": ["cualquiera", "futbol"]}).url.path == "/cuestionario/3"
    c.post("/cuestionario/3", data={"dias": ["sab", "mar", "jue"], "franjas": ["manana", "tarde"]})
    c.post("/cuestionario/4", data={"zona": "Cualquier zona"})
    r = c.post("/cuestionario/5", data={"presupuesto": "150"})
    assert "Mejor opción" in r.text and "opciones más" in r.text
    assert 'class="tabbar"' in r.text
    child_id = r.url.path.rsplit("/", 1)[1]
    r = c.get(f"/explorar?hijo={child_id}")
    assert r.status_code == 200 and "Explorar actividades" in r.text
    r = c.get(f"/explorar?hijo={child_id}&cat=natacion&dia=sab")
    assert "Natación" in r.text and "Fútbol" not in r.text.split("<main")[1].split("</main>")[0].split("actividad")[-1]
    assert c.get("/explorar?hijo=999999").status_code == 404
    # el cuestionario no muestra la barra inferior (menos distracciones)
    assert 'class="tabbar"' not in c.get("/cuestionario/1").text
