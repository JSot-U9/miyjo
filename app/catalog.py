"""Constantes del dominio: días, zonas de Cusco, categorías deportivas y presupuestos."""

DAYS = [("lun", "Lun"), ("mar", "Mar"), ("mie", "Mié"), ("jue", "Jue"),
        ("vie", "Vie"), ("sab", "Sáb"), ("dom", "Dom")]
DAY_LABEL = dict(DAYS)
DAY_FULL = {"lun": "lunes", "mar": "martes", "mie": "miércoles", "jue": "jueves",
            "vie": "viernes", "sab": "sábado", "dom": "domingo"}
WEEKDAY_CODE = [d for d, _ in DAYS]  # date.weekday(): lunes = 0

SLOTS = {
    "manana": ("Mañana", "antes de las 12:00"),
    "tarde": ("Tarde", "de 12:00 a 18:00"),
    "noche": ("Noche", "después de las 18:00"),
}

ZONES = ["Cusco Centro", "Wanchaq", "San Sebastián", "San Jerónimo", "Santiago"]
ZONE_ANY = "Cualquier zona"
_ADJ = [("Cusco Centro", "Wanchaq"), ("Cusco Centro", "Santiago"), ("Cusco Centro", "San Sebastián"),
        ("Wanchaq", "San Sebastián"), ("San Sebastián", "San Jerónimo"), ("Wanchaq", "Santiago")]
ADJACENT = {z: set() for z in ZONES}
for a, b in _ADJ:
    ADJACENT[a].add(b)
    ADJACENT[b].add(a)

CATEGORIES = {
    "futbol": {"label": "Fútbol", "emoji": "⚽", "group": "equipo"},
    "basquet": {"label": "Básquet", "emoji": "🏀", "group": "equipo"},
    "voley": {"label": "Vóley", "emoji": "🏐", "group": "equipo"},
    "natacion": {"label": "Natación", "emoji": "🏊", "group": "agua"},
    "karate": {"label": "Karate", "emoji": "🥋", "group": "combate"},
    "taekwondo": {"label": "Taekwondo", "emoji": "🦵", "group": "combate"},
    "judo": {"label": "Judo", "emoji": "🤼", "group": "combate"},
    "danza": {"label": "Danza", "emoji": "💃", "group": "artistico"},
    "ballet": {"label": "Ballet", "emoji": "🩰", "group": "artistico"},
    "gimnasia": {"label": "Gimnasia", "emoji": "🤸", "group": "artistico"},
    "tenis": {"label": "Tenis", "emoji": "🎾", "group": "raqueta"},
    "tenis_mesa": {"label": "Tenis de mesa", "emoji": "🏓", "group": "raqueta"},
    "skate": {"label": "Skate", "emoji": "🛹", "group": "ruedas"},
    "patinaje": {"label": "Patinaje", "emoji": "🛼", "group": "ruedas"},
    "ciclismo": {"label": "Ciclismo", "emoji": "🚴", "group": "ruedas"},
    "atletismo": {"label": "Atletismo", "emoji": "🏃", "group": "libre"},
    "escalada": {"label": "Escalada", "emoji": "🧗", "group": "libre"},
    "yoga": {"label": "Yoga", "emoji": "🧘", "group": "libre"},
    "multideporte": {"label": "Multideporte", "emoji": "🎯", "group": "libre"},
}

# Orden y títulos con los que se muestran las actividades al elegir gustos
GROUP_TITLES = {
    "equipo": "Deportes de equipo", "agua": "Agua", "combate": "Artes marciales",
    "artistico": "Baile y gimnasia", "raqueta": "Raqueta", "ruedas": "Sobre ruedas",
    "libre": "Aire libre y bienestar",
}
CATEGORY_GROUPS = [(g, t, [(k, c) for k, c in CATEGORIES.items() if c["group"] == g])
                   for g, t in GROUP_TITLES.items()]
ANY_INTEREST = "cualquiera"  # "No sé, muéstrame variedad"

BUDGETS = [(60, "Hasta S/ 60 al mes"), (100, "Hasta S/ 100 al mes"), (150, "Hasta S/ 150 al mes"),
           (200, "Hasta S/ 200 al mes"), (300, "Más de S/ 200 al mes")]

AGES = list(range(3, 18))


def slot_of(hhmm: str) -> str:
    h = int(hhmm.split(":")[0])
    return "manana" if h < 12 else "tarde" if h < 18 else "noche"


def minutes_between(start: str, end: str) -> int:
    (h1, m1), (h2, m2) = (map(int, start.split(":")), map(int, end.split(":")))
    return (h2 * 60 + m2) - (h1 * 60 + m1)
