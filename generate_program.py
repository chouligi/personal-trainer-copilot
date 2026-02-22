#!/usr/bin/env python3
"""CLI entrypoint for profile/program/image/PDF workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from src.image_library import collect_unique_exercises, load_curated_catalog, resolve_images_for_program, save_curated_catalog
from src.pdf_render import build_html_context, render_pdf_html
from src.profile_service import create_profile, default_profile, load_profile, update_profile, validate_profile
from src.program_builder import build_program, validate_program_constraints
from src.program_io import get_paths, read_json, slugify, write_json

DEFAULT_PDF_NAME = "program_report.pdf"
DEFAULT_HTML_NAME = "program_report.html"


def _coerce_set_value(raw: str) -> Any:
    text = raw.strip()
    if text.isdigit():
        return int(text)
    try:
        val = float(text)
        return int(val) if val.is_integer() else val
    except ValueError:
        return text


def cmd_profile_create(args) -> int:
    paths = get_paths()
    overrides = {
        "name": args.name,
        "sex": args.sex,
        "age": args.age,
        "height_cm": args.height_cm,
        "weight_kg": args.weight_kg,
        "goal": args.goal,
        "gym_days": args.gym_days,
        "session_length_minutes": args.session_length_minutes,
        "equipment": args.equipment,
        "notes": args.notes,
    }
    create_profile(paths, args.user, overrides, force=args.force)
    print(f"Created profile: {paths.profile_path(args.user)}")
    return 0


def cmd_profile_show(args) -> int:
    paths = get_paths()
    profile = load_profile(paths, args.user)
    print(json.dumps(profile, indent=2))
    return 0


def cmd_profile_update(args) -> int:
    paths = get_paths()
    updates: dict[str, Any] = {}
    for item in args.set or []:
        if "=" not in item:
            raise ValueError(f"Invalid --set value '{item}'. Use key=value.")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid key in --set value '{item}'.")
        updates[key] = _coerce_set_value(raw)

    update_profile(paths, args.user, updates)
    print(f"Updated profile: {paths.profile_path(args.user)}")
    return 0


def cmd_generate_draft(args) -> int:
    paths = get_paths()
    profile_file = paths.profile_path(args.user)
    if not profile_file.exists():
        profile = default_profile(args.user)
        validate_profile(profile)
        write_json(profile_file, profile)
        print(f"Profile not found. Created default profile: {profile_file}")

    profile = load_profile(paths, args.user)
    days = args.days if args.days is not None else int(profile.get("gym_days", 3))
    goal = args.goal if args.goal else str(profile.get("goal", "general_fitness"))

    program = build_program(paths, profile=profile, days=days, goal=goal)
    draft_path = paths.program_path(args.user, "draft")
    write_json(draft_path, program)
    print(f"Created draft program: {draft_path}")
    print("Review and edit this file before approval.")
    return 0


def cmd_approve_program(args) -> int:
    paths = get_paths()
    draft_path = paths.program_path(args.user, "draft")
    final_path = paths.program_path(args.user, "final")
    if not draft_path.exists():
        raise FileNotFoundError(f"Draft program not found: {draft_path}. Run generate-draft first.")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(draft_path, final_path)
    print(f"Approved program: {final_path}")
    return 0


def _refresh_program_images(paths, program: dict) -> None:
    catalog = load_curated_catalog(paths)
    items = catalog.setdefault("items", {})
    for exercise in collect_unique_exercises(program):
        key = exercise["canonical_key"]
        base = paths.image_library_dir / slugify(key)
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            p = base.with_suffix(ext)
            if p.exists():
                p.unlink()
        if key in items:
            del items[key]
    save_curated_catalog(paths, catalog)


def cmd_fetch_images(args) -> int:
    paths = get_paths()
    program_path = paths.program_path(args.user, args.stage)
    if not program_path.exists():
        raise FileNotFoundError(f"Program not found: {program_path}")

    program = read_json(program_path)
    validate_program_constraints(program)

    if args.refresh_program_images:
        _refresh_program_images(paths, program)

    manifest = resolve_images_for_program(paths, program)
    curated_count = sum(1 for x in manifest["credits"] if x["kind"] == "curated_library")
    missing = [x for x in manifest["credits"] if x["kind"] == "missing"]
    print(f"Wrote {paths.image_manifest} ({curated_count} curated library, {len(missing)} missing).")
    if missing:
        print("Missing images:", ", ".join(x["canonical_key"] for x in missing))
        if not args.allow_missing_images:
            raise RuntimeError("Missing exercise images detected. Add curated images and rerun fetch-images.")
    return 0


def cmd_build_pdf(args) -> int:
    paths = get_paths()
    program_path = paths.program_path(args.user, args.stage)
    if not program_path.exists():
        raise FileNotFoundError(f"Program not found: {program_path}")
    if not paths.image_manifest.exists():
        raise FileNotFoundError(f"{paths.image_manifest} not found. Run fetch-images first.")

    program = read_json(program_path)
    manifest = read_json(paths.image_manifest)
    validate_program_constraints(program)

    missing = [x for x in manifest.get("credits", []) if x.get("kind") == "missing"]
    if missing and not args.allow_missing_images:
        missing_keys = ", ".join(x.get("canonical_key", "unknown") for x in missing)
        raise RuntimeError(
            f"Cannot build PDF with missing exercise images: {missing_keys}. "
            "Curate images first or pass --allow-missing-images."
        )

    out_pdf = Path(args.out) if args.out else Path(DEFAULT_PDF_NAME)
    out_html = Path(args.html_out) if args.html_out else None

    context = build_html_context(program, manifest, user=args.user)
    render_pdf_html(paths, context=context, out_pdf=out_pdf, out_html=out_html)

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
    p_draft.add_argument("--goal", choices=["fat_loss", "muscle_gain", "strength", "general_fitness"])
    p_draft.set_defaults(func=cmd_generate_draft)

    p_approve = sub.add_parser("approve-program", help="Copy draft program to final program.")
    p_approve.add_argument("--user", default="default")
    p_approve.set_defaults(func=cmd_approve_program)

    p_images = sub.add_parser("fetch-images", help="Resolve exercise images from local library only.")
    p_images.add_argument("--user", default="default")
    p_images.add_argument("--stage", choices=["draft", "final"], default="final")
    p_images.add_argument("--allow-missing-images", action="store_true")
    p_images.add_argument(
        "--refresh-program-images",
        action="store_true",
        help="Delete cached library images for this program's exercise keys before resolving.",
    )
    p_images.set_defaults(func=cmd_fetch_images)

    p_pdf = sub.add_parser("build-pdf", help="Build polished PDF using HTML/CSS + WeasyPrint.")
    p_pdf.add_argument("--user", default="default")
    p_pdf.add_argument("--stage", choices=["draft", "final"], default="final")
    p_pdf.add_argument("--out", default=DEFAULT_PDF_NAME)
    p_pdf.add_argument("--html-out", default=DEFAULT_HTML_NAME)
    p_pdf.add_argument("--allow-missing-images", action="store_true")
    p_pdf.set_defaults(func=cmd_build_pdf)

    p_all = sub.add_parser("all", help="Quick run: generate-draft -> fetch-images -> build-pdf.")
    p_all.add_argument("--user", default="default")
    p_all.add_argument("--days", type=int, choices=[2, 3, 4, 5])
    p_all.add_argument("--goal", choices=["fat_loss", "muscle_gain", "strength", "general_fitness"])
    p_all.add_argument("--auto-approve", action="store_true")
    p_all.add_argument("--out", default=DEFAULT_PDF_NAME)
    p_all.add_argument("--html-out", default=DEFAULT_HTML_NAME)
    p_all.add_argument("--allow-missing-images", action="store_true")
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
