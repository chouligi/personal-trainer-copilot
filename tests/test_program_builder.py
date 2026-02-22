from src.program_builder import build_program
from src.program_io import get_paths
from src.profile_service import default_profile


def test_build_program_from_config():
    paths = get_paths()
    profile = default_profile("tester")
    program = build_program(paths, profile=profile, days=3, goal="fat_loss")
    assert len(program["days"]) == 3
    assert program["goal"] == "fat_loss"
    assert "session_cap_minutes" in program
