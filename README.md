# Sheetfit

Expand short book PDFs to **~400 pages** so they print on **100 landscape sheets** (2 pages per side × duplex = 4 book pages per sheet).

Private tool for a fixed print format: half-Letter reading pages → FoldPress (or similar) for imposition.

## How it works

1. Count pages in the uploaded PDF.
2. If **&lt; 350** → extract text/images, retypeset with searchable typography (font size, leading, margins, chapter openers) until the layout lands near **400** pages.
3. If **350–399** → pad blank pages to 400 (no retypeset).
4. If **≥ 400** → pass through unchanged.

Page size of the expanded PDF is **half Letter portrait** (`5.5″ × 8.5″` / `396 × 612` pt), matching one slot on a landscape Letter sheet.

## Example: The Alchemist

Fixture: [`fixtures/3-The-Alchemist-Paulo-Coelho.pdf`](fixtures/3-The-Alchemist-Paulo-Coelho.pdf) (136 pages).

```bash
cd engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sheetfit expand ../fixtures/3-The-Alchemist-Paulo-Coelho.pdf \
  -o ../output/alchemist-expanded.pdf \
  --report ../examples/alchemist-report.json
```

See [`examples/alchemist-report.json`](examples/alchemist-report.json) for the last run’s parameters and page counts.

## Local app

Terminal 1 — engine API:

```bash
cd engine
source .venv/bin/activate
uvicorn sheetfit.api:app --host 127.0.0.1 --port 8765
```

Terminal 2 — web UI:

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The UI talks to `http://127.0.0.1:8765` (override with `NEXT_PUBLIC_SHEETFIT_API`).

## CLI

```bash
sheetfit info book.pdf
sheetfit expand book.pdf -o expanded.pdf --target 400 --threshold 350 --report report.json
```

## Print handoff

Sheetfit produces the **reading-page** PDF. For landscape duplex sheets (2-up), run the result through [FoldPress](https://github.com/Tahir-581/foldpress) (or your impose tool):

1. Media: Letter (or A4 if you change geometry later)
2. Duplex: **Flip on short edge**
3. Scale: **100% / Actual size**

## Layout

```
sheetfit/
  engine/          Python extract + typography search + WeasyPrint + FastAPI
  web/             Next.js upload / expand / download UI
  fixtures/        Sample PDFs (Alchemist)
  examples/        Expand reports
  output/          Local expand outputs (gitignored)
```

## Notes

- Happy path: narrative books with extractable text (Calibre / ebook PDFs).
- Images are kept; formula-like regions that are not clean text are preserved as images.
- Shrinking books **over** 400 pages is out of scope for v1.
- Retypesetting a full novel can take several minutes (multiple WeasyPrint passes).
