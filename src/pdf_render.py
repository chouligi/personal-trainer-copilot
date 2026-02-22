from __future__ import annotations

import os
import platform
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.program_io import AppPaths, ascii_clean
from src.time_cap import estimate_day_duration_minutes

THEME_FILES: dict[str, tuple[str, str]] = {
    "modern": ("program_pdf.html.j2", "program_pdf.css"),
}


def load_image_index_from_manifest(manifest: dict) -> dict[str, dict]:
    return {row["canonical_key"]: row for row in manifest.get("credits", [])}


def _split_sets_reps(sets_reps: str) -> tuple[str, str]:
    text = (sets_reps or "").strip()
    if "x" not in text:
        return text, ""
    parts = [p.strip() for p in text.replace("X", "x").split("x", 1)]
    if len(parts) != 2:
        return text, ""
    return parts[0], parts[1]


def _build_exercise_view(exercise: dict, image_index: dict[str, dict], pair_code: str, suffix: str = "") -> dict:
    image_path = image_index.get(exercise["canonical_key"], {}).get("image_path")
    image_uri = Path(image_path).resolve().as_uri() if image_path and Path(image_path).exists() else ""
    sets, reps = _split_sets_reps(exercise["sets_reps"])
    label = exercise["name"] + suffix if suffix else exercise["name"]
    pair_label = pair_code
    if pair_code.startswith("S") and "." in pair_code:
        superset_number, exercise_number = pair_code[1:].split(".", 1)
        if exercise_number.isdigit():
            idx = int(exercise_number)
            if 1 <= idx <= 26:
                pair_label = f"{superset_number}{chr(64 + idx)}"
    return {
        "kind": "exercise",
        "pair_code": pair_code,
        "pair_label": pair_label,
        "name": ascii_clean(label),
        "sets_reps": ascii_clean(exercise["sets_reps"]),
        "sets": ascii_clean(sets),
        "reps": ascii_clean(reps),
        "notes": ascii_clean(f"{exercise['note']}. Alt: {exercise['alternatives']}"),
        "image_uri": image_uri,
        "has_image": bool(image_uri),
    }


def build_html_context(program: dict, manifest: dict, user: str) -> dict:
    profile = program["profile"]
    image_index = load_image_index_from_manifest(manifest)

    day_views: list[dict] = []
    for day_key, day in program["days"].items():
        rows: list[dict] = []
        superset_blocks: list[dict] = []
        for superset_idx, superset in enumerate(day["supersets"], start=1):
            rows.append(
                {
                    "kind": "superset_header",
                    "label": f"Superset {superset_idx}",
                    "instruction": "Alternate Exercise 1 and Exercise 2 each round.",
                }
            )
            superset_exercises: list[dict] = []
            for exercise_idx, exercise in enumerate(superset["exercises"], start=1):
                exercise_view = _build_exercise_view(
                    exercise,
                    image_index=image_index,
                    pair_code=f"S{superset_idx}.{exercise_idx}",
                )
                rows.append(exercise_view)
                superset_exercises.append(exercise_view)
            superset_blocks.append(
                {
                    "label": f"Superset {superset_idx}",
                    "instruction": "Perform Exercise 1A, then 1B. Rest 45-75 sec after both are done.",
                    "exercises": superset_exercises,
                }
            )

        core = day["core"]
        core_view = _build_exercise_view(core, image_index=image_index, pair_code="Core", suffix=" (core)")
        rows.append(core_view)

        day_views.append(
            {
                "day_key": day_key,
                "title": ascii_clean(day["title"]),
                "warmup": ascii_clean(day["warmup"]),
                "main_work": ascii_clean(day["main_work"]),
                "finisher": ascii_clean(day["finisher"]),
                "estimated_duration_min": int(day.get("estimated_duration_min") or estimate_day_duration_minutes(day)),
                "rows": rows,
                "superset_blocks": superset_blocks,
                "core": core_view,
            }
        )

    return {
        "generated_for": ascii_clean(user),
        "profile": profile,
        "goal": ascii_clean(program.get("goal", "general_fitness")),
        "session_cap_minutes": int(program.get("session_cap_minutes") or profile.get("session_length_minutes", 40)),
        "weekly_structure": program["weekly_structure"],
        "days": day_views,
        "superset_rules": [ascii_clean(x) for x in program["superset_rules"]],
        "progression_rules": [ascii_clean(x) for x in program["progression_rules"]],
        "fat_loss_non_negotiables": [ascii_clean(x) for x in program["fat_loss_non_negotiables"]],
        "non_gym_guidance": [ascii_clean(x) for x in program["non_gym_guidance"]],
        "schedule_example": [ascii_clean(x) for x in program["schedule_example"]],
    }


def render_pdf_html(paths: AppPaths, context: dict, out_pdf: Path, out_html: Path | None, style: str = "modern") -> None:
    style_key = (style or "modern").strip().lower()
    if style_key not in THEME_FILES:
        supported = ", ".join(sorted(THEME_FILES.keys()))
        raise ValueError(f"Unsupported style '{style}'. Supported values: {supported}.")

    template_name, css_name = THEME_FILES[style_key]

    if not paths.templates_dir.exists():
        raise FileNotFoundError("templates/ directory not found")
    css_path = paths.templates_dir / css_name
    if not css_path.exists():
        raise FileNotFoundError(f"CSS template not found: {css_path}")

    env = Environment(
        loader=FileSystemLoader(str(paths.templates_dir)),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = env.get_template(template_name)
    css = css_path.read_text(encoding="utf-8")
    html = template.render(css=css, **context)

    if out_html:
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html, encoding="utf-8")

    cache_dir = paths.root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.resolve()))

    if platform.system() == "Darwin":
        candidates = ["/opt/homebrew/lib", "/usr/local/lib"]
        existing = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]
        merged: list[str] = []
        for p in candidates + existing:
            if p and p not in merged:
                merged.append(p)
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(merged)

    try:
        from weasyprint import HTML
    except Exception as exc:
        raise RuntimeError(
            "WeasyPrint import failed. Install weasyprint and platform libs (pango/cairo/gdk-pixbuf/glib/libffi)."
        ) from exc

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(paths.root)).write_pdf(str(out_pdf))
