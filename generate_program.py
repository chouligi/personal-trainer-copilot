#!/usr/bin/env python3
"""
Program workflow:
1) profile-create / profile-update
2) generate-draft -> writes programs/<user>_draft.json
3) user reviews draft JSON
4) approve-program -> writes programs/<user>_final.json
5) fetch-images + build-pdf
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shutil
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont


PROFILES_DIR = Path("profiles")
PROGRAMS_DIR = Path("programs")
ASSETS_DIR = Path("assets")
IMAGE_MANIFEST = ASSETS_DIR / "image_manifest.json"
DEFAULT_PDF_NAME = "program_report.pdf"
DEFAULT_HTML_NAME = "program_report.html"
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


def program_path(user: str, stage: str) -> Path:
    return PROGRAMS_DIR / f"{slugify(user)}_{stage}.json"


def profile_path(user: str) -> Path:
    return PROFILES_DIR / f"{slugify(user)}.json"


def default_profile(user: str) -> Dict:
    return {
        "user_id": slugify(user),
        "name": user,
        "sex": "Prefer not to say",
        "age": 30,
        "height_cm": 175,
        "weight_kg": 75,
        "goal": "general_fitness",
        "gym_days": 3,
        "session_length_minutes": 40,
        "experience_level": "beginner-intermediate",
        "equipment": "full_gym",
        "notes": "",
    }


def validate_profile(profile: Dict) -> None:
    required = [
        "user_id",
        "name",
        "age",
        "height_cm",
        "weight_kg",
        "goal",
        "gym_days",
        "session_length_minutes",
        "equipment",
    ]
    missing = [k for k in required if k not in profile]
    if missing:
        raise ValueError(f"Profile missing fields: {missing}")
    gym_days = int(profile["gym_days"])
    if gym_days < 2 or gym_days > 5:
        raise ValueError("gym_days must be between 2 and 5")


def ex(name: str, note: str, canonical_key: str, alternatives: str = "") -> Dict:
    return {
        "name": name,
        "sets_reps": "3 x 8-12",
        "note": note,
        "canonical_key": canonical_key,
        "alternatives": alternatives,
    }


def day_templates() -> List[Dict]:
    return [
        {
            "key": "A",
            "title": "Day A - lower + pull focus",
            "warmup": "5 min easy cardio + one light set on first two lifts",
            "main_work": "Superset style, short transitions, smooth tempo",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Leg Press", "Knee-dominant lower", "leg_press", "Hack squat or goblet squat"),
                        ex(
                            "Chest-Supported Row",
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
                            "Horizontal push",
                            "flat_db_bench_press",
                            "Machine chest press or push-ups",
                        ),
                        ex("Romanian Deadlift", "Hip hinge", "romanian_deadlift", "Back extension"),
                    ],
                },
            ],
            "core": ex("Cable Pallof Press", "Anti-rotation core", "cable_pallof_press", "Side plank"),
            "finisher": "Optional 6-8 min intervals: 30 sec hard + 60 sec easy",
        },
        {
            "key": "B",
            "title": "Day B - upper + glute focus",
            "warmup": "5 min incline walk + shoulder/hip prep",
            "main_work": "Superset style, controlled eccentric and full range",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Goblet Squat", "Knee-dominant lower", "goblet_squat", "Leg press"),
                        ex("Seated Cable Row", "Horizontal pull", "seated_cable_row", "Machine row"),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex(
                            "Incline Dumbbell Bench Press",
                            "Horizontal push",
                            "incline_db_bench_press",
                            "Machine incline press",
                        ),
                        ex("Dumbbell Hip Thrust", "Glute/hinge", "dumbbell_hip_thrust", "Glute bridge"),
                    ],
                },
            ],
            "core": ex("Dead Bug", "Simple trunk control core", "dead_bug", "Bird dog"),
            "finisher": "Optional 8-10 min brisk incline treadmill walk",
        },
        {
            "key": "C",
            "title": "Day C - balanced full-body",
            "warmup": "5 min easy cardio + dynamic mobility",
            "main_work": "Superset style, keep 1-3 reps in reserve",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Dumbbell Split Squat", "Unilateral knee-dominant", "dumbbell_split_squat", "Reverse lunge"),
                        ex("Lat Pulldown", "Vertical pull", "lat_pulldown", "Assisted pull-up"),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex("Machine Chest Press", "Horizontal push", "machine_chest_press", "Push-ups"),
                        ex("Cable Pull-Through", "Hip hinge accessory", "cable_pull_through", "Back extension"),
                    ],
                },
            ],
            "core": ex("Front Plank", "Bracing core", "front_plank", "RKC plank"),
            "finisher": "Optional 8 min EMOM: swings/bike calories",
        },
        {
            "key": "D",
            "title": "Day D - overhead + single-leg",
            "warmup": "5 min bike + shoulder mobility",
            "main_work": "Superset style, rest 45-75 sec between rounds",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Overhead Dumbbell Press", "Vertical push", "overhead_db_press", "Machine shoulder press"),
                        ex("One-Arm Cable Row", "Horizontal pull", "one_arm_cable_row", "Chest-supported row"),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex("Bulgarian Split Squat", "Unilateral lower", "bulgarian_split_squat", "Walking lunge"),
                        ex("Hamstring Curl Machine", "Posterior chain accessory", "hamstring_curl_machine", "Swiss ball curl"),
                    ],
                },
            ],
            "core": ex("Side Plank", "Anti-lateral flexion core", "side_plank", "Pallof press"),
            "finisher": "Optional 6-8 min rower intervals",
        },
        {
            "key": "E",
            "title": "Day E - posterior chain + pull",
            "warmup": "5 min row + light movement prep",
            "main_work": "Superset style, controlled reps with full lockout",
            "supersets": [
                {
                    "label": "Superset 1",
                    "exercises": [
                        ex("Trap Bar Deadlift", "Primary hinge", "trap_bar_deadlift", "Romanian deadlift"),
                        ex("Incline Push-up", "Upper push accessory", "incline_push_up", "Machine chest press"),
                    ],
                },
                {
                    "label": "Superset 2",
                    "exercises": [
                        ex("Walking Lunge", "Knee-dominant lower", "walking_lunge", "Split squat"),
                        ex("Assisted Pull-up", "Vertical pull", "assisted_pull_up", "Lat pulldown"),
                    ],
                },
            ],
            "core": ex("Bird Dog", "Simple spinal stability", "bird_dog", "Dead bug"),
            "finisher": "Optional 8 min moderate bike",
        },
    ]


def apply_goal_rules(program: Dict, goal: str) -> None:
    goal_key = slugify(goal)
    first_pair = "4 x 4-6"
    second_pair = "3 x 6-8"
    core_scheme = "2 x 30-45 sec or 8-12 reps"
    finisher = "Optional 6-10 min easy conditioning"

    if goal_key == "fat_loss":
        first_pair = "3 x 8-12"
        second_pair = "3 x 10-15"
        core_scheme = "2 x 10-12 reps or 30-45 sec"
        finisher = "Optional 8-12 min zone-2 or intervals"
    elif goal_key == "muscle_gain":
        first_pair = "4 x 6-10"
        second_pair = "3 x 8-12"
        core_scheme = "3 x 10-15 reps or 30-60 sec"
        finisher = "Optional 6-8 min easy cardio"
    elif goal_key == "general_fitness":
        first_pair = "3 x 6-10"
        second_pair = "3 x 8-12"
        core_scheme = "2 x 10-12 reps or 30-45 sec"

    for day in program["days"].values():
        for idx, superset in enumerate(day["supersets"]):
            scheme = first_pair if idx == 0 else second_pair
            for exercise in superset["exercises"]:
                exercise["sets_reps"] = scheme
        day["core"]["sets_reps"] = core_scheme
        day["finisher"] = finisher


def build_program(profile: Dict, days: int, goal: str) -> Dict:
    templates = day_templates()
    selected = templates[:days]

    program_days = {}
    for day in selected:
        program_days[day["key"]] = {
            "title": day["title"],
            "warmup": day["warmup"],
            "main_work": day["main_work"],
            "supersets": day["supersets"],
            "core": day["core"],
            "finisher": day["finisher"],
        }

    program = {
        "profile": profile,
        "goal": goal,
        "weekly_structure": {
            "warmup": "5 minutes",
            "main": "25-35 minutes supersets",
            "finisher": "5-10 minutes optional",
        },
        "days": program_days,
        "substitution_map": [
            "Leg press <-> hack squat <-> goblet squat",
            "DB bench <-> machine chest press <-> push-ups",
            "Cable row <-> chest-supported row <-> machine row",
            "RDL/Trap bar <-> hinge machine <-> back extension",
            "Lat pulldown <-> assisted pull-up",
            "Pallof press <-> plank variants",
        ],
        "superset_rules": [
            "Pair upper+lower or push+pull when possible.",
            "Rest 45-75 sec between rounds.",
            "Keep transitions short and stable.",
            "Stop sets with 1-3 reps in reserve.",
        ],
        "progression_rules": [
            "Hit the top of the rep range before adding weight.",
            "Upper body: add 1-2.5 kg total when ready.",
            "Lower body: add 2.5-5 kg total when ready.",
            "If stalled 2-3 weeks, deload 1 week and rebuild.",
        ],
        "non_gym_guidance": [
            "Keep daily steps consistent and gradually increase.",
            "Use low-intensity cardio for recovery, not exhaustion.",
            "Prioritize hydration and sleep.",
        ],
        "fat_loss_non_negotiables": [
            "Protein target: 1.8-2.2 g/kg/day.",
            "Sleep: 7-8+ hours.",
            "Progressive overload with good form.",
            "Nutrition aligned to goal and adherence.",
        ],
        "schedule_example": [f"Day {day_key}: training" for day_key in program_days.keys()],
    }

    apply_goal_rules(program, goal)
    validate_program_constraints(program)
    return program


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
        "overhead_db_press": ["dumbbell overhead press exercise"],
        "one_arm_cable_row": ["one arm cable row exercise"],
        "bulgarian_split_squat": ["bulgarian split squat exercise"],
        "hamstring_curl_machine": ["hamstring curl machine exercise"],
        "side_plank": ["side plank exercise"],
        "trap_bar_deadlift": ["trap bar deadlift exercise"],
        "incline_push_up": ["incline push up exercise"],
        "walking_lunge": ["walking lunge exercise"],
        "assisted_pull_up": ["assisted pull up machine exercise"],
        "bird_dog": ["bird dog core exercise"],
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
            for exercise in superset["exercises"]:
                if exercise["canonical_key"] not in seen:
                    seen.add(exercise["canonical_key"])
                    out.append(exercise)
        core = day["core"]
        if core["canonical_key"] not in seen:
            seen.add(core["canonical_key"])
            out.append(core)
    return out


def resolve_images_for_program(program: Dict) -> Dict:
    query_map = exercise_query_map()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    records: List[CreditEntry] = []

    for exercise in collect_unique_exercises(program):
        key = exercise["canonical_key"]
        exercise_name = exercise["name"]
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
        if any(k in names for k in ["leg press", "squat", "split squat", "lunge"]):
            movement_hits["knee_dominant"] = True
        if any(k in names for k in ["deadlift", "hip thrust", "pull-through", "back extension", "hamstring curl"]):
            movement_hits["hinge"] = True
        if any(k in names for k in ["bench press", "chest press", "push-up", "overhead"]):
            movement_hits["horizontal_push"] = True
        if "row" in names:
            movement_hits["horizontal_pull"] = True
        if any(k in names for k in ["lat pulldown", "pull-up", "overhead"]):
            movement_hits["vertical"] = True
        if any(k in names for k in ["plank", "dead bug", "pallof", "bird dog"]):
            movement_hits["core"] = True
    if not all(4 <= n <= 6 for n in per_day_counts):
        raise ValueError("Each day must have 4-6 exercises including core.")
    if not all(movement_hits.values()):
        missing = [k for k, v in movement_hits.items() if not v]
        raise ValueError(f"Program missing movement patterns: {missing}")


def load_image_index_from_manifest(manifest: Dict) -> Dict[str, Dict]:
    return {row["canonical_key"]: row for row in manifest.get("credits", [])}


def build_html_context(program: Dict, manifest: Dict, user: str, stage: str) -> Dict:
    profile = program["profile"]
    image_index = load_image_index_from_manifest(manifest)

    day_views: List[Dict] = []
    for day_key, day in program["days"].items():
        rows = []
        for superset in day["supersets"]:
            for exercise in superset["exercises"]:
                image_path = image_index.get(exercise["canonical_key"], {}).get("image_path")
                image_uri = Path(image_path).resolve().as_uri() if image_path and Path(image_path).exists() else ""
                rows.append(
                    {
                        "name": ascii_clean(exercise["name"]),
                        "sets_reps": ascii_clean(exercise["sets_reps"]),
                        "notes": ascii_clean(f"{exercise['note']}. Alt: {exercise['alternatives']}"),
                        "image_uri": image_uri,
                    }
                )

        core = day["core"]
        core_path = image_index.get(core["canonical_key"], {}).get("image_path")
        core_uri = Path(core_path).resolve().as_uri() if core_path and Path(core_path).exists() else ""
        rows.append(
            {
                "name": ascii_clean(core["name"] + " (core)"),
                "sets_reps": ascii_clean(core["sets_reps"]),
                "notes": ascii_clean(f"{core['note']}. Alt: {core['alternatives']}"),
                "image_uri": core_uri,
            }
        )

        day_views.append(
            {
                "day_key": day_key,
                "title": ascii_clean(day["title"]),
                "warmup": ascii_clean(day["warmup"]),
                "main_work": ascii_clean(day["main_work"]),
                "finisher": ascii_clean(day["finisher"]),
                "rows": rows,
            }
        )

    return {
        "generated_for": ascii_clean(user),
        "stage": ascii_clean(stage),
        "profile": ensure_ascii_structure(profile),
        "goal": ascii_clean(program.get("goal", "general_fitness")),
        "weekly_structure": ensure_ascii_structure(program["weekly_structure"]),
        "days": day_views,
        "superset_rules": [ascii_clean(x) for x in program["superset_rules"]],
        "progression_rules": [ascii_clean(x) for x in program["progression_rules"]],
        "fat_loss_non_negotiables": [ascii_clean(x) for x in program["fat_loss_non_negotiables"]],
        "non_gym_guidance": [ascii_clean(x) for x in program["non_gym_guidance"]],
        "schedule_example": [ascii_clean(x) for x in program["schedule_example"]],
        "credits": [
            {
                "exercise": ascii_clean(row.get("exercise", "")),
                "title": ascii_clean(row.get("title", "")),
                "author": ascii_clean(row.get("author", "")),
                "source_url": ascii_clean(row.get("source_url", "")),
                "license": ascii_clean(row.get("license", "")),
            }
            for row in manifest.get("credits", [])
        ],
    }


def render_pdf_html(context: Dict, out_pdf: Path, out_html: Optional[Path]) -> None:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    template_dir = Path("templates")
    template_name = "program_pdf.html.j2"
    css_name = "program_pdf.css"

    if not template_dir.exists():
        raise FileNotFoundError("templates/ directory not found")
    css_path = template_dir / css_name
    if not css_path.exists():
        raise FileNotFoundError(f"CSS template not found: {css_path}")

    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape(("html", "xml")))
    template = env.get_template(template_name)
    css = css_path.read_text(encoding="utf-8")
    html = template.render(css=css, **context)

    if out_html:
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html, encoding="utf-8")

    cache_dir = Path(".cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.resolve()))

    if platform.system() == "Darwin":
        candidates = ["/opt/homebrew/lib", "/usr/local/lib"]
        existing = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]
        merged = []
        for path in candidates + existing:
            if path and path not in merged:
                merged.append(path)
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(merged)

    try:
        from weasyprint import HTML
    except Exception as exc:
        raise RuntimeError(
            "WeasyPrint import failed. Install weasyprint and platform libs (pango/cairo/gdk-pixbuf/glib/libffi)."
        ) from exc

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(Path.cwd())).write_pdf(str(out_pdf))


def cmd_profile_create(args) -> int:
    path = profile_path(args.user)
    if path.exists() and not args.force:
        raise FileExistsError(f"Profile already exists: {path}. Use --force to overwrite.")

    profile = default_profile(args.user)
    if args.name:
        profile["name"] = args.name
    if args.sex:
        profile["sex"] = args.sex
    if args.age is not None:
        profile["age"] = args.age
    if args.height_cm is not None:
        profile["height_cm"] = args.height_cm
    if args.weight_kg is not None:
        profile["weight_kg"] = args.weight_kg
    if args.goal:
        profile["goal"] = slugify(args.goal)
    if args.gym_days is not None:
        profile["gym_days"] = args.gym_days
    if args.session_length_minutes is not None:
        profile["session_length_minutes"] = args.session_length_minutes
    if args.equipment:
        profile["equipment"] = slugify(args.equipment)
    if args.notes:
        profile["notes"] = args.notes

    validate_profile(profile)
    write_json(path, profile)
    print(f"Created profile: {path}")
    return 0


def cmd_profile_show(args) -> int:
    path = profile_path(args.user)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}. Run profile-create first.")
    profile = read_json(path)
    print(json.dumps(profile, indent=2))
    return 0


def cmd_profile_update(args) -> int:
    path = profile_path(args.user)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}. Run profile-create first.")
    profile = read_json(path)

    for item in args.set or []:
        if "=" not in item:
            raise ValueError(f"Invalid --set value '{item}'. Use key=value.")
        key, raw = item.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            raise ValueError(f"Invalid key in --set value '{item}'.")

        if raw.isdigit():
            value = int(raw)
        else:
            try:
                value = float(raw)
                if value.is_integer():
                    value = int(value)
            except ValueError:
                value = raw
        profile[key] = value

    validate_profile(profile)
    write_json(path, profile)
    print(f"Updated profile: {path}")
    return 0


def cmd_generate_draft(args) -> int:
    p_path = profile_path(args.user)
    if not p_path.exists():
        raise FileNotFoundError(f"Profile not found: {p_path}. Run profile-create first.")
    profile = read_json(p_path)
    validate_profile(profile)

    days = args.days if args.days is not None else int(profile.get("gym_days", 3))
    goal = args.goal if args.goal else str(profile.get("goal", "general_fitness"))
    program = build_program(profile, days=days, goal=goal)
    draft_path = program_path(args.user, "draft")
    write_json(draft_path, program)
    print(f"Created draft program: {draft_path}")
    print("Review and edit this file before approval.")
    return 0


def cmd_approve_program(args) -> int:
    draft_path = program_path(args.user, "draft")
    final_path = program_path(args.user, "final")
    if not draft_path.exists():
        raise FileNotFoundError(f"Draft program not found: {draft_path}. Run generate-draft first.")

    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(draft_path, final_path)
    print(f"Approved program: {final_path}")
    return 0


def cmd_fetch_images(args) -> int:
    p_path = program_path(args.user, args.stage)
    if not p_path.exists():
        raise FileNotFoundError(f"Program not found: {p_path}")
    program = read_json(p_path)
    validate_program_constraints(program)
    manifest = resolve_images_for_program(program)
    commons_count = sum(1 for x in manifest["credits"] if x["kind"] == "commons")
    placeholder_count = sum(1 for x in manifest["credits"] if x["kind"] == "placeholder")
    print(f"Wrote {IMAGE_MANIFEST} ({commons_count} commons, {placeholder_count} placeholders).")
    return 0


def cmd_build_pdf(args) -> int:
    p_path = program_path(args.user, args.stage)
    if not p_path.exists():
        raise FileNotFoundError(f"Program not found: {p_path}")
    if not IMAGE_MANIFEST.exists():
        raise FileNotFoundError(f"{IMAGE_MANIFEST} not found. Run fetch-images first.")

    program = read_json(p_path)
    manifest = read_json(IMAGE_MANIFEST)
    validate_program_constraints(program)

    out_pdf = Path(args.out) if args.out else Path(DEFAULT_PDF_NAME)
    out_html = Path(args.html_out) if args.html_out else None
    context = build_html_context(program, manifest, user=args.user, stage=args.stage)
    render_pdf_html(context, out_pdf=out_pdf, out_html=out_html)
    print(f"Created PDF: {out_pdf}")
    if out_html:
        print(f"Wrote HTML preview: {out_html}")
    return 0


def cmd_all(args) -> int:
    cmd_generate_draft(args)
    if args.auto_approve:
        cmd_approve_program(args)
        args.stage = "final"
    else:
        args.stage = "draft"
    cmd_fetch_images(args)
    cmd_build_pdf(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal training program generator with profile + review workflow.")
    sub = parser.add_subparsers(dest="command")

    p_profile_create = sub.add_parser("profile-create", help="Create a user profile JSON.")
    p_profile_create.add_argument("--user", default="default")
    p_profile_create.add_argument("--name")
    p_profile_create.add_argument("--sex")
    p_profile_create.add_argument("--age", type=int)
    p_profile_create.add_argument("--height-cm", type=int)
    p_profile_create.add_argument("--weight-kg", type=int)
    p_profile_create.add_argument("--goal")
    p_profile_create.add_argument("--gym-days", type=int)
    p_profile_create.add_argument("--session-length-minutes", type=int)
    p_profile_create.add_argument("--equipment")
    p_profile_create.add_argument("--notes")
    p_profile_create.add_argument("--force", action="store_true")
    p_profile_create.set_defaults(func=cmd_profile_create)

    p_profile_show = sub.add_parser("profile-show", help="Print a user profile JSON.")
    p_profile_show.add_argument("--user", default="default")
    p_profile_show.set_defaults(func=cmd_profile_show)

    p_profile_update = sub.add_parser("profile-update", help="Update profile fields via --set key=value.")
    p_profile_update.add_argument("--user", default="default")
    p_profile_update.add_argument("--set", action="append", default=[])
    p_profile_update.set_defaults(func=cmd_profile_update)

    p_draft = sub.add_parser("generate-draft", help="Generate draft program from profile + goal + days.")
    p_draft.add_argument("--user", default="default")
    p_draft.add_argument("--days", type=int, choices=[2, 3, 4, 5], help="Training days per week")
    p_draft.add_argument(
        "--goal",
        choices=["fat_loss", "muscle_gain", "strength", "general_fitness"],
        help="Program objective",
    )
    p_draft.set_defaults(func=cmd_generate_draft)

    p_approve = sub.add_parser("approve-program", help="Copy draft program to final program.")
    p_approve.add_argument("--user", default="default")
    p_approve.set_defaults(func=cmd_approve_program)

    p_images = sub.add_parser("fetch-images", help="Resolve exercise images and write assets manifest.")
    p_images.add_argument("--user", default="default")
    p_images.add_argument("--stage", choices=["draft", "final"], default="final")
    p_images.set_defaults(func=cmd_fetch_images)

    p_pdf = sub.add_parser("build-pdf", help="Build beautiful PDF using HTML/CSS + WeasyPrint.")
    p_pdf.add_argument("--user", default="default")
    p_pdf.add_argument("--stage", choices=["draft", "final"], default="final")
    p_pdf.add_argument("--out", help="Output PDF path", default=DEFAULT_PDF_NAME)
    p_pdf.add_argument("--html-out", help="Optional debug HTML output path", default=DEFAULT_HTML_NAME)
    p_pdf.set_defaults(func=cmd_build_pdf)

    p_all = sub.add_parser("all", help="Quick run: generate-draft -> fetch-images -> build-pdf.")
    p_all.add_argument("--user", default="default")
    p_all.add_argument("--days", type=int, choices=[2, 3, 4, 5])
    p_all.add_argument("--goal", choices=["fat_loss", "muscle_gain", "strength", "general_fitness"])
    p_all.add_argument("--auto-approve", action="store_true", help="Auto-promote draft to final before export.")
    p_all.add_argument("--out", help="Output PDF path", default=DEFAULT_PDF_NAME)
    p_all.add_argument("--html-out", help="Optional debug HTML output path", default=DEFAULT_HTML_NAME)
    p_all.set_defaults(func=cmd_all, stage="draft")

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
