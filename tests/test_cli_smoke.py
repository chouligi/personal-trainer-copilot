from generate_program import build_parser


def test_cli_has_expected_commands():
    parser = build_parser()
    sub = [a for a in parser._actions if getattr(a, 'choices', None)]
    assert sub, 'Expected subcommands action'
    commands = set(sub[0].choices.keys())
    expected = {
        'profile-create',
        'profile-show',
        'profile-update',
        'generate-draft',
        'approve-program',
        'fetch-images',
        'build-pdf',
        'all',
    }
    assert expected.issubset(commands)


def test_build_pdf_style_flag_is_supported():
    parser = build_parser()
    args = parser.parse_args(["build-pdf"])
    assert args.style == "modern"
    args = parser.parse_args(["build-pdf", "--style", "future_theme"])
    assert args.style == "future_theme"
