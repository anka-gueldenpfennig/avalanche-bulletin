import requests
import datetime
import math
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import hashlib
from collections import OrderedDict
import argparse
from zoneinfo import ZoneInfo
from pathlib import Path
import xml.etree.ElementTree as ET


# METHODS
# --- compass methods ---
# define circle
def _pt(r, ang_deg):
    a = math.radians(ang_deg)
    return (r * math.cos(a), r * math.sin(a))


# make compass petals
def _petal_polygon(theta_c, r_in, r_out, gap_deg, tip_len):
    """Return vertices for a 'petal' with a centered triangular tip."""
    half = 22.5 - gap_deg / 2.0
    start = theta_c - half
    end = theta_c + half

    p0 = _pt(r_in, start)  # inner-left
    p1 = _pt(r_out, start)  # outer-left
    p2 = _pt(r_out + tip_len, theta_c)  # centered tip
    p3 = _pt(r_out, end)  # outer-right
    p4 = _pt(r_in, end)  # inner-right
    return [p0, p1, p2, p3, p4]

# make actual compass
def draw_compass(expos, ax=None, *,
                 r_inner=0.30, r_outer=1.0,
                 gap_deg=3.0,
                 tip_len_diag=0.28, tip_len_card=0.40,  # diagonals vs cardinals
                 face_on="#9fb7ff", face_off="#e7e7e7",
                 edge="#333333", lw=3.0,
                 label_size=21, label_offset=1.6,
                 title=None):
    expos = {e.upper() for e in expos}
    if ax is None:
        fig, ax = plt.subplots(figsize=(4, 4))

    for d in ORDER:
        theta_c = CENTER_ANGLE[d]
        # choose longer tips for cardinals
        tip_len = tip_len_card if d in CARDINALS else tip_len_diag
        verts = _petal_polygon(theta_c, r_inner, r_outer, gap_deg, tip_len)
        poly = Polygon(verts, closed=True,
                       facecolor=(face_on if d in expos else face_off),
                       edgecolor=edge, linewidth=lw, joinstyle='round')
        ax.add_patch(poly)

    # center dot
    ax.add_artist(plt.Circle((0, 0), r_inner * 0.22, color=edge))

    # labels
    for d in ORDER:
        ang = math.radians(CENTER_ANGLE[d])
        x = label_offset * r_outer * math.cos(ang)
        y = label_offset * r_outer * math.sin(ang)
        ax.text(x, y, d, ha='center', va='center', fontsize=label_size, color=edge)

    ax.set_aspect('equal', 'box')
    ax.set_xlim(-1.6 * r_outer, 1.6 * r_outer)
    ax.set_ylim(-1.6 * r_outer, 1.6 * r_outer)
    ax.axis('off')
    if title:
        ax.set_title(title, pad=14, fontsize=14, color=edge)
    return ax


# save compass to file
def save_compass(expos, path, fmt="svg", *, bg_transparent=True, dpi=180):
    fig, ax = plt.subplots(figsize=(4, 4))
    draw_compass(expos, ax=ax)
    kw = dict(bbox_inches="tight", pad_inches=0.01)
    if fmt.lower() == "svg":
        fig.savefig(path, format="svg", transparent=bg_transparent, **kw)
    else:
        fig.savefig(path, format=fmt, dpi=dpi, transparent=bg_transparent, **kw)
    plt.close(fig)

# define filename for compass rose icon from exposition list
def filename_for_expos(expos, prefix="compass_fr_", fmt="svg"):
    key = ",".join(sorted(e.upper() for e in expos))
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"{prefix}{h}.{fmt}"


# --- end of compass methods ---

# --- grouping methods ---
# Normalize elevation ranges for grouping
def _elev_key(elev):
    if not elev:
        return ('all', None, None)
    return (
        'range',
        elev.get('lowerBound'),  # can be None
        elev.get('upperBound'),  # can be None
    )


# aspects order for the compass rose icon
def _aspects_key(aspects):
    if aspects in (None, [], ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']):
        return ('all',)
    return tuple(aspects)  # keep order to avoid surprise; or use tuple(sorted(aspects))


# tidy comment field for grouping
def _comment_key(c):
    return (c or '').strip()


# check for "Sonstige Probleme" type
def is_pure_other(entries):
    return all(pt == "no_distinct_avalanche_problem" for pt, _ in entries)


# --- end of grouping methods ---

# handling date input
def parse_active_at(s: str) -> datetime:
    """
    Accepts:
      - 'today' → returns today at 08:00 in Europe/Zurich
      - 'YYYY-MM-DD' → builds 08:00 local time that day
      - 'YYYY-MM-DDTHH:MM[:SS][+/-HH:MM]' → parsed as-is (timezone-aware)
    """
    if s == "today":
        return datetime.datetime.now(TZ).replace(hour=8, minute=0, second=0, microsecond=0)

    try:
        # Full ISO with or without offset
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        # Maybe just a date
        d = datetime.date.fromisoformat(s)
        return datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ)

# --- build HTML methods ---
# styles header
def styles():
    html_styles = """<!DOCTYPE html>
    <html lang="de">
    <head>
      <meta charset="UTF-8">
      <title>Bulletin d'avalanche</title>
      <style>
        body {
          font-family: Helvetica, Arial, sans-serif;
          font-size: 16px;
          font-weight: 300;
          line-height: 1.5;
          padding: 20px;
          max-width: 2000px;
          margin: auto;
        }
        h1, h2, h3, h4, h5, h6 {
          font-family: Mark, Arial, sans-serif;
          font-weight: 700;
          letter-spacing: .02em;
          margin-top: 1em;
        }
        .section {
          margin-bottom: 20px;
        }
        .danger {
          font-weight: bold;
        }
        .subheading {
          font-weight: bold;
          margin-top: 10px;
        }
        .alert-beacon{
          position:fixed;
          top:16px;
          right:20px;
          width:16px; height:16px;
          border-radius:50%;
          background:#ff3b30;                 /* default red */
          box-shadow:
            0 0 0 3px rgba(255,59,48,.25),
            0 0 12px rgba(255,59,48,.6);
          z-index:9999;
          animation:beacon-blink 1.2s steps(2, end) infinite; /* ~0.83 Hz (safe) */
        }

        @keyframes beacon-blink{
          0%,49%   { opacity:1; }
          50%,100% { opacity:.15; }            /* dim instead of fully off = nicer */
        }

      </style>
    </head>
    <body>
    """

    return html_styles


# find highest warning level in dangerRatings to define overall warning level
def highest_warning(region_info):
    # iterate through warnings and collect highest only for overall warning level
    for dr in region_info.get("dangerRatings", []):
        # check if there is a previous warning (ie: more than one). If yes, save it to old_warning. If not, save 0
        if 'mainValue' in locals() and mainValue is not None:
            old_warning = warning_numbers.get(mainValue, mainValue)
        else:
            old_warning = 0

        # get new mainValue
        mainValue = dr.get("mainValue")

        # only save new mainValue number if it's higher than the previous one -> always show highest overall level
        new_warning = warning_numbers.get(mainValue, mainValue)

        if new_warning > old_warning:
            mainValue = new_warning
        else:
            mainValue = old_warning

    return mainValue


# get the +/-/= too
def warning_subdivision(region_info):
    dr = region_info.get("dangerRatings", [])[0]
    mainValue = dr.get("customData")
    ch = mainValue.get("CH")
    sub = ch.get("subdivision")
    sub_sign = subdiv_dict.get(sub, sub)

    if sub_sign is None:
        sub_sign = ("")

    return sub_sign


def html_header(mainValue, subdiv_value, warnings, hex_warnings):
    # Top: Main heading
    html_header = []
    html_header.append("<h1 style='margin:0;'>Bulletin d'avalanche</h1>")

    # turn on warning light when level is 3 or higher (top right corner)
    if mainValue >= 3:
        html_header.append(f"<div class='alert-beacon alert' aria-hidden='true' title='Warnsignal'></div>")

    # start section: overall danger rating (icon + text)
    html_header.append(
        "<div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:30px;'>")
    html_header.append("<div style='display:flex; align-items:center; gap:10px;'>")

    # get warning word in German + matching colour
    german_warning = warnings.get(mainValue, mainValue)
    hex_warning = hex_warnings.get(mainValue, mainValue)

    # add icon to html
    html_header.append(f"<img src='static/images/{mainValue}.png' style='height:60px;' />")

    # add warning level to html (with matching colour)
    if hex_warning == "#ffff00" or hex_warning == "#ccff66":
        html_header.append(
            f"<span style='font-size:1.4em; font-weight:700; background-color:{hex_warning}; color:#000000; padding: 2px 6px; border-radius:4px; font-weight:700;'>Niveau de danger: {german_warning} ({mainValue}{subdiv_value})</h2>"
        )
    else:
        html_header.append(
            f"<span style='font-size:1.4em; font-weight:700; color:{hex_warning}; font-weight:700;'>Niveau de danger: {german_warning} ({mainValue}{subdiv_value})</h2>"
        )

    # close warning level + header row
    html_header.append("</div>")
    html_header.append("</div>")

    # make list into string to add to html
    html_header = "\n".join(html_header)

    return html_header


# make "card" for each problem type - render HTML
def render_group_card(g):
    # Deduplicate and order problem types for the header row
    seen = set()
    types = []
    for pt, german in g["problem_entries"]:
        if pt not in seen:
            seen.add(pt);
            types.append((pt, german))

    # --- one card (grid cell) ---
    html_output.append("<div style='min-width:0; box-sizing:border-box;'>")

    # inner: left (3+ rows type, altitude, exposition) + right (comment)
    html_output.append("<div style='display:flex; align-items:flex-start; gap:16px;'>")

    # LEFT stack
    html_output.append("<div style='display:flex; flex-direction:column; gap:8px;'>")

    # === Problem type rows (one row per type: icon left, label right) ===
    # Deduplicate & order problem types for consistent output
    seen = set()
    types = []
    for pt, german in g["problem_entries"]:
        if pt not in seen:
            seen.add(pt)
            types.append((pt, german))

    for pt, german in types:
        html_output.append("<div style='display:flex; align-items:center; gap:10px; margin-bottom:6px;'>")

        # icon (skip for 'no_distinct_avalanche_problem')
        if pt != "no_distinct_avalanche_problem":
            html_output.append(
                f"<img src='static/images/{pt}.jpg' style='max-height:48px; max-width:48px;' />"
            )
            label = german
        else:
            # keep spacing aligned when there’s no icon
            html_output.append("<div style='width:48px; height:48px; flex:0 0 48px;'></div>")
            label = "Pas de problème avalancheux particulier"

        # label badge for problem type
        html_output.append(
            f"<span style='display:inline-block; padding:2px 8px; border-radius:12px; background:#f2f2f2; font-weight:700;'>{label}</span>"
        )

        html_output.append("</div>")
    # === end problem type rows ===

    # Row 2: Altitude
    html_output.append("<div style='display:flex; align-items:center;'>")
    if g['mountain_icon']:
        html_output.append(
            f"<img src='static/images/{g['mountain_icon']}' style='max-height:60px; max-width:60px; margin-right:10px;' />")
    html_output.append(
        f"<p style='margin:0; overflow-wrap:anywhere; word-break:break-word;'><b style='font-weight:700;'>Plage d'altitude:</b> {g['elev_text']}</p>")
    html_output.append("</div>")

    # Row 3: Exposition
    html_output.append("<div style='display:flex; align-items:center;'>")
    if g['fname']:
        html_output.append(
            f"<img src='static/images/{g['fname']}' style='max-height:60px; max-width:60px; margin-right:10px;' />")
    html_output.append(
        f"<p style='margin:0; overflow-wrap:anywhere; word-break:break-word;'><b style='font-weight:700;'>Exposition:</b> {g['expo_text']}</p>")
    html_output.append("</div>")

    # close left
    html_output.append("</div>")

    # RIGHT: comment
    html_output.append("<div style='flex:1; min-width:140px;'>")
    html_output.append(
        f"<p style='margin:0; overflow-wrap:anywhere; word-break:break-word;'><b style='font-weight:700;'>Description des dangers:</b> {g['comment']}</p>")
    html_output.append("</div>")

    # --- close inner + card ---
    html_output.append("</div>")
    html_output.append("</div>")


def footer_date(ACTIVE_AT):
    # Parse ISO format into datetime
    dt = datetime.fromisoformat(ACTIVE_AT)

    # Format into German-style date/time: dd.mm.yyyy, HH:MM
    formatted_date = dt.strftime("%d.%m.%Y, %H:%M")

    # Footer note (fixed bottom right)
    html_date = f"""
    <div style='position:fixed; bottom:10px; right:20px; font-size:0.9em; color:#555;'>
      Zuletzt aktualisiert: {formatted_date}
    </div>
    """

    return html_date


# MAIN CODE

# dictionary definitions (translations, warning levels, hex codes for warning level colouring)
warning_numbers = {
    "low": 1,
    "moderate": 2,
    "considerable": 3,
    "high": 4,
    "very high": 5
}

warnings = {
    1: "faible",
    2: "limité",
    3: "marqué",
    4: "fort",
    5: "très fort"
}

subdiv_dict = {
    "neutral": "=",
    "minus": "-",
    "plus": "+",
    "equal": "="
}

hex_warnings = {
    1: "#ccff66",
    2: "#ffff00",
    3: "#ff9900",
    4: "#ff0000",
    5: "#ff0000"
}

snow_type = {
    "new_snow": "Neige fraîche",
    "wind_slab": "Neige soufflée",
    "gliding_snow": "Avalanches de glissement",
    "wet_snow": "Neige mouillée",
    "persistent_weak_layers": "Neige ancienne"
}

aspects_dict = {
    'N': 'N',
    'NE': 'NE',
    'E': 'E',
    'SE': 'SE',
    'S': 'S',
    'SW': 'SO',
    'W': 'O',
    'NW': 'NO'
}

# Global Config
REGION_ID = "CH-4211"  # Leukerbad - Lötschental
LANG = "fr"
TZ = ZoneInfo("Europe/Zurich")

# for automation
parser = argparse.ArgumentParser()
parser.add_argument("--date", default="today")
parser.add_argument("--out", default="bulletin/output/bulletin.html")
args = parser.parse_args()

# figure out date
ACTIVE_AT = parse_active_at(args.date)

url = f"https://aws.slf.ch/api/bulletin/caaml/{LANG}/geojson"
params = {"activeAt": ACTIVE_AT}

# get data from SLF API
resp = requests.get(url, params=params)
resp.raise_for_status()
data = resp.json()

# Compass config
ORDER = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']
CENTER_ANGLE = {d: 90 - i * 45 for i, d in enumerate(ORDER)}
CARDINALS = {'N', 'E', 'S', 'O'}

# get bulletin for Leukerbad - Lötschental region ID
region_info = None
for feat in data.get("features", []):
    for r in feat.get("properties", {}).get("regions", []):
        if r.get("regionID") == REGION_ID:
            region_info = feat["properties"]
            break
    if region_info:
        break

# return error if no active bulletin
if not region_info:
    print(f"Region de {REGION_ID} introuvable.")
# otherwise start building output
else:
    # --- Build HTML content ---
    html_output = []

    # build styles
    html_styles = styles()
    html_output.append(html_styles)

    # get highest warning level
    mainValue = highest_warning(region_info)
    subdiv_value = warning_subdivision(region_info)

    # assemble top of html (heading, overall warning level icon + text, warning light)
    html_top = html_header(mainValue, subdiv_value, warnings, hex_warnings)
    html_output.append(html_top)

    # individual problems section
    # Build groups keyed by identical non-type info
    groups = OrderedDict()
    for ap in region_info.get("avalancheProblems", []):
        elev = ap.get("elevation", {})
        aspects = ap.get("aspects")
        k = (_elev_key(elev), _aspects_key(aspects), _comment_key(ap.get("comment")))

        if k not in groups:
            # Compute once per group
            # elevation text + mountain icon
            if elev:
                lower = elev.get("lowerBound")
                upper = elev.get("upperBound")
                if lower is None and upper is not None:
                    elev_text = f"en dessous de {upper}m"
                    mountain_icon = "below_mountain.png"
                elif upper is None and lower is not None:
                    elev_text = f"à plus de {lower}m"
                    mountain_icon = "above_mountain.png"
                else:
                    elev_text = f"{lower}-{upper}m" if lower is not None and upper is not None else "toutes les altitudes"
                    mountain_icon = "all_mountain.png"
            else:
                elev_text = "toutes les altitudes"
                mountain_icon = "all_mountain.png"

            # exposition text + compass icon
            if aspects in (None, [], ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']):
                expo_text = "toutes les expositions"
                fr_asp_list = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']

            # otherwise, make list of aspects while changing letters to correct French ones
            else:
                fr_asp_list = []
                for aspect in aspects:
                    fr_asp = aspects_dict.get(aspect)
                    if fr_asp is None:
                        fr_asp = aspect

                    fr_asp_list.append(fr_asp)

                expo_text = ", ".join(fr_asp_list)

            # save compass rose
            fname = filename_for_expos(fr_asp_list, fmt="svg")
            save_compass(fr_asp_list, f"bulletin/static/images/{fname}", fmt="svg")

            # group problem types by same elevation/exposition/comment to deduplicate
            groups[k] = {
                "problem_entries": [],  # will collect (problem_type, german_type)
                "mountain_icon": mountain_icon,
                "elev_text": elev_text,
                "fname": fname,
                "expo_text": expo_text,
                "comment": ap.get("comment"),
                "raw": []
            }

        pt = ap.get("problemType")
        german = snow_type.get(pt, pt)
        groups[k]["problem_entries"].append((pt, german))
        groups[k]["raw"].append(ap)

    normal_groups = []
    other_groups = []
    for g in groups.values():
        (other_groups if is_pure_other(g["problem_entries"]) else normal_groups).append(g)

    # Problems grid container (2 equal columns)
    html_output.append(
        "<div style='display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:40px; align-items:start; margin-bottom:30px;'>")

    # Render normal groups, then pure 'other'
    for g in normal_groups:
        render_group_card(g)
    for g in other_groups:
        render_group_card(g)

    html_output.append("</div>")  # end grid

    # make date/time footer
    html_date = footer_date(ACTIVE_AT)
    html_output.append(html_date)

    html_output.append("</body></html>")

    # Write to file
    BASE = Path(__file__).resolve().parent
    out_path = BASE / "signage_bulletin_fr.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_output))