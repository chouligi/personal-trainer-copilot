from __future__ import annotations

from copy import deepcopy

from src.program_io import AppPaths, load_evidence_sources, load_program_templates, load_progression_rules
from src.time_cap import enforce_session_duration_cap, estimate_day_duration_minutes


MOVEMENT_KEYWORDS = {
    "knee_dominant": ["leg press", "squat", "split squat", "lunge"],
    "hinge": ["deadlift", "hip thrust", "pull-through", "back extension", "hamstring curl"],
    "horizontal_push": ["bench press", "chest press", "push-up", "overhead"],
    "horizontal_pull": ["row"],
    "vertical": ["lat pulldown", "pull-up", "overhead"],
    "core": ["plank", "dead bug", "pallof", "bird dog"],
}


def validate_templates_config(config: dict) -> None:
    if "days" not in config or not isinstance(config["days"], list):
        raise ValueError("config/program_templates.json must contain 'days' list")
    if "defaults" not in config or not isinstance(config["defaults"], dict):
        raise ValueError("config/program_templates.json must contain 'defaults' object")
    for day in config["days"]:
        for field in ["key", "title", "warmup", "main_work", "supersets", "core", "finisher"]:
            if field not in day:
                raise ValueError(f"Day template missing field '{field}'")
        for superset in day["supersets"]:
            if "exercises" not in superset:
                raise ValueError("Superset template missing 'exercises'")
            for exercise in superset["exercises"]:
                for ef in ["name", "sets_reps", "note", "canonical_key", "alternatives"]:
                    if ef not in exercise:
                        raise ValueError(f"Exercise missing field '{ef}'")
        core = day["core"]
        for ef in ["name", "sets_reps", "note", "canonical_key", "alternatives"]:
            if ef not in core:
                raise ValueError(f"Core exercise missing field '{ef}'")


def validate_progression_config(config: dict) -> None:
    if "goal_profiles" not in config or not isinstance(config["goal_profiles"], dict):
        raise ValueError("config/progression_rules.json must contain 'goal_profiles' object")


def validate_evidence_sources_config(config: dict) -> None:
    sources = config.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("config/evidence_sources.json must contain non-empty 'sources' object")
    for source_id, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError(f"Evidence source '{source_id}' must be an object")
        for field in ["title", "organization", "year", "url", "role", "use_for", "do_not_use_for", "last_verified"]:
            if field not in source:
                raise ValueError(f"Evidence source '{source_id}' missing field '{field}'")


def _collect_source_ids(value) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, child in value.items():
            if key in {"source_ids", "evidence_ids"}:
                found.update(str(item) for item in child if isinstance(child, list))
            else:
                found.update(_collect_source_ids(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(_collect_source_ids(item))
        return found
    return set()


def validate_source_references(source_ids: set[str], evidence_cfg: dict) -> None:
    known = set(evidence_cfg.get("sources", {}).keys())
    missing = sorted(source_ids - known)
    if missing:
        raise ValueError(f"Unknown evidence source ids referenced by config: {missing}")


def build_source_summary(source_ids: set[str], evidence_cfg: dict) -> list[dict]:
    sources = evidence_cfg.get("sources", {})
    summary = []
    for source_id in sorted(source_ids):
        source = sources[source_id]
        summary.append(
            {
                "id": source_id,
                "title": source["title"],
                "organization": source["organization"],
                "year": source["year"],
                "url": source["url"],
                "role": source["role"],
                "last_verified": source["last_verified"],
            }
        )
    return summary


def resolve_goal_key(goal: str, progression_cfg: dict) -> str:
    key = (goal or "").strip().lower().replace("-", "_").replace(" ", "_")
    profiles = progression_cfg["goal_profiles"]
    if key in profiles:
        return key
    aliases = progression_cfg.get("goal_aliases", {})
    if key in aliases and aliases[key] in profiles:
        return aliases[key]
    return progression_cfg.get("default_goal", "general_fitness")


def apply_goal_rules(program: dict, progression_cfg: dict, goal: str) -> None:
    resolved = resolve_goal_key(goal, progression_cfg)
    gp = progression_cfg["goal_profiles"][resolved]

    for day in program["days"].values():
        for idx, superset in enumerate(day["supersets"]):
            scheme = gp["first_pair"] if idx == 0 else gp["second_pair"]
            for exercise in superset["exercises"]:
                exercise["sets_reps"] = scheme
        day["core"]["sets_reps"] = gp["core_scheme"]
        day["finisher"] = gp["finisher"]

    program["goal"] = resolved


def validate_program_constraints(program: dict) -> None:
    per_day_counts = []
    movement_hits = {k: False for k in MOVEMENT_KEYWORDS}

    for day in program["days"].values():
        count = sum(len(ss["exercises"]) for ss in day["supersets"]) + 1
        per_day_counts.append(count)

        names = " ".join(
            ex["name"].lower() for ss in day["supersets"] for ex in ss["exercises"]
        ) + " " + day["core"]["name"].lower()

        for key, keywords in MOVEMENT_KEYWORDS.items():
            if any(kw in names for kw in keywords):
                movement_hits[key] = True

    if not all(4 <= n <= 6 for n in per_day_counts):
        raise ValueError("Each day must have 4-6 exercises including core.")

    if not all(movement_hits.values()):
        missing = [k for k, v in movement_hits.items() if not v]
        raise ValueError(f"Program missing movement patterns: {missing}")

    cap = int(program.get("session_cap_minutes") or program.get("profile", {}).get("session_length_minutes", 0) or 0)
    if cap > 0:
        for day in program.get("days", {}).values():
            estimate = int(day.get("estimated_duration_min") or estimate_day_duration_minutes(day))
            if estimate > cap:
                raise ValueError(f"{day.get('title', 'day')} estimated at {estimate} min, exceeds cap {cap} min.")


def build_program(paths: AppPaths, profile: dict, days: int, goal: str) -> dict:
    templates_cfg = load_program_templates(paths)
    progression_cfg = load_progression_rules(paths)
    evidence_cfg = load_evidence_sources(paths)
    validate_templates_config(templates_cfg)
    validate_progression_config(progression_cfg)
    validate_evidence_sources_config(evidence_cfg)
    source_ids = _collect_source_ids(templates_cfg) | _collect_source_ids(progression_cfg)
    validate_source_references(source_ids, evidence_cfg)

    selected_days = templates_cfg["days"][:days]
    program_days = {
        d["key"]: {
            "title": d["title"],
            "warmup": d["warmup"],
            "main_work": d["main_work"],
            "supersets": deepcopy(d["supersets"]),
            "core": deepcopy(d["core"]),
            "finisher": d["finisher"],
        }
        for d in selected_days
    }

    defaults = deepcopy(templates_cfg["defaults"])
    program = {
        "profile": deepcopy(profile),
        "goal": goal,
        "weekly_structure": defaults["weekly_structure"],
        "days": program_days,
        "substitution_map": defaults["substitution_map"],
        "superset_rules": defaults["superset_rules"],
        "progression_rules": progression_cfg.get("progression_rules", []),
        "non_gym_guidance": defaults["non_gym_guidance"],
        "fat_loss_non_negotiables": defaults["fat_loss_non_negotiables"],
        "schedule_example": [f"Day {k}: training" for k in program_days.keys()],
        "source_ids": sorted(source_ids),
        "sources": build_source_summary(source_ids, evidence_cfg),
    }

    apply_goal_rules(program, progression_cfg, goal)
    enforce_session_duration_cap(program)
    validate_program_constraints(program)
    return program
