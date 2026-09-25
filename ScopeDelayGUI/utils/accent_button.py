"""Shared styling for the few buttons that start something physical.

Fire, Prep System and Capture All are the three an operator reaches for while
running a shot, and the default Windows button is close enough to white that
they disappear into the rest of the panel. Each gets its own hue, so they are
told apart by colour rather than by stopping to read labels.

The colours live here, not in the panels, so the three cannot drift apart.
"""

FIRE_RED = "#C62828"        # BNC575 Fire (INT) - the master shot, t0
PREP_BLUE = "#1565C0"       # Prep System - arms both lasers
CAPTURE_GREEN = "#2E7D32"   # Capture All - arms the scopes


def _shade(hex_color, factor):
    """Lighten (factor > 1) or darken (factor < 1) a #rrggbb colour."""
    h = hex_color.lstrip("#")
    rgb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    out = [max(0, min(255, int(round(c * factor)))) for c in rgb]
    return "#{:02X}{:02X}{:02X}".format(*out)


def accent_button(btn, color, tooltip=None):
    """Make `btn` a large, solid-coloured action button. Returns the button.

    The colour is set on the widget itself, which beats the application-wide
    rule in main.py, so these stay coloured whatever the global stylesheet says.
    """
    btn.setStyleSheet(
        "QPushButton {"
        f" background-color: {color};"
        " color: white;"
        " font-weight: bold;"
        " font-size: 12pt;"
        " padding: 10px 18px;"
        f" border: 2px solid {_shade(color, 0.8)};"
        " border-radius: 5px;"
        "}"
        f"QPushButton:hover {{ background-color: {_shade(color, 1.15)}; }}"
        f"QPushButton:pressed {{ background-color: {_shade(color, 0.8)}; }}"
        "QPushButton:disabled {"
        " background-color: #BDBDBD; color: #EEEEEE; border-color: #9E9E9E;"
        "}"
    )
    if tooltip:
        btn.setToolTip(tooltip)
    return btn
