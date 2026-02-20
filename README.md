# 3-Day Gym Program Generator (Modular Workflow)

This tool is intentionally split into stages so you can review and edit the plan before moving to images and PDF.

## Files

- `generate_program.py` - main CLI entrypoint
- `requirements.txt` - dependencies
- `program.json` - generated/editable program spec
- `assets/image_manifest.json` - image paths + credits metadata
- `3_day_gym_program.pdf` - final report

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step-by-step usage

### 1) Create program spec only

```bash
python generate_program.py create-program
```

This creates `program.json`.

Review and edit `program.json` if needed.

### 2) Download/resolve images based on selected exercises

```bash
python generate_program.py fetch-images
```

This reads `program.json`, downloads reusable images from Wikimedia Commons when possible, falls back to generated placeholders if needed, and writes:

- image files into `assets/`
- `assets/image_manifest.json` with credits

### 3) Build final PDF

```bash
python generate_program.py build-pdf
```

This reads `program.json` + `assets/image_manifest.json` and writes `3_day_gym_program.pdf`.

## One-command pipeline (optional)

```bash
python generate_program.py all
```

Runs all three steps in order.

## Licensing and safety

- External images are sourced from Wikimedia Commons only.
- Script accepts only clearly reusable license markers (CC BY, CC BY-SA, CC0, Public Domain, GFDL markers).
- If fetching fails, a locally generated placeholder is used.
- PDF text is normalized to ASCII-safe punctuation to reduce glyph issues.
