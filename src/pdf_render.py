from __future__ import annotations

import os
import platform
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.program_io import AppPaths, ascii_clean
from src.time_cap import estimate_day_duration_minutes


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


def build_html_context(program: dict, manifest: dict, user: str) -> dict:
    profile = program["profile"]
    image_index = load_image_index_from_manifest(manifest)

    day_views: list[dict] = []
    for day_key, day in program["days"].items():
        rows: list[dict] = []
        for superset_idx, superset in enumerate(day["supersets"], start=1):
            rows.append(
                {
                    "kind": "superset_header",
                    "label": f"Superset {superset_idx}",
                    "instruction": "Alternate Exercise 1 and Exercise 2 each round.",
                }
            )
            for exercise_idx, exercise in enumerate(superset["exercises"], start=1):
                image_path = image_index.get(exercise["canonical_key"], {}).get("image_path")
                image_uri = Path(image_path).resolve().as_uri() if image_path and Path(image_path).exists() else ""
                sets, reps = _split_sets_reps(exercise["sets_reps"])
                rows.append(
                    {
                        "kind": "exercise",
                        "pair_code": f"S{superset_idx}.{exercise_idx}",
                        "name": ascii_clean(exercise["name"]),
                        "sets_reps": ascii_clean(exercise["sets_reps"]),
                        "sets": ascii_clean(sets),
                        "reps": ascii_clean(reps),
                        "notes": ascii_clean(f"{exercise['note']}. Alt: {exercise['alternatives']}"),
                        "image_uri": image_uri,
                    }
                )

        core = day["core"]
        core_path = image_index.get(core["canonical_key"], {}).get("image_path")
        core_uri = Path(core_path).resolve().as_uri() if core_path and Path(core_path).exists() else ""
        core_sets, core_reps = _split_sets_reps(core["sets_reps"])
        rows.append(
            {
                "kind": "exercise",
                "pair_code": "Core",
                "name": ascii_clean(core["name"] + " (core)"),
                "sets_reps": ascii_clean(core["sets_reps"]),
                "sets": ascii_clean(core_sets),
                "reps": ascii_clean(core_reps),
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
                "estimated_duration_min": int(day.get("estimated_duration_min") or estimate_day_duration_minutes(day)),
                "rows": rows,
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


def render_pdf_html(paths: AppPaths, context: dict, out_pdf: Path, out_html: Path | None) -> None:
    template_name = "program_pdf.html.j2"
    css_name = "program_pdf.css"

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
