"""Checks on easyadmin's stylesheets: the light and dark palettes.

Each page has two palettes of custom properties. These tests keep them honest:
both define the same names, every colour in the rules comes from a palette,
and the text colours stay readable on their backgrounds in both modes.
"""

import os
import re

import pytest

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "apps", "easyadmin", "appserver", "static")

COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")

# (text, background, minimum ratio). 4.5 is WCAG AA for normal-size text;
# 3.0 for the change outline and the small count badge's shape against the tab.
CONTRAST_PAIRS = [
    ("--ea-fg", "--ea-bg", 4.5),
    ("--ea-fg", "--ea-head", 4.5),
    ("--ea-fg", "--ea-hover", 4.5),
    ("--ea-fg", "--ea-effective", 4.5),
    ("--ea-fg", "--ea-effective-hover", 4.5),
    ("--ea-fg", "--ea-info-bg", 4.5),
    ("--ea-fg", "--ea-error-bg", 4.5),
    ("--ea-fg", "--ea-success-bg", 4.5),
    ("--ea-muted", "--ea-bg", 4.5),
    ("--ea-muted", "--ea-head", 4.5),
    ("--ea-badge-fg", "--ea-badge-bg", 4.5),
    ("--ea-count-fg", "--ea-count-bg", 4.5),
    ("--ea-input-fg", "--ea-input-bg", 4.5),
    ("--ea-changed", "--ea-bg", 3.0),
]

APPS_CONTRAST_PAIRS = [
    ("--ea-fg", "--ea-bg", 4.5),
    ("--ea-fg", "--ea-head", 4.5),
    ("--ea-fg", "--ea-hover", 4.5),
    ("--ea-fg", "--ea-changed-bg", 4.5),
    ("--ea-fg", "--ea-drop-bg", 4.5),
    ("--ea-fg", "--ea-info-bg", 4.5),
    ("--ea-fg", "--ea-error-bg", 4.5),
    ("--ea-fg", "--ea-success-bg", 4.5),
    ("--ea-muted", "--ea-bg", 4.5),
    ("--ea-muted", "--ea-head", 4.5),
    ("--ea-badge-fg", "--ea-badge-bg", 4.5),
    ("--ea-input-fg", "--ea-input-bg", 4.5),
    ("--ea-danger", "--ea-head", 4.5),
    ("--ea-danger", "--ea-bg", 4.5),
    # Outlines and focus rings: 3:1 against what they sit on (WCAG 1.4.11).
    ("--ea-changed", "--ea-changed-bg", 3.0),
    ("--ea-drop", "--ea-drop-bg", 3.0),
    ("--ea-focus", "--ea-bg", 3.0),
    ("--ea-focus", "--ea-head", 3.0),
]

# (stylesheet, light palette selector, contrast pairs) for each page.
SHEETS = [
    ("easyadmin_roles.css", "#easyadmin-roles", CONTRAST_PAIRS),
    ("easyadmin_apps.css", "#easyadmin-apps", APPS_CONTRAST_PAIRS),
]
SHEET_IDS = [sheet[0] for sheet in SHEETS]


def _strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _text(css):
    return _strip_comments(open(os.path.join(STATIC, css), encoding="utf-8").read())


def _blocks(css):
    """[(selector, body)] for every rule in the stylesheet."""
    text = _text(css)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text)]


def _palette(css, selector):
    """The custom properties a palette block defines, as {name: '#rrggbb'}."""
    found = {}
    for sel, body in _blocks(css):
        if sel == selector:
            for name, value in re.findall(r"(--ea-[\w-]+)\s*:\s*([^;]+);", body):
                found[name] = value.strip()
    return found


def _rgb(hex_colour):
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _luminance(hex_colour):
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contrast_helper_matches_known_values():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("css, light_selector, pairs", SHEETS, ids=SHEET_IDS)
def test_both_palettes_define_the_same_names(css, light_selector, pairs):
    light, dark = _palette(css, light_selector), _palette(css, light_selector + ".ea-dark")
    assert light, "no light palette found"
    assert set(light) == set(dark)


@pytest.mark.parametrize("css, light_selector, pairs", SHEETS, ids=SHEET_IDS)
def test_every_palette_value_is_a_hex_colour(css, light_selector, pairs):
    for selector in (light_selector, light_selector + ".ea-dark"):
        for name, value in _palette(css, selector).items():
            assert re.match(r"^#[0-9a-fA-F]{6}$", value), (selector, name, value)


@pytest.mark.parametrize("css, light_selector, pairs", SHEETS, ids=SHEET_IDS)
def test_rules_use_only_palette_colours(css, light_selector, pairs):
    """A literal colour outside the palettes would look wrong in one mode."""
    palette_selectors = {light_selector, light_selector + ".ea-dark"}
    offenders = []
    for sel, body in _blocks(css):
        if sel in palette_selectors:
            continue
        for declaration in body.split(";"):
            if COLOUR_LITERAL.search(declaration):
                offenders.append((sel, declaration.strip()))
    assert offenders == []


@pytest.mark.parametrize("css, light_selector, pairs", SHEETS, ids=SHEET_IDS)
def test_every_variable_used_is_defined(css, light_selector, pairs):
    used = set(re.findall(r"var\((--ea-[\w-]+)\)", _text(css)))
    assert used <= set(_palette(css, light_selector))


@pytest.mark.parametrize("css, light_selector, text, background, minimum", [
    (css, root + suffix, text, background, minimum)
    for css, root, pairs in SHEETS
    for suffix in ("", ".ea-dark")
    for text, background, minimum in pairs
])
def test_text_is_readable(css, light_selector, text, background, minimum):
    palette = _palette(css, light_selector)
    ratio = contrast(palette[text], palette[background])
    assert ratio >= minimum, "%s on %s in %s %s: %.2f" % (text, background, css, light_selector, ratio)
