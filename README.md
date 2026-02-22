# Personal Trainer Copilot - Program Generator

This project supports a review-first workflow with local-only curated images.

## Key Principles

- Program generation is config-driven (`config/*.json`), not hardcoded in Python.
- Exercise images are local-only from `assets/exercise_library`.
- PDF rendering is HTML/CSS based via WeasyPrint.

## Files

- `generate_program.py` - CLI entrypoint (thin wrapper)
- `src/` - modular services (`program_io`, `profile_service`, `program_builder`, `time_cap`, `image_library`, `pdf_render`)
- `config/program_templates.json` - day templates
- `config/progression_rules.json` - goal progression rules
- `profiles/<user>.json` - user profiles
- `programs/<user>_draft.json` - editable draft
- `programs/<user>_final.json` - approved final program
- `assets/exercise_library/` - curated exercise images (`<canonical_key>.<ext>`)
- `assets/image_manifest.json` - resolved local image manifest
- `templates/program_pdf.html.j2` - PDF HTML template
- `templates/program_pdf.css` - PDF styles

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Workflow

### 1) Create profile

```bash
python generate_program.py profile-create --user fosa --name "Fosa" --goal fat_loss --gym-days 3
```

### 2) Generate draft

```bash
python generate_program.py generate-draft --user fosa --days 3 --goal fat_loss
```

Review/edit `programs/fosa_draft.json`.

### 3) Approve final

```bash
python generate_program.py approve-program --user fosa
```

### 4) Add local images

Place images in:

- `assets/exercise_library/<canonical_key>.jpg`
- `assets/exercise_library/<canonical_key>.jpeg`
- `assets/exercise_library/<canonical_key>.png`
- `assets/exercise_library/<canonical_key>.webp`

No web image downloading is performed.

### 5) Resolve image manifest

```bash
python generate_program.py fetch-images --user fosa --stage final --allow-missing-images
```

### 6) Build PDF

```bash
python generate_program.py build-pdf --user fosa --stage final --allow-missing-images --out fosa_program.pdf --html-out fosa_program.html
```

## Tests

```bash
pytest -q
```
