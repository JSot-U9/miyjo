"""Verifica el contraste (WCAG 2.1) de la paleta definida en app.css."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "app/static/css/app.css").read_text(encoding="utf-8")
VARS = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", CSS.split("}")[0]))


def lum(hex_):
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(VARS[a]), lum(VARS[b])), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (texto, fondo, mínimo). 7:1 = AAA para texto normal; 4.5:1 = AA; 3:1 = componentes de interfaz.
TEXT = [("ink", "bg", 7), ("ink", "card", 7), ("muted", "card", 7), ("muted", "bg", 7),
        ("brand", "card", 7), ("brand", "bg", 7), ("brand-ink", "brand", 7), ("brand-ink", "brand-hover", 7),
        ("accent-ink", "accent", 7), ("ok", "ok-soft", 7), ("warn", "warn-soft", 7), ("err", "err-soft", 7),
        ("brand", "brand-soft", 7), ("ink", "brand-soft", 7), ("err", "card", 7), ("wa", "card", 7),
        ("brand-ink", "wa", 7), ("ok", "card", 7)]
UI = [("line-strong", "card", 3), ("line-strong", "bg", 3), ("brand", "card", 3), ("focus", "card", 3), ("focus", "bg", 3)]


def test_text_contrast_is_aaa():
    bad = [(a, b, round(ratio(a, b), 2)) for a, b, m in TEXT if ratio(a, b) < m]
    assert not bad, f"Contraste insuficiente (mínimo 7:1): {bad}"


def test_ui_component_contrast():
    bad = [(a, b, round(ratio(a, b), 2)) for a, b, m in UI if ratio(a, b) < m]
    assert not bad, f"Contraste insuficiente en controles (mínimo 3:1): {bad}"
