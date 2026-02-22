from __future__ import annotations

import re


def parse_set_count(sets_reps: str, default: int = 3) -> int:
    match = re.match(r"^\s*(\d+)\s*x\s*.+$", (sets_reps or "").strip(), flags=re.IGNORECASE)
    if not match:
        return default
    return int(match.group(1))


def replace_set_count(sets_reps: str, new_sets: int) -> str:
    text = (sets_reps or "").strip()
    match = re.match(r"^\s*\d+\s*x\s*(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return text
    return f"{new_sets} x {match.group(1)}"


def estimate_day_duration_minutes(day: dict) -> int:
    # Heuristic: first-lift ramp-up is included in this budget.
    minutes = 5.0
    for superset in day.get("supersets", []):
        set_counts = [parse_set_count(ex.get("sets_reps", "3 x 8-12")) for ex in superset.get("exercises", [])]
        rounds = max(set_counts) if set_counts else 3
        minutes += rounds * 3.5
    core_sets = parse_set_count(day.get("core", {}).get("sets_reps", "2 x 10-12"), default=2)
    minutes += (core_sets * 1.5) + 1.0
    minutes += 4.0
    return int(round(minutes))


def enforce_session_duration_cap(program: dict) -> None:
    cap = int(program.get("profile", {}).get("session_length_minutes", 40))
    if cap <= 0:
        cap = 40

    for day in program.get("days", {}).values():
        while estimate_day_duration_minutes(day) > cap:
            changed = False
            for superset in reversed(day.get("supersets", [])):
                for exercise in superset.get("exercises", []):
                    current_sets = parse_set_count(exercise.get("sets_reps", "3 x 8-12"))
                    if current_sets > 2:
                        exercise["sets_reps"] = replace_set_count(exercise["sets_reps"], current_sets - 1)
                        changed = True
                        break
                if changed:
                    break
            if changed:
                continue

            core = day.get("core", {})
            core_sets = parse_set_count(core.get("sets_reps", "2 x 10-12"), default=2)
            if core_sets > 1:
                core["sets_reps"] = replace_set_count(core["sets_reps"], core_sets - 1)
                continue

            if day.get("finisher"):
                day["finisher"] = f"Skip finisher when session time is capped at {cap} minutes."
                break

            raise ValueError(f"Could not fit session within {cap} minutes: {day.get('title', 'day')}")

        day["estimated_duration_min"] = estimate_day_duration_minutes(day)

    program["session_cap_minutes"] = cap
