from pathlib import Path

from src.image_library import resolve_images_for_program
from src.program_io import get_paths


def test_local_only_resolution(tmp_path: Path):
    paths = get_paths(tmp_path)
    paths.image_library_dir.mkdir(parents=True, exist_ok=True)

    # Provide one local image and keep one missing.
    (paths.image_library_dir / "leg_press.png").write_bytes(b"fake")

    program = {
        "days": {
            "A": {
                "supersets": [
                    {
                        "exercises": [
                            {"name": "Leg Press", "canonical_key": "leg_press"},
                            {"name": "Bench Press", "canonical_key": "barbell_bench_press"},
                        ]
                    }
                ],
                "core": {"name": "Front Plank", "canonical_key": "front_plank"},
            }
        }
    }

    manifest = resolve_images_for_program(paths, program)
    kinds = {row["canonical_key"]: row["kind"] for row in manifest["credits"]}
    assert kinds["leg_press"] == "curated_library"
    assert kinds["barbell_bench_press"] == "missing"
    assert kinds["front_plank"] == "missing"
