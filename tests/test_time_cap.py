from src.time_cap import enforce_session_duration_cap, estimate_day_duration_minutes


def _program():
    return {
        "profile": {"session_length_minutes": 40},
        "days": {
            "A": {
                "title": "Day A",
                "supersets": [
                    {"exercises": [{"sets_reps": "4 x 6-8"}, {"sets_reps": "4 x 6-8"}]},
                    {"exercises": [{"sets_reps": "4 x 8-10"}, {"sets_reps": "4 x 8-10"}]},
                ],
                "core": {"sets_reps": "3 x 12"},
                "finisher": "Optional",
            }
        },
    }


def test_enforce_time_cap():
    program = _program()
    enforce_session_duration_cap(program)
    assert program["session_cap_minutes"] == 40
    assert estimate_day_duration_minutes(program["days"]["A"]) <= 40
