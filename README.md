# Personal Trainer Copilot - Program Generator

This project now supports a review-first workflow:

1. Create/update a user profile
2. Generate a draft program based on goal + days
3. Review/edit the draft JSON
4. Approve the draft as final
5. Resolve exercise images + render a polished PDF (HTML/CSS via WeasyPrint)

## Files

- `generate_program.py` - CLI entrypoint
- `profiles/<user>.json` - user profiles
- `programs/<user>_draft.json` - editable draft
- `programs/<user>_final.json` - approved final program
- `assets/image_manifest.json` - image metadata and credits
- `templates/program_pdf.html.j2` - PDF HTML template
- `templates/program_pdf.css` - PDF styles

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Note: WeasyPrint may require OS libraries (pango/cairo/gdk-pixbuf/glib/libffi), depending on your machine.

## Workflow

### 1) Create profile

```bash
python generate_program.py profile-create --user fosa --name "Fosa" --goal fat_loss --gym-days 4
```

### 2) Generate draft

```bash
python generate_program.py generate-draft --user fosa --days 4 --goal fat_loss
```

Review/edit `programs/fosa_draft.json`.

### 3) Approve final

```bash
python generate_program.py approve-program --user fosa
```

### 4) Resolve images

```bash
python generate_program.py fetch-images --user fosa --stage final
```

### 5) Build PDF

```bash
python generate_program.py build-pdf --user fosa --stage final --out fosa_program.pdf --html-out fosa_program.html
```

## Fast path

Run everything in one go (not ideal if you want manual review):

```bash
python generate_program.py all --user fosa --days 4 --goal fat_loss --auto-approve --out fosa_program.pdf
```
