from __future__ import annotations

from typing import Any

from src.program_io import AppPaths, slugify, write_json, read_json


REQUIRED_PROFILE_FIELDS = [
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


def default_profile(user: str) -> dict:
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


def validate_profile(profile: dict) -> None:
    missing = [k for k in REQUIRED_PROFILE_FIELDS if k not in profile]
    if missing:
        raise ValueError(f"Profile missing fields: {missing}")
    gym_days = int(profile["gym_days"])
    if gym_days < 2 or gym_days > 5:
        raise ValueError("gym_days must be between 2 and 5")
    if int(profile["session_length_minutes"]) <= 0:
        raise ValueError("session_length_minutes must be > 0")


def create_profile(paths: AppPaths, user: str, overrides: dict[str, Any], force: bool = False) -> dict:
    path = paths.profile_path(user)
    if path.exists() and not force:
        raise FileExistsError(f"Profile already exists: {path}. Use --force to overwrite.")
    profile = default_profile(user)
    profile.update({k: v for k, v in overrides.items() if v is not None})
    if "goal" in profile:
        profile["goal"] = slugify(str(profile["goal"]))
    if "equipment" in profile:
        profile["equipment"] = slugify(str(profile["equipment"]))
    validate_profile(profile)
    write_json(path, profile)
    return profile


def load_profile(paths: AppPaths, user: str) -> dict:
    path = paths.profile_path(user)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}. Run profile-create first.")
    profile = read_json(path)
    validate_profile(profile)
    return profile


def update_profile(paths: AppPaths, user: str, updates: dict[str, Any]) -> dict:
    profile = load_profile(paths, user)
    profile.update(updates)
    validate_profile(profile)
    write_json(paths.profile_path(user), profile)
    return profile
