from src.profile_service import default_profile, validate_profile


def test_default_profile_is_valid():
    profile = default_profile("alice")
    validate_profile(profile)
    assert profile["user_id"] == "alice"


def test_profile_requires_fields():
    profile = default_profile("bob")
    del profile["goal"]
    try:
        validate_profile(profile)
    except ValueError as exc:
        assert "missing fields" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError")
