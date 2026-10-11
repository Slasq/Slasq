from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

GRAPHQL_URL = "https://api.github.com/graphql"
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount weekday } }
      }
    }
  }
}
"""

ABOUT_WINDOW_TITLE = "maciek.exe"
ABOUT_HEADING = ("Machine Learning · ", "Data Science")  # drugi człon dostaje czerwone podświetlenie
ABOUT_BODY = "Engineering & Data Analysis, 3rd year, Rzeszów University of Technology."
TASKBAR_MENU = ("Slasq",)
STACK_ROWS = (
    ("ml", "Python, PyTorch, scikit-learn, pandas"),
    ("serving", "FastAPI, Docker"),
    ("data", "Oracle SQL, T-SQL, SSIS, Power BI"),
    ("low_level", "C++, MATLAB"),
    ("off_the_clock", "reverse engineering, where it overlaps with my day-to-day tasks"),
)

PIXEL_FONT = "'PS2P','Press Start 2P',monospace"
BODY_FONT = "'VT323',monospace"
TITLE_BAR_HEIGHT = 22
TASKBAR_HEIGHT = 28
LOG_LINE_HEIGHT = 18
GLYPHS = "0123456789!@#$%^&*()"


class ProfileSvgError(Exception):
    pass


class ConfigError(ProfileSvgError):
    pass


class FetchError(ProfileSvgError):
    pass


@dataclass(frozen=True)
class Theme:
    # ten sam motyw w light i dark mode GitHuba
    ink: str = "#0F1026"  # ramki, tekst, pasek tytułu
    window_bg: str = "#FFFFFF"
    dither: str = "#F0F0F0"  # drugi kolor szachownicy
    accent: str = "#5C45FF"
    red: str = "#E6192B"
    code_bg: str = "#FAFAFA"
    code_border: str = "#AAAAAA"
    inactive_shadow_opacity: float = 0.15
    grid_lightness: int = 65
    grid_opacity: float = 0.45
    glyph_lightness: int = 60


@dataclass(frozen=True)
class PlaneLayout:
    width: int = 800
    height: int = 340
    origin_y: float = 150.0
    week_dx: float = 13.0
    week_dy: float = 1.5
    day_dx: float = -9.0
    day_dy: float = 8.0
    max_height: float = 75.0
    wave_amplitude: float = 3.0
    frames: int = 24
    duration_s: float = 4.0  # okres fali
    hue_period_s: float = 8.0  # okres hue i znaków
    peaks: int = 5
    random_slots: int = 16  # losowe znaki: liczba losowań na okres hue
    random_chance: float = 0.04  # odsetek punktów siatki z losowym znakiem w jednym slocie
    seed: int = 7  # stały seed: SVG zmienia się tylko przy zmianie danych albo daty


@dataclass(frozen=True)
class Calendar:
    weeks: list[list[int]]  # [tydzień][dzień tygodnia 0..6, 0 = niedziela]
    total: int


def fetch_calendar(login: str, token: str) -> Calendar:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-svg-generator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.URLError as exc:
        raise FetchError(f"GraphQL request failed: {exc}") from exc

    if payload.get("errors"):
        raise FetchError(f"GraphQL errors: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if user is None:
        raise FetchError(f"user '{login}' not found")

    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks: list[list[int]] = []
    for week in calendar["weeks"]:
        # pierwszy i ostatni tydzień bywają niepełne; brakujące dni to 0
        days = [0] * 7
        for day in week["contributionDays"]:
            days[day["weekday"]] = day["contributionCount"]
        weeks.append(days)
    return Calendar(weeks=weeks, total=calendar["totalContributions"])


def demo_calendar(seed: int = 42) -> Calendar:
    rng = random.Random(seed)
    weeks: list[list[int]] = []
    for week in range(53):
        activity = 0.5 + 0.5 * math.sin(week / 6)
        days = [
            rng.choice([1, 1, 2, 3, 5, 8, 13]) if rng.random() < activity else 0
            for _ in range(7)
        ]
        weeks.append(days)
    return Calendar(weeks=weeks, total=sum(map(sum, weeks)))


FONT_FORMATS = {".ttf": ("font/ttf", "truetype"), ".woff2": ("font/woff2", "woff2"), ".woff": ("font/woff", "woff")}


def font_face_css(font_path: Path, family: str) -> str:
    if not font_path.is_file():
        print(f"warning: font not found at {font_path}, using monospace", file=sys.stderr)
        return ""
    mime, fmt_name = FONT_FORMATS.get(font_path.suffix.lower(), ("font/ttf", "truetype"))
    data = base64.b64encode(font_path.read_bytes()).decode("ascii")
    return f"@font-face{{font-family:'{family}';src:url(data:{mime};base64,{data}) format('{fmt_name}');}}"


def fmt(value: float) -> str:
    return str(round(value))


def svg_root(width: int, height: int, label: str, font_css: str, content: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{escape(label)}">'
        f"<title>{escape(label)}</title>"
        f"<style>{font_css}text{{font-family:{PIXEL_FONT};}}.body{{font-family:{BODY_FONT};}}</style>"
        f"{content}</svg>\n"
    )


def dither_pattern(theme: Theme) -> str:
    # szachownica 2x2 px w kafelku 4x4 px
    return (
        '<pattern id="dither" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="4" fill="{theme.window_bg}"/>'
        f'<rect width="2" height="2" fill="{theme.dither}"/>'
        f'<rect x="2" y="2" width="2" height="2" fill="{theme.dither}"/></pattern>'
    )


def window_chrome(x: int, y: int, w: int, h: int, title: str, theme: Theme, active: bool) -> str:
    bar_bg = theme.ink if active else theme.window_bg
    bar_fg = theme.window_bg if active else theme.ink
    shadow_opacity = 1 if active else theme.inactive_shadow_opacity
    parts = [
        f'<rect x="{x + 4}" y="{y + 4}" width="{w}" height="{h}" fill="{theme.ink}" '
        f'fill-opacity="{shadow_opacity:g}"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{theme.window_bg}" '
        f'stroke="{theme.ink}" stroke-width="2"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{TITLE_BAR_HEIGHT}" fill="{bar_bg}" '
        f'stroke="{theme.ink}" stroke-width="2"/>',
        # przyciski 12x12 z ramką 2 px: close czerwony, drugi biały
        f'<rect x="{x + 6}" y="{y + 6}" width="10" height="10" fill="{theme.red}" '
        f'stroke="{theme.ink}" stroke-width="2"/>',
        f'<rect x="{x + w - 16}" y="{y + 6}" width="10" height="10" fill="{theme.window_bg}" '
        f'stroke="{theme.ink}" stroke-width="2"/>',
    ]
    # Press Start 2P ma stałą szerokość znaku równą rozmiarowi fontu (8 px) plus letter-spacing 1 px
    text_width = len(title) * 9
    center = x + w / 2
    segments = (
        (x + 27, center - text_width / 2 - 10),
        (center + text_width / 2 + 10, x + w - 27),
    )
    for stripe_y in (y + 7, y + 11, y + 15):
        for start, end in segments:
            parts.append(
                f'<rect x="{fmt(start)}" y="{stripe_y}" width="{fmt(end - start)}" '
                f'height="1" fill="{bar_fg}"/>'
            )
    parts.append(
        f'<text x="{fmt(center)}" y="{y + 15}" font-size="8" letter-spacing="1" '
        f'text-anchor="middle" fill="{bar_fg}">{escape(title)}</text>'
    )
    return "".join(parts)


def blinking_block(x: int, y: int, theme: Theme) -> str:
    # kursor z compiler.log: blok 8x14 px, animacja blink 1s
    return (
        f'<rect x="{x}" y="{y}" width="8" height="14" fill="{theme.red}">'
        '<animate attributeName="opacity" values="1;0" dur="1s" calcMode="discrete" '
        'repeatCount="indefinite"/></rect>'
    )


def log_box_height(lines: int) -> int:
    # linie tekstu + kursor w kolejnej linii + 10 px marginesu pod kursorem
    return LOG_LINE_HEIGHT * lines + 30


def render_about(theme: Theme, font_css: str) -> str:
    width, height = 800, 120
    plain, highlighted = ABOUT_HEADING
    # Press Start 2P 12 px: szerokość znaku = 12 px
    plain_w = len(plain) * 12
    hl_x = 19 + plain_w
    hl_w = len(highlighted) * 12 + 8
    content = (
        window_chrome(2, 2, 790, height - 10, ABOUT_WINDOW_TITLE, theme, active=True)
        + f'<text x="19" y="{2 + TITLE_BAR_HEIGHT + 30}" font-size="12" fill="{theme.ink}">'
        + f"{escape(plain)}</text>"
        + f'<rect x="{hl_x - 4}" y="{2 + TITLE_BAR_HEIGHT + 15}" width="{hl_w}" height="20" fill="{theme.red}"/>'
        + f'<text x="{hl_x}" y="{2 + TITLE_BAR_HEIGHT + 30}" font-size="12" fill="{theme.window_bg}">'
        + f"{escape(highlighted)}</text>"
        + f'<text class="body" x="19" y="{2 + TITLE_BAR_HEIGHT + 64}" font-size="18" fill="{theme.ink}">'
        + f"{escape(ABOUT_BODY)}</text>"
    )
    label = f"Maciek. {plain}{highlighted}. {ABOUT_BODY}"
    return svg_root(width, height, label, font_css, content)


def render_stack(theme: Theme, font_css: str) -> str:
    line_h = LOG_LINE_HEIGHT
    x, y, w = 2, 2, 790
    box_x, box_y = x + 10, y + TITLE_BAR_HEIGHT + 8
    box_h = log_box_height(len(STACK_ROWS) + 1)
    win_h = TITLE_BAR_HEIGHT + box_h + 18

    def line(index: int, body: str) -> str:
        return (
            f'<text class="body" x="{box_x + 8}" y="{box_y + line_h * (index + 1)}" '
            f'font-size="18" fill="{theme.ink}">{body}</text>'
        )

    lines = [line(0, f"<tspan fill=\"{theme.accent}\">load</tspan> '@slasq/stack'")]
    for index, (key, value) in enumerate(STACK_ROWS, start=1):
        lines.append(
            line(
                index,
                f'&gt; <tspan fill="{theme.accent}">{escape(key)}</tspan>: {escape(value)} '
                f'<tspan fill="{theme.red}">[OK]</tspan>',
            )
        )
    content = (
        window_chrome(x, y, w, win_h, "stack.log", theme, active=False)
        + f'<rect x="{box_x}" y="{box_y}" width="{w - 20}" height="{box_h}" fill="{theme.code_bg}" '
        f'stroke="{theme.code_border}" stroke-width="2"/>'
        + "".join(lines)
        + blinking_block(box_x + 8, box_y + line_h * (len(STACK_ROWS) + 1) + 6, theme)
    )
    label = "Stack: " + "; ".join(f"{key}: {value}" for key, value in STACK_ROWS)
    # +8 px na cień okna
    return svg_root(800, win_h + 8, label, font_css, content)


def base_heights(calendar: Calendar, layout: PlaneLayout) -> list[list[float]]:
    peak = max((count for week in calendar.weeks for count in week), default=0)
    if peak == 0:
        return [[0.0] * 7 for _ in calendar.weeks]
    # pierwiastek spłaszcza pojedyncze dni z dużą liczbą commitów
    return [[layout.max_height * math.sqrt(count / peak) for count in week] for week in calendar.weeks]


def slot_group(slot: int, slots: int, period: str, body: str) -> str:
    # grupa widoczna tylko w swoim slocie czasu; jedna animacja na grupę zamiast na znak
    start, end = slot / slots, (slot + 1) / slots
    if slot == 0:
        values, key_times, initial = "1;0", f"0;{end:.4f}", 1
    else:
        values, key_times, initial = "0;1;0", f"0;{start:.4f};{end:.4f}", 0
    return (
        f'<g opacity="{initial}"><animate attributeName="opacity" values="{values}" '
        f'keyTimes="{key_times}" calcMode="discrete" dur="{period}" repeatCount="indefinite"/>'
        f"{body}</g>"
    )


def glyph(px: int, py: int, char: str, color: str, theme: Theme) -> str:
    # biały kwadrat pod znakiem zasłania linie siatki
    return (
        f'<rect x="{px - 5}" y="{py - 5}" width="10" height="10" fill="{theme.window_bg}"/>'
        f'<text x="{px}" y="{py + 4}" font-size="8" text-anchor="middle" fill="{color}">{escape(char)}</text>'
    )


def taskbar(width: int, total: int, date: dt.date, theme: Theme) -> str:
    menu_x, parts = 10, []
    for item in TASKBAR_MENU:
        parts.append(f'<text x="{menu_x}" y="18" font-size="8" fill="{theme.window_bg}">{escape(item)}</text>')
        menu_x += len(item) * 8 + 15
    right = f"{date:%d.%m.%Y}"
    stats = f"COMMITS: {total:,}"
    return (
        f'<rect width="{width}" height="{TASKBAR_HEIGHT - 2}" fill="{theme.ink}"/>'
        f'<rect y="{TASKBAR_HEIGHT - 2}" width="{width}" height="2" fill="{theme.red}"/>'
        + "".join(parts)
        + f'<text x="{width - 10}" y="18" font-size="8" text-anchor="end" fill="{theme.window_bg}">'
        f'<tspan fill="{theme.red}">{escape(stats)}</tspan> | {right}</text>'
    )


def render_plane(calendar: Calendar, theme: Theme, font_css: str, layout: PlaneLayout, date: dt.date) -> str:
    n_weeks = len(calendar.weeks)
    if n_weeks == 0:
        raise ConfigError("calendar has no weeks")

    span = (n_weeks - 1) * layout.week_dx - 6 * layout.day_dx
    origin_x = (layout.width - span) / 2 - 6 * layout.day_dx
    heights = base_heights(calendar, layout)

    def project(week: int, day: int, height: float) -> tuple[float, float]:
        px = origin_x + week * layout.week_dx + day * layout.day_dx
        py = layout.origin_y + week * layout.week_dy + day * layout.day_dy - height
        return px, py

    def height_at(week: int, day: int, phase: float) -> float:
        wave = layout.wave_amplitude * math.sin(0.45 * week + 0.9 * day - phase)
        return heights[week][day] + wave

    def wave_phase(t: float) -> float:
        return 2 * math.pi * t / layout.duration_s

    def hue_at(x: float, t: float) -> int:
        # odtwarza kolor gradientu #hue w punkcie x w chwili t (reflect, przesunięcie w prawo)
        shift = (t / layout.hue_period_s) * layout.width
        u = (x - shift) % layout.width
        half_w = layout.width / 2
        hue = 220 + 60 * u / half_w if u <= half_w else 280 - 60 * (u - half_w) / half_w
        return round(hue)

    # siatka: ostatnia klatka równa pierwszej, więc pętla nie przeskakuje
    phases = [2 * math.pi * k / layout.frames for k in range(layout.frames)] + [0.0]
    lines: list[list[tuple[int, int]]] = []
    lines += [[(w, d) for w in range(n_weeks)] for d in range(7)]
    lines += [[(w, d) for d in range(7)] for w in range(n_weeks)]

    wave_dur = f"{layout.duration_s:g}s"
    hue_dur = f"{layout.hue_period_s:g}s"
    paths = []
    for cells in lines:
        frames = []
        for phase in phases:
            points = (project(w, d, height_at(w, d, phase)) for w, d in cells)
            frames.append("M" + "L".join(f"{fmt(px)},{fmt(py)}" for px, py in points))
        paths.append(
            f'<path d="{frames[0]}"><animate attributeName="d" values="{";".join(frames)}" '
            f'dur="{wave_dur}" repeatCount="indefinite"/></path>'
        )

    cells_all = [(w, d) for w in range(n_weeks) for d in range(7)]
    rng = random.Random(layout.seed)

    # losowe znaki tła: 4% punktów na slot, kolor z gradientu pod znakiem
    random_groups = []
    for slot in range(layout.random_slots):
        t = (slot + 0.5) / layout.random_slots * layout.hue_period_s
        body = []
        for w, d in cells_all:
            if rng.random() >= layout.random_chance:
                continue
            px, py = project(w, d, height_at(w, d, wave_phase(t)))
            color = f"hsl({hue_at(px, t)},100%,{theme.glyph_lightness}%)"
            body.append(glyph(round(px), round(py), rng.choice(GLYPHS), color, theme))
        random_groups.append(slot_group(slot, layout.random_slots, hue_dur, "".join(body)))

    ranked = sorted(
        ((count, w, d) for w, d in cells_all if (count := calendar.weeks[w][d]) > 0),
        reverse=True,
    )[: layout.peaks]
    markers = []
    for _, w, d in ranked:
        px, _ = project(w, d, 0.0)
        ys = [str(round(project(w, d, height_at(w, d, phase))[1]) - 2) for phase in phases]
        markers.append(
            f'<rect x="{round(px) - 2}" y="{ys[0]}" width="4" height="4" fill="{theme.red}">'
            f'<animate attributeName="y" values="{";".join(ys)}" dur="{wave_dur}" '
            'repeatCount="indefinite"/></rect>'
        )

    lightness = theme.grid_lightness
    half = layout.width // 2
    defs = (
        "<defs>"
        + dither_pattern(theme)
        + '<linearGradient id="hue" gradientUnits="userSpaceOnUse" '
        f'x1="0" y1="0" x2="{half}" y2="0" spreadMethod="reflect">'
        f'<stop offset="0" stop-color="hsl(220,100%,{lightness}%)"/>'
        f'<stop offset="1" stop-color="hsl(280,100%,{lightness}%)"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" '
        f'from="0 0" to="{layout.width} 0" dur="{hue_dur}" repeatCount="indefinite"/>'
        "</linearGradient></defs>"
    )

    # okno compiler.log: nieaktywne, z polem kodu
    # wysokość z tej samej formuły co stack.log, więc kursor mieści się w polu kodu
    log_box_h = log_box_height(2)
    log_x, log_w, log_h = 20, 330, TITLE_BAR_HEIGHT + log_box_h + 18
    log_y = layout.height - log_h - 16
    box_x, box_y = log_x + 10, log_y + TITLE_BAR_HEIGHT + 8
    log_window = (
        window_chrome(log_x, log_y, log_w, log_h, "compiler.log", theme, active=False)
        + f'<rect x="{box_x}" y="{box_y}" width="{log_w - 20}" height="{log_box_h}" '
        f'fill="{theme.code_bg}" stroke="{theme.code_border}" stroke-width="2"/>'
        + f'<text class="body" x="{box_x + 8}" y="{box_y + 18}" font-size="18" fill="{theme.ink}">'
        f'<tspan fill="{theme.accent}">load</tspan> \'@slasq/contributions\'</text>'
        + f'<text class="body" x="{box_x + 8}" y="{box_y + 36}" font-size="18" fill="{theme.ink}">'
        f'&gt; {calendar.total:,} in the last year <tspan fill="{theme.red}">[OK]</tspan></text>'
        + blinking_block(box_x + 8, box_y + LOG_LINE_HEIGHT * 2 + 6, theme)
    )

    content = (
        defs
        + f'<rect x="1" y="1" width="{layout.width - 2}" height="{layout.height - 2}" fill="url(#dither)" '
        f'stroke="{theme.ink}" stroke-width="2"/>'
        + f'<g fill="none" stroke="url(#hue)" stroke-width="2" stroke-opacity="{theme.grid_opacity:g}" '
        f'shape-rendering="crispEdges">{"".join(paths)}</g>'
        + f'<g shape-rendering="crispEdges">{"".join(random_groups)}</g>'
        + f'<g shape-rendering="crispEdges">{"".join(markers)}</g>'
        + log_window
        + taskbar(layout.width, calendar.total, date, theme)
    )
    label = f"Contribution activity over the last year: {calendar.total:,} contributions"
    return svg_root(layout.width, layout.height, label, font_css, content)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate profile README SVG files.")
    parser.add_argument("--out-dir", type=Path, default=Path("assets"))
    parser.add_argument("--font", type=Path, default=Path("fonts/PressStart2P-Regular.ttf"))
    parser.add_argument("--body-font", type=Path, default=Path("fonts/VT323-Regular.woff2"))
    parser.add_argument("--demo", action="store_true", help="dane syntetyczne, bez API")
    return parser.parse_args(argv)


def load_calendar(demo: bool) -> Calendar:
    if demo:
        return demo_calendar()
    login = os.environ.get("GH_LOGIN")
    token = os.environ.get("GITHUB_TOKEN")
    if not login or not token:
        raise ConfigError("set GH_LOGIN and GITHUB_TOKEN, or use --demo")
    return fetch_calendar(login, token)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        calendar = load_calendar(args.demo)
        font_css = font_face_css(args.font, "PS2P") + font_face_css(args.body_font, "VT323")
        theme, layout = Theme(), PlaneLayout()
        today = dt.datetime.now(dt.timezone.utc).date()
        args.out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "about.svg": render_about(theme, font_css),
            "stack.svg": render_stack(theme, font_css),
            "plane.svg": render_plane(calendar, theme, font_css, layout, today),
        }
        for name, svg in outputs.items():
            path = args.out_dir / name
            path.write_text(svg, encoding="utf-8", newline="\n")
            print(f"{path}: {len(svg.encode('utf-8')) / 1024:.0f} KiB")
    except ProfileSvgError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
