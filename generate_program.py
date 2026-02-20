#!/usr/bin/env python3
"""
Modular 3-day gym program workflow:
1) create-program -> writes program.json
2) fetch-images -> resolves reusable images for exercises
3) build-pdf -> renders final PDF from reviewed artifacts
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PDF_NAME = "3_day_gym_program.pdf"
PROGRAM_JSON = Path("program.json")
ASSETS_DIR = Path("assets")
IMAGE_MANIFEST = ASSETS_DIR / "image_manifest.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
REQUEST_TIMEOUT = 20

PERMISSIVE_LICENSE_MARKERS = {
    "cc-by",
    "cc-by-sa",
    "cc0",
    "public domain",
    "gfdl",
    "pdm",
}


@dataclass
class CreditEntry:
    canonical_key: str
    exercise: str
    title: str
    author: str
    source_url: str
    license: str
    image_path: str
    kind: str  # commons | placeholder


def ascii_clean(value: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for bad, good in replacements.items():
        value = value.replace(bad, good)
    return value.encode("ascii", errors="ignore").decode("ascii")


def slugify(value: str) -> str:
    value = ascii_clean(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "item"


def ensure_ascii_structure(data):
    if isinstance(data, dict):
        return {ascii_clean(str(k)): ensure_ascii_structure(v) for k, v in data.items()}
    if isinstance(data, list):
        return [ensure_ascii_structure(x) for x in data]
    if isinstance(data, str):
        return ascii_clean(data)
    return data


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(ensure_ascii_structure(payload), f, indent=2)


def read_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def choose_font() -> str:
    candidates = [
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("DejaVuSans", "/Library/Fonts/Arial Unicode.ttf"),
        ("Arial", "/Library/Fonts/Arial.ttf"),
    ]
    for font_name, font_path in candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                return font_name
            except Exception:
                continue
    return "Helvetica"


def build_program() -> Dict:
    profile = {
        "sex": "Male",
        "age": 35,
        "height_cm": 183,
        "weight_kg": 85,
        "goal": "Lose fat fast while maintaining muscle and strength",
        "gym_frequency": "3 times per week",
        "session_length": "30-40 minutes",
        "current_issue": "Lifting, but scale movement is slow",
    }

    def ex(name: str, sets_reps: str, note: str, canonical_key: str, alternatives: str = "") -> Dict:
        return {
            "name": name,
            "sets_reps": sets_reps,
            "note": note,
            "canonical_key": canonical_key,
            "alternatives": alternatives,
        }

    days = {
        "A": {
            "title": "Day A - strength-ish",
            "warmup": "Optional 5 min easy bike/row + 1 light set on first 2 lifts",
            "main_work": "25-30 min using supersets",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Leg Press", "3 x 5-8", "Knee-dominant lower", "leg_press", "Hack squat or goblet squat"),
                        ex(
                            "Chest-Supported Row",
                            "3 x 6-8",
                            "Horizontal pull",
                            "chest_supported_row",
                            "Seated cable row or machine row",
                        ),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex(
                            "Flat Dumbbell Bench Press",
                            "3 x 5-8",
                            "Horizontal push",
                            "flat_db_bench_press",
                            "Machine chest press or push-ups",
                        ),
                        ex(
                            "Romanian Deadlift",
                            "3 x 6-8",
                            "Hip hinge",
                            "romanian_deadlift",
                            "Back extension or hip hinge machine",
                        ),
                    ],
                },
            ],
            "core": ex(
                "Cable Pallof Press",
                "2 x 10-12 per side",
                "Brief anti-rotation core",
                "cable_pallof_press",
                "Side plank",
            ),
            "finisher": "Optional 6-8 min: bike/rower intervals, 30 sec hard + 60 sec easy",
        },
        "B": {
            "title": "Day B - volume-ish",
            "warmup": "Optional 5 min incline walk + 1 light set on first 2 lifts",
            "main_work": "25-30 min using supersets",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex(
                            "Goblet Squat",
                            "3 x 8-12",
                            "Knee-dominant lower",
                            "goblet_squat",
                            "Hack squat machine or leg press",
                        ),
                        ex(
                            "Seated Cable Row",
                            "3 x 10-12",
                            "Horizontal pull",
                            "seated_cable_row",
                            "Chest-supported row or machine row",
                        ),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex(
                            "Incline Dumbbell Bench Press",
                            "3 x 8-12",
                            "Horizontal push",
                            "incline_db_bench_press",
                            "Machine incline press or push-ups",
                        ),
                        ex(
                            "Dumbbell Hip Thrust",
                            "3 x 10-12",
                            "Hip hinge/glute focus",
                            "dumbbell_hip_thrust",
                            "Glute bridge",
                        ),
                    ],
                },
            ],
            "core": ex("Dead Bug", "2 x 8-10 per side", "Simple trunk control core", "dead_bug", "Bird dog"),
            "finisher": "Optional 8-10 min: incline treadmill brisk walk, zone 2-ish effort",
        },
        "C": {
            "title": "Day C - balanced",
            "warmup": "Optional 5 min easy cardio + dynamic hips/shoulders",
            "main_work": "25-30 min using supersets",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex(
                            "Dumbbell Split Squat",
                            "3 x 8-10 per leg",
                            "Knee-dominant unilateral",
                            "dumbbell_split_squat",
                            "Reverse lunge",
                        ),
                        ex("Lat Pulldown", "3 x 8-12", "Vertical pull", "lat_pulldown", "Assisted pull-up or high cable row"),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex(
                            "Machine Chest Press",
                            "3 x 8-12",
                            "Horizontal push",
                            "machine_chest_press",
                            "Push-ups",
                        ),
                        ex("Cable Pull-Through", "3 x 10-12", "Hip hinge accessory", "cable_pull_through", "Back extension"),
                    ],
                },
            ],
            "core": ex("Front Plank", "2 x 30-45 sec", "Simple bracing core", "front_plank", "RKC plank"),
            "finisher": "Optional 8 min EMOM: odd min 10 kettlebell swings, even min 8-10 calories bike",
        },
    }

    return {
        "profile": profile,
        "weekly_structure": {
            "warmup": "Optional ~5 min",
            "main": "~25-30 min supersets",
            "finisher": "Optional ~6-10 min",
        },
        "days": days,
        "substitution_map": [
            "Leg press <-> hack squat <-> goblet squat",
            "DB bench <-> machine chest press <-> push-ups",
            "Cable row <-> chest-supported DB row <-> machine row",
            "RDL <-> hip hinge machine <-> back extension",
            "Lat pulldown <-> assisted pull-up <-> high cable row",
            "Pallof press <-> side plank",
        ],
        "superset_rules": [
            "Pair upper+lower or push+pull.",
            "Rest about 45-75 sec between rounds.",
            "Avoid pairing two heavy lower compounds together.",
            "Keep transitions short and stay at 1-3 reps in reserve.",
        ],
        "progression_rules": [
            "Work in the rep range with RIR 1-3 (RPE about 7-9).",
            "If all sets hit the top of range with good form, add load next session.",
            "Upper body jumps: +1 to +2.5 kg total.",
            "Lower body jumps: +2.5 to +5 kg total.",
            "If stalled 2-3 weeks: deload 1 week (load down 10-15% or one less set), then rebuild.",
            "Alternative after stall: swap one movement variant for 4-6 weeks.",
        ],
        "non_gym_guidance": [
            "Increase daily steps from about 5k to 7k-9k average, ramping gradually.",
            "Treat e-bike commute as sustainable zone-2-ish effort 1-2 days/week.",
            "Keep non-gym cardio recoverable, not all-out.",
        ],
        "fat_loss_non_negotiables": [
            "Protein: 1.8-2.2 g/kg/day (about 153-187 g/day).",
            "Sleep: 7-8+ hours per night.",
            "Steps: weekly average 7k-9k/day.",
            "Consistency: moderate, sustainable calorie deficit.",
        ],
        "schedule_example": [
            "Mon: Day A",
            "Tue: e-bike commute (zone-2-ish)",
            "Wed: Day B",
            "Thu: e-bike commute or extra steps",
            "Fri: Day C",
            "Weekend: light activity, recovery, maintain steps",
        ],
    }


def exercise_query_map() -> Dict[str, List[str]]:
    return {
        "leg_press": ["leg press machine exercise"],
        "chest_supported_row": ["chest supported dumbbell row exercise", "seated row exercise gym"],
        "flat_db_bench_press": ["dumbbell bench press exercise"],
        "romanian_deadlift": ["romanian deadlift exercise"],
        "cable_pallof_press": ["Pallof press cable exercise"],
        "goblet_squat": ["goblet squat exercise dumbbell"],
        "seated_cable_row": ["seated cable row exercise"],
        "incline_db_bench_press": ["incline dumbbell bench press exercise"],
        "dumbbell_hip_thrust": ["dumbbell hip thrust exercise", "glute bridge dumbbell exercise"],
        "dead_bug": ["dead bug core exercise"],
        "dumbbell_split_squat": ["dumbbell split squat exercise"],
        "lat_pulldown": ["lat pulldown exercise machine"],
        "machine_chest_press": ["chest press machine exercise"],
        "cable_pull_through": ["cable pull through exercise"],
        "front_plank": ["front plank exercise"],
    }


def extract_license_text(extmetadata: Dict) -> str:
    license_short = extmetadata.get("LicenseShortName", {}).get("value", "")
    license_url = extmetadata.get("LicenseUrl", {}).get("value", "")
    usage = extmetadata.get("UsageTerms", {}).get("value", "")
    return ascii_clean(" | ".join([license_short, license_url, usage]).strip(" |"))


def is_permissive_license(license_text: str) -> bool:
    lower = license_text.lower()
    return any(marker in lower for marker in PERMISSIVE_LICENSE_MARKERS)


def fetch_wikimedia_image(query: str) -> Optional[Dict]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f'filetype:bitmap "{query}"',
        "gsrnamespace": 6,
        "gsrlimit": 10,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
    }
    response = requests.get(COMMONS_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        imageinfo = page.get("imageinfo", [])
        if not imageinfo:
            continue
        info = imageinfo[0]
        extmetadata = info.get("extmetadata", {})
        license_text = extract_license_text(extmetadata)
        if not license_text or not is_permissive_license(license_text):
            continue
        return {
            "title": ascii_clean(page.get("title", "").replace("File:", "")),
            "author": ascii_clean(extmetadata.get("Artist", {}).get("value", "")).strip() or "Unknown",
            "url": info.get("url", ""),
            "description_url": info.get("descriptionurl", ""),
            "license": license_text,
        }
    return None


def create_placeholder_image(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = PILImage.new("RGB", (520, 320), color=(249, 250, 252))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((8, 8, 512, 312), radius=18, outline=(60, 70, 85), width=3, fill=(249, 250, 252))
    draw.ellipse((225, 40, 295, 110), outline=(45, 55, 70), width=5)
    draw.line((260, 110, 260, 190), fill=(45, 55, 70), width=6)
    draw.line((260, 130, 205, 155), fill=(45, 55, 70), width=5)
    draw.line((260, 130, 315, 155), fill=(45, 55, 70), width=5)
    draw.line((260, 190, 220, 250), fill=(45, 55, 70), width=5)
    draw.line((260, 190, 300, 250), fill=(45, 55, 70), width=5)
    draw.line((120, 255, 400, 255), fill=(120, 130, 145), width=4)

    wrapped = textwrap.fill(ascii_clean(label), width=36)
    draw.text((28, 270), wrapped, fill=(30, 35, 40), font=ImageFont.load_default())
    img.save(path, format="PNG")


def download_image(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    with PILImage.open(io.BytesIO(resp.content)) as img:
        img.convert("RGB").save(destination, format="JPEG", quality=90)


def collect_unique_exercises(program: Dict) -> List[Dict]:
    out: List[Dict] = []
    seen = set()
    for day in program["days"].values():
        for superset in day["supersets"]:
            for ex in superset["exercises"]:
                if ex["canonical_key"] not in seen:
                    seen.add(ex["canonical_key"])
                    out.append(ex)
        core = day["core"]
        if core["canonical_key"] not in seen:
            seen.add(core["canonical_key"])
            out.append(core)
    return out


def resolve_images_for_program(program: Dict) -> Dict:
    query_map = exercise_query_map()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    records: List[CreditEntry] = []

    for ex in collect_unique_exercises(program):
        key = ex["canonical_key"]
        exercise_name = ex["name"]
        jpg_path = ASSETS_DIR / f"{slugify(key)}.jpg"
        png_placeholder_path = ASSETS_DIR / f"{slugify(key)}_placeholder.png"

        if jpg_path.exists():
            records.append(
                CreditEntry(
                    canonical_key=key,
                    exercise=exercise_name,
                    title=f"Cached image for {exercise_name}",
                    author="Cached file",
                    source_url=str(jpg_path),
                    license="Cached from prior run",
                    image_path=str(jpg_path),
                    kind="commons",
                )
            )
            continue

        if png_placeholder_path.exists():
            records.append(
                CreditEntry(
                    canonical_key=key,
                    exercise=exercise_name,
                    title=f"Generated placeholder - {exercise_name}",
                    author="Generated locally",
                    source_url="N/A",
                    license="Original generated placeholder",
                    image_path=str(png_placeholder_path),
                    kind="placeholder",
                )
            )
            continue

        chosen: Optional[CreditEntry] = None
        for query in query_map.get(key, [exercise_name]):
            try:
                candidate = fetch_wikimedia_image(query)
                if not candidate or not candidate.get("url"):
                    continue
                download_image(candidate["url"], jpg_path)
                chosen = CreditEntry(
                    canonical_key=key,
                    exercise=exercise_name,
                    title=candidate["title"],
                    author=candidate["author"],
                    source_url=candidate["description_url"] or candidate["url"],
                    license=candidate["license"],
                    image_path=str(jpg_path),
                    kind="commons",
                )
                break
            except Exception:
                continue

        if chosen is None:
            create_placeholder_image(png_placeholder_path, exercise_name)
            chosen = CreditEntry(
                canonical_key=key,
                exercise=exercise_name,
                title=f"Generated placeholder - {exercise_name}",
                author="Generated locally",
                source_url="N/A",
                license="Original generated placeholder",
                image_path=str(png_placeholder_path),
                kind="placeholder",
            )
        records.append(chosen)

    manifest = {
        "generated_from": str(PROGRAM_JSON),
        "credits": [asdict(x) for x in records],
    }
    write_json(IMAGE_MANIFEST, manifest)
    return manifest


def validate_program_constraints(program: Dict) -> None:
    per_day_counts = []
    movement_hits = {
        "knee_dominant": False,
        "hinge": False,
        "horizontal_push": False,
        "horizontal_pull": False,
        "vertical": False,
        "core": False,
    }
    for day in program["days"].values():
        count = sum(len(ss["exercises"]) for ss in day["supersets"]) + 1
        per_day_counts.append(count)
        names = " ".join(ex["name"].lower() for ss in day["supersets"] for ex in ss["exercises"]) + " " + day["core"][
            "name"
        ].lower()
        if any(k in names for k in ["leg press", "squat", "split squat"]):
            movement_hits["knee_dominant"] = True
        if any(k in names for k in ["deadlift", "hip thrust", "pull-through", "back extension"]):
            movement_hits["hinge"] = True
        if any(k in names for k in ["bench press", "chest press", "push-up"]):
            movement_hits["horizontal_push"] = True
        if "row" in names:
            movement_hits["horizontal_pull"] = True
        if any(k in names for k in ["lat pulldown", "pull-up", "overhead"]):
            movement_hits["vertical"] = True
        if any(k in names for k in ["plank", "dead bug", "pallof"]):
            movement_hits["core"] = True
    if not all(4 <= n <= 6 for n in per_day_counts):
        raise ValueError("Each day must have 4-6 exercises including core.")
    if not all(movement_hits.values()):
        missing = [k for k, v in movement_hits.items() if not v]
        raise ValueError(f"Program missing movement patterns: {missing}")


def boxed_section(title: str, lines: List[str], styles, color_hex: str = "#f6f8fb") -> Table:
    text = f"<b>{ascii_clean(title)}</b><br/>" + "<br/>".join(f"- {ascii_clean(x)}" for x in lines)
    table = Table([[Paragraph(text, styles["BodyText"])]] , colWidths=[180 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#2f3b4b")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color_hex)),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def load_image_index_from_manifest(manifest: Dict) -> Dict[str, Dict]:
    return {row["canonical_key"]: row for row in manifest.get("credits", [])}


def render_day_table(day: Dict, image_index: Dict[str, Dict], styles) -> Table:
    rows = [["Image", "Exercise", "Sets x reps", "Notes / substitutions"]]
    for superset in day["supersets"]:
        for ex in superset["exercises"]:
            path = image_index.get(ex["canonical_key"], {}).get("image_path", "")
            image_cell = Paragraph("-", styles["BodyText"])
            if path and Path(path).exists():
                image_cell = RLImage(path, width=26 * mm, height=17 * mm)
            rows.append(
                [
                    image_cell,
                    Paragraph(ascii_clean(ex["name"]), styles["BodyText"]),
                    Paragraph(ascii_clean(ex["sets_reps"]), styles["BodyText"]),
                    Paragraph(ascii_clean(f"{ex['note']}. Alt: {ex['alternatives']}"), styles["BodyText"]),
                ]
            )

    core = day["core"]
    core_path = image_index.get(core["canonical_key"], {}).get("image_path", "")
    core_cell = Paragraph("-", styles["BodyText"])
    if core_path and Path(core_path).exists():
        core_cell = RLImage(core_path, width=26 * mm, height=17 * mm)
    rows.append(
        [
            core_cell,
            Paragraph(ascii_clean(core["name"] + " (core)"), styles["BodyText"]),
            Paragraph(ascii_clean(core["sets_reps"]), styles["BodyText"]),
            Paragraph(ascii_clean(f"{core['note']}. Alt: {core['alternatives']}"), styles["BodyText"]),
        ]
    )

    table = Table(rows, colWidths=[30 * mm, 47 * mm, 25 * mm, 78 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9aa3b2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
            ]
        )
    )
    return table


def build_pdf(program: Dict, manifest: Dict) -> None:
    font_name = choose_font()
    styles = getSampleStyleSheet()
    for name in ["Normal", "BodyText", "Heading1", "Heading2", "Heading3"]:
        styles[name].fontName = font_name

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=20,
        leading=23,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
    )

    doc = SimpleDocTemplate(
        PDF_NAME,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title="3 Day Gym Program",
    )

    p = program["profile"]
    image_index = load_image_index_from_manifest(manifest)
    story = []
    story.append(Paragraph("3-Day Full-Body Gym Program", title_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(
        Paragraph(
            "Fat-loss focused, strength-retention plan. 3 gym days/week. 30-40 min sessions. Simple and repeatable.",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 1.2 * mm))
    story.append(
        Paragraph(
            f"Stats: {p['sex']}, {p['age']} y, {p['height_cm']} cm, {p['weight_kg']} kg | Goal: {ascii_clean(p['goal'])}",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        boxed_section(
            "Session structure",
            [
                f"Warm-up: {program['weekly_structure']['warmup']}",
                f"Main work: {program['weekly_structure']['main']}",
                f"Finisher: {program['weekly_structure']['finisher']}",
            ],
            styles,
            "#eef4ff",
        )
    )
    story.append(Spacer(1, 3 * mm))

    for day_key in ["A", "B", "C"]:
        day = program["days"][day_key]
        block = [
            Paragraph(f"<b>{ascii_clean(day['title'])}</b>", styles["Heading2"]),
            Paragraph(ascii_clean(day["warmup"]), styles["BodyText"]),
            Paragraph(ascii_clean(day["main_work"]), styles["BodyText"]),
            Spacer(1, 1.2 * mm),
            render_day_table(day, image_index, styles),
            Spacer(1, 1.2 * mm),
            Paragraph(ascii_clean(day["finisher"]), styles["BodyText"]),
            Spacer(1, 3 * mm),
        ]
        story.append(KeepTogether(block))

    story.append(boxed_section("Superset rules", program["superset_rules"], styles, "#eefbf4"))
    story.append(Spacer(1, 2 * mm))
    story.append(boxed_section("Progression", program["progression_rules"], styles, "#fff8ec"))
    story.append(Spacer(1, 2 * mm))
    story.append(boxed_section("Fat loss non-negotiables", program["fat_loss_non_negotiables"], styles, "#ffeef1"))
    story.append(Spacer(1, 2 * mm))
    story.append(boxed_section("How to schedule the week (example)", program["schedule_example"], styles, "#f2f2ff"))
    story.append(Spacer(1, 2 * mm))
    story.append(boxed_section("Non-gym day guidance", program["non_gym_guidance"], styles, "#eef6ff"))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("<b>Image credits</b>", styles["Heading2"]))
    credit_rows = [["Exercise", "Image title", "Author", "Source URL", "License"]]
    for row in manifest.get("credits", []):
        credit_rows.append(
            [
                Paragraph(ascii_clean(row["exercise"]), styles["BodyText"]),
                Paragraph(ascii_clean(row["title"]), styles["BodyText"]),
                Paragraph(ascii_clean(row["author"]), styles["BodyText"]),
                Paragraph(ascii_clean(row["source_url"]), styles["BodyText"]),
                Paragraph(ascii_clean(row["license"]), styles["BodyText"]),
            ]
        )

    credit_table = Table(credit_rows, colWidths=[30 * mm, 38 * mm, 25 * mm, 49 * mm, 38 * mm], hAlign="LEFT")
    credit_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#a7adb7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    story.append(credit_table)
    doc.build(story)


def cmd_create_program(args) -> int:
    program = build_program()
    validate_program_constraints(program)
    write_json(PROGRAM_JSON, program)
    print(f"Created {PROGRAM_JSON}. Review and edit it before the next step.")
    return 0


def cmd_fetch_images(args) -> int:
    if not PROGRAM_JSON.exists():
        raise FileNotFoundError(f"{PROGRAM_JSON} not found. Run create-program first.")
    program = read_json(PROGRAM_JSON)
    validate_program_constraints(program)
    manifest = resolve_images_for_program(program)
    commons_count = sum(1 for x in manifest["credits"] if x["kind"] == "commons")
    placeholder_count = sum(1 for x in manifest["credits"] if x["kind"] == "placeholder")
    print(f"Wrote {IMAGE_MANIFEST} ({commons_count} commons, {placeholder_count} placeholders).")
    return 0


def cmd_build_pdf(args) -> int:
    if not PROGRAM_JSON.exists():
        raise FileNotFoundError(f"{PROGRAM_JSON} not found. Run create-program first.")
    if not IMAGE_MANIFEST.exists():
        raise FileNotFoundError(f"{IMAGE_MANIFEST} not found. Run fetch-images first.")
    program = read_json(PROGRAM_JSON)
    manifest = read_json(IMAGE_MANIFEST)
    validate_program_constraints(program)
    build_pdf(program, manifest)
    print(f"Created {PDF_NAME}.")
    return 0


def cmd_all(args) -> int:
    cmd_create_program(args)
    cmd_fetch_images(args)
    cmd_build_pdf(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modular gym program generator: create program, fetch images, then build PDF."
    )
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create-program", help="Generate program.json only.")
    p_create.set_defaults(func=cmd_create_program)

    p_images = sub.add_parser("fetch-images", help="Resolve/download exercise images into assets + manifest.")
    p_images.set_defaults(func=cmd_fetch_images)

    p_pdf = sub.add_parser("build-pdf", help="Build 3_day_gym_program.pdf from program.json + image manifest.")
    p_pdf.set_defaults(func=cmd_build_pdf)

    p_all = sub.add_parser("all", help="Run full pipeline: create-program -> fetch-images -> build-pdf.")
    p_all.set_defaults(func=cmd_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
