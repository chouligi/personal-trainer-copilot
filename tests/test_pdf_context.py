from src.pdf_render import build_html_context


def test_context_handles_missing_images():
    program = {
        "profile": {
            "name": "Fosa",
            "age": 35,
            "height_cm": 183,
            "weight_kg": 85,
            "experience_level": "intermediate",
            "session_length_minutes": 40,
        },
        "goal": "fat_loss",
        "weekly_structure": {"warmup": "w", "main": "m", "finisher": "f"},
        "session_cap_minutes": 40,
        "superset_rules": ["r1"],
        "progression_rules": ["r2"],
        "fat_loss_non_negotiables": ["n1"],
        "non_gym_guidance": ["g1"],
        "schedule_example": ["s1"],
        "days": {
            "A": {
                "title": "Day A",
                "warmup": "WU",
                "main_work": "MAIN",
                "finisher": "FIN",
                "estimated_duration_min": 34,
                "supersets": [{"exercises": [{"name": "Leg Press", "sets_reps": "3 x 8", "note": "n", "alternatives": "a", "canonical_key": "leg_press"}]}],
                "core": {"name": "Front Plank", "sets_reps": "2 x 30s", "note": "n", "alternatives": "a", "canonical_key": "front_plank"},
            }
        },
    }
    manifest = {"credits": [{"canonical_key": "leg_press", "image_path": "", "kind": "missing"}]}

    ctx = build_html_context(program, manifest, user="fosa", stage="final")
    assert ctx["days"][0]["rows"][0]["image_uri"] == ""
    assert "credits" not in ctx
