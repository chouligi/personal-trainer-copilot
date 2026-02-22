from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from src.program_io import AppPaths, read_json, slugify, write_json


@dataclass
class CreditEntry:
    canonical_key: str
    exercise: str
    title: str
    author: str
    source_url: str
    license: str
    image_path: str
    kind: str  # curated_library | missing


def load_curated_catalog(paths: AppPaths) -> dict:
    if paths.curated_catalog.exists():
        return read_json(paths.curated_catalog)
    return {"items": {}}


def save_curated_catalog(paths: AppPaths, catalog: dict) -> None:
    write_json(paths.curated_catalog, catalog)


def collect_unique_exercises(program: dict) -> list[dict]:
    out: list[dict] = []
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


def find_local_library_image(paths: AppPaths, canonical_key: str) -> Path | None:
    base = paths.image_library_dir / slugify(canonical_key)
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def resolve_images_for_program(paths: AppPaths, program: dict) -> dict:
    paths.assets_dir.mkdir(parents=True, exist_ok=True)
    paths.image_library_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_curated_catalog(paths)
    catalog_items = catalog.setdefault("items", {})

    records: list[CreditEntry] = []
    for exercise in collect_unique_exercises(program):
        key = exercise["canonical_key"]
        exercise_name = exercise["name"]

        catalog_hit = catalog_items.get(key, {})
        catalog_image_path_raw = catalog_hit.get("image_path", "")
        if catalog_hit and catalog_image_path_raw and Path(catalog_image_path_raw).exists():
            p = Path(catalog_image_path_raw)
            records.append(
                CreditEntry(
                    canonical_key=key,
                    exercise=exercise_name,
                    title=catalog_hit.get("title", f"Curated image for {exercise_name}"),
                    author=catalog_hit.get("author", "Local library"),
                    source_url=catalog_hit.get("source_url", str(p)),
                    license=catalog_hit.get("license", "Self-generated"),
                    image_path=str(p),
                    kind="curated_library",
                )
            )
            continue

        local_img = find_local_library_image(paths, key)
        if local_img is not None:
            records.append(
                CreditEntry(
                    canonical_key=key,
                    exercise=exercise_name,
                    title=f"Curated library image for {exercise_name}",
                    author="Local library",
                    source_url=str(local_img),
                    license="Self-generated",
                    image_path=str(local_img),
                    kind="curated_library",
                )
            )
            catalog_items[key] = {
                "exercise": exercise_name,
                "title": f"Curated library image for {exercise_name}",
                "author": "Local library",
                "source_url": str(local_img),
                "license": "Self-generated",
                "image_path": str(local_img),
            }
            continue

        records.append(
            CreditEntry(
                canonical_key=key,
                exercise=exercise_name,
                title=f"No curated image available for {exercise_name}",
                author="N/A",
                source_url="N/A",
                license="N/A",
                image_path="",
                kind="missing",
            )
        )

    manifest = {"credits": [asdict(x) for x in records]}
    write_json(paths.image_manifest, manifest)
    save_curated_catalog(paths, catalog)
    return manifest
