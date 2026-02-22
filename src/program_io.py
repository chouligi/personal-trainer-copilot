from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppPaths:
    root: Path
    profiles_dir: Path
    programs_dir: Path
    assets_dir: Path
    image_library_dir: Path
    image_manifest: Path
    curated_catalog: Path
    templates_dir: Path
    config_dir: Path

    def profile_path(self, user: str) -> Path:
        return self.profiles_dir / f"{slugify(user)}.json"

    def program_path(self, user: str, stage: str) -> Path:
        return self.programs_dir / f"{slugify(user)}_{stage}.json"


ASCII_REPLACEMENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u00a0": " ",
}


def get_paths(root: Path | None = None) -> AppPaths:
    base = (root or Path.cwd()).resolve()
    assets = base / "assets"
    return AppPaths(
        root=base,
        profiles_dir=base / "profiles",
        programs_dir=base / "programs",
        assets_dir=assets,
        image_library_dir=assets / "exercise_library",
        image_manifest=assets / "image_manifest.json",
        curated_catalog=assets / "curated_image_catalog.json",
        templates_dir=base / "templates",
        config_dir=base / "config",
    )


def ascii_clean(value: str) -> str:
    out = value
    for bad, good in ASCII_REPLACEMENTS.items():
        out = out.replace(bad, good)
    return out.encode("ascii", errors="ignore").decode("ascii")


def slugify(value: str) -> str:
    text = ascii_clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "item"


def ensure_ascii_structure(data: Any) -> Any:
    if isinstance(data, dict):
        return {ascii_clean(str(k)): ensure_ascii_structure(v) for k, v in data.items()}
    if isinstance(data, list):
        return [ensure_ascii_structure(x) for x in data]
    if isinstance(data, str):
        return ascii_clean(data)
    return data


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(ensure_ascii_structure(payload), handle, indent=2)


def load_program_templates(paths: AppPaths) -> dict:
    path = paths.config_dir / "program_templates.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    return read_json(path)


def load_progression_rules(paths: AppPaths) -> dict:
    path = paths.config_dir / "progression_rules.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    return read_json(path)
