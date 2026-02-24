# PDF → Markdown: Image & Equation Extraction Guide

> **Prerequisites:** `pip install PyMuPDF pymupdf4llm Pillow`

---

## 1. Embedded Image Extraction (pymupdf4llm)

`pymupdf4llm` wraps PyMuPDF and handles images automatically when you pass the right kwargs:

```python
import pymupdf4llm
from pathlib import Path

md = pymupdf4llm.to_markdown(
    "input.pdf",
    write_images=True,      # extract embedded images to disk
    image_path="output/images",  # directory for saved images
    image_format="png",     # "png" or "jpeg"
    dpi=200,                # render resolution for image extraction
)

Path("output/output.md").write_text(md, encoding="utf-8")
```

### What this does

| Kwarg | Purpose |
|---|---|
| `write_images=True` | Enables image extraction (default is `False`) |
| `image_path` | Directory where images are saved (created automatically) |
| `image_format` | Output format — `"png"` for lossless, `"jpeg"` for smaller size |
| `dpi` | Resolution for rasterized images — 150 is fast, 200–300 for high quality |

### How it works internally

1. Iterates every page via `page.get_images(full=True)` to find embedded image xrefs
2. Extracts raw image bytes via `doc.extract_image(xref)`
3. Saves to `{image_path}/{image_name}.{image_format}`
4. Inserts `![image](images/image_name.png)` into the Markdown output
5. For vector/drawn content it falls back to `page.get_pixmap()` rendering

### Minimal standalone script

```python
"""extract_images.py — Extract PDF images using pymupdf4llm"""
import pymupdf4llm
from pathlib import Path
import sys

def extract(pdf_path: str, out_dir: str = "output"):
    img_dir = f"{out_dir}/images"
    Path(img_dir).mkdir(parents=True, exist_ok=True)

    md = pymupdf4llm.to_markdown(
        pdf_path,
        write_images=True,
        image_path=img_dir,
        image_format="png",
        dpi=200,
    )

    md_path = f"{out_dir}/{Path(pdf_path).stem}.md"
    Path(md_path).write_text(md, encoding="utf-8")
    print(f"✅ Saved to {md_path}")
    print(f"   Images in {img_dir}/")

if __name__ == "__main__":
    extract(sys.argv[1] if len(sys.argv) > 1 else "input.pdf")
```

```bash
pip install PyMuPDF pymupdf4llm
python extract_images.py my_document.pdf
```

---

## 2. Equation Image Extraction (Custom Pipeline)

PDFs render equations using special math fonts (Symbol, CMSY, CMMI, etc.). These produce garbled Unicode when extracted as text. The solution: **detect equation regions → render them as PNG screenshots → replace the garbled text with image references.**

### Pipeline Overview

```
PDF Page
  │
  ├── Font Analysis ──→ Identify math fonts
  │
  ├── Line-Level Detection ──→ Flag lines as "equation" vs "text"
  │
  ├── Region Detection ──→ Merge adjacent equation lines into bounding boxes
  │
  ├── Rendering ──→ Clip page region as high-res PNG
  │
  └── Markdown Replacement ──→ Swap garbled text with ![equation](path)
```

---

### Step 1: Font Analysis — Detecting Math Fonts

PDFs use fonts like **Symbol**, **CMSY10**, **CMMI12**, **CMEX10**, **MT Extra** for math.
We scan every span on every page to build a set of "math font" names.

```python
import fitz  # PyMuPDF

# Fonts whose names contain any of these substrings are math fonts
MATH_FONT_MARKERS = [
    "Symbol", "CMSY", "CMMI", "CMEX", "CMR", "CMTI",
    "MT Extra", "Math", "Euclid", "Universal",
    "Mathematica", "Cambria Math", "STIX",
]

def is_math_font(font_name: str) -> bool:
    """Check if a font name indicates a math/symbol font."""
    name_upper = font_name.upper()
    return any(marker.upper() in name_upper for marker in MATH_FONT_MARKERS)


def get_page_math_fonts(page) -> set[str]:
    """Return the set of math font names used on a page."""
    math_fonts = set()
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if is_math_font(span["font"]):
                    math_fonts.add(span["font"])
    return math_fonts
```

### How to verify

```python
doc = fitz.open("paper.pdf")
for i, page in enumerate(doc):
    fonts = get_page_math_fonts(page)
    if fonts:
        print(f"Page {i+1}: math fonts = {fonts}")
```

---

### Step 2: Line-Level Detection — Is This Line an Equation?

A text line is classified as an equation if **most of its characters come from math fonts**, or if it contains a high density of known math symbols.

```python
# Unicode ranges and characters commonly used in equations
MATH_SYMBOLS = set("∀∃∅∈∉∋∏∑−∗√∝∞∠∧∨∩∪∫≈≠≡≤≥⊂⊃⊆⊇⊕⊗⊥⋅±×÷αβγδεζηθικλμνξπρσςτυφχψωΓΔΘΛΞΠΣΦΨΩ∂∇←→↑↓↔⇒⇔ℵℏ")

def math_char_ratio(text: str) -> float:
    """Fraction of characters that are math symbols or from known math code points."""
    if not text.strip():
        return 0.0
    math_count = sum(1 for ch in text if ch in MATH_SYMBOLS or ord(ch) > 0x2200)
    return math_count / len(text)


def is_equation_line(line: dict, math_fonts: set[str]) -> bool:
    """Decide if a text line dict (from page.get_text('dict')) is an equation.

    Heuristics:
      1. >50% of spans use a math font
      2. >30% of characters are math symbols
      3. Short lines with mostly non-ASCII (garbled math)
    """
    spans = line["spans"]
    if not spans:
        return False

    # Heuristic 1: majority of spans use math fonts
    math_span_count = sum(1 for s in spans if s["font"] in math_fonts)
    if math_span_count / len(spans) > 0.5:
        return True

    # Heuristic 2: high density of math symbols in combined text
    full_text = "".join(s["text"] for s in spans)
    if math_char_ratio(full_text) > 0.30:
        return True

    # Heuristic 3: short garbled text (non-ASCII heavy, < 80 chars)
    if len(full_text) < 80:
        non_ascii = sum(1 for ch in full_text if ord(ch) > 127)
        if non_ascii / max(len(full_text), 1) > 0.5:
            return True

    return False
```

---

### Step 3: Region Detection — Finding Equation Bounding Boxes

Adjacent equation lines are merged into a single bounding box. This handles multi-line equations like:

```
    E = mc²
      = m × c × c
```

```python
def find_equation_regions(page, math_fonts: set[str]) -> list[fitz.Rect]:
    """Find bounding boxes of equation regions on a page.

    Scans all text blocks/lines, flags equation lines, and merges
    vertically adjacent ones into unified rectangles.
    """
    equation_rects: list[fitz.Rect] = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    current_rect = None  # accumulator for merging adjacent eq lines

    for block in blocks:
        for line in block.get("lines", []):
            bbox = fitz.Rect(line["bbox"])

            if is_equation_line(line, math_fonts):
                if current_rect is None:
                    current_rect = bbox
                else:
                    # Merge if vertically close (gap < 10pt)
                    if bbox.y0 - current_rect.y1 < 10:
                        current_rect |= bbox  # union of rects
                    else:
                        equation_rects.append(current_rect)
                        current_rect = bbox
            else:
                # Non-equation line — flush any pending region
                if current_rect is not None:
                    equation_rects.append(current_rect)
                    current_rect = None

    # Don't forget the last region
    if current_rect is not None:
        equation_rects.append(current_rect)

    return equation_rects
```

---

### Step 4: Rendering — Clipping the Page Region as High-Res PNG

Once we have the bounding box, we render just that region at high DPI.

```python
from pathlib import Path

def render_equation(page, rect: fitz.Rect, output_path: str, dpi: int = 300) -> str:
    """Render a rectangular region of a PDF page as a PNG image.

    Args:
        page: fitz.Page object
        rect: bounding box of the equation region
        output_path: full path to save the PNG (e.g. 'images/eq_p2_1.png')
        dpi: render resolution (300 recommended for equations)

    Returns:
        The output_path on success, empty string on failure.
    """
    try:
        # Add small padding around the equation (5pt each side)
        padded = rect + (-5, -5, 5, 5)
        # Clip to page bounds
        padded &= page.rect

        # Create a transformation matrix for the target DPI
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        # Render only the clipped region
        pix = page.get_pixmap(matrix=mat, clip=padded, alpha=False)
        pix.save(output_path)

        return output_path
    except Exception as e:
        print(f"  [warn] Equation render failed: {e}")
        return ""
```

### Key parameters

| Parameter | Purpose |
|---|---|
| `dpi=300` | High resolution keeps symbols legible — use 200 for speed, 300 for quality |
| `clip=padded` | Only renders the equation region, not the whole page |
| `alpha=False` | White background instead of transparent |
| Padding `(-5, -5, 5, 5)` | Prevents clipping edges of ascenders/descenders |

---

### Step 5: Markdown Replacement — Swapping Garbled Text with Images

Extract the Markdown normally, then find and replace equation text with image references.

```python
import re

def replace_equations_in_markdown(
    md_text: str,
    page_num: int,
    page,
    math_fonts: set[str],
    image_dir: str,
    dpi: int = 300,
) -> str:
    """Find equation regions on a page and replace their garbled text
    in the Markdown output with image references.
    """
    regions = find_equation_regions(page, math_fonts)
    if not regions:
        return md_text

    Path(image_dir).mkdir(parents=True, exist_ok=True)

    for idx, rect in enumerate(regions):
        # Get the raw text from this region to find it in md_text
        garbled = page.get_text("text", clip=rect).strip()
        if not garbled:
            continue

        # Render the equation region
        img_name = f"eq_p{page_num}_{idx + 1}.png"
        img_path = str(Path(image_dir) / img_name)
        result = render_equation(page, rect, img_path, dpi=dpi)

        if result:
            # Replace the garbled text with an image reference
            # Escape regex special chars in the garbled text
            escaped = re.escape(garbled)
            # Allow flexible whitespace matching
            pattern = re.sub(r"\\s+", r"\\s+", escaped)
            replacement = f"![equation](images/{img_name})"
            md_text = re.sub(pattern, replacement, md_text, count=1)

    return md_text
```

---

## 3. Post-Processing Pipeline — Putting It All Together

This integrates pymupdf4llm image extraction with custom equation replacement.

```python
import fitz
import pymupdf4llm
from pathlib import Path


def convert_pdf_with_equations(
    pdf_path: str,
    output_dir: str = "output",
    dpi: int = 200,
    eq_dpi: int = 300,
) -> str:
    """Full pipeline: extract images AND replace equations.

    1. Use pymupdf4llm for base Markdown + image extraction
    2. Post-process each page to detect and render equations
    """
    img_dir = f"{output_dir}/images"
    Path(img_dir).mkdir(parents=True, exist_ok=True)

    # ── Stage 1: Base extraction with pymupdf4llm ──
    md_text = pymupdf4llm.to_markdown(
        pdf_path,
        write_images=True,
        image_path=img_dir,
        image_format="png",
        dpi=dpi,
    )

    # ── Stage 2: Equation detection and replacement ──
    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        math_fonts = get_page_math_fonts(page)

        if math_fonts:
            md_text = replace_equations_in_markdown(
                md_text,
                page_num + 1,
                page,
                math_fonts,
                img_dir,
                dpi=eq_dpi,
            )

    doc.close()

    # ── Stage 3: Fix relative image paths ──
    # pymupdf4llm may use absolute paths; normalise to relative
    md_text = md_text.replace(img_dir.replace("\\", "/") + "/", "images/")
    md_text = md_text.replace(img_dir.replace("/", "\\") + "\\", "images/")

    # ── Save ──
    md_path = f"{output_dir}/{Path(pdf_path).stem}.md"
    Path(md_path).write_text(md_text, encoding="utf-8")

    return md_text
```

---

## 4. Output Structure

After running the pipeline, you'll get:

```
output/
├── document.md            # Final Markdown with all content
└── images/
    ├── page1_img0.png      # Embedded photos/diagrams (from pymupdf4llm)
    ├── page1_img1.png
    ├── page3_img0.png
    ├── eq_p2_1.png         # Equation screenshot (custom pipeline)
    ├── eq_p2_2.png
    ├── eq_p5_1.png
    └── ...
```

### In the Markdown

Embedded images appear as:
```markdown
![image](images/page1_img0.png)
```

Equations appear as:
```markdown
The energy-mass equivalence is given by:

![equation](images/eq_p2_1.png)

where *m* is the rest mass.
```

---

## 5. Quick Start — Complete Runnable Script

Copy this into `convert.py` and run it:

```python
#!/usr/bin/env python3
"""
PDF → Markdown converter with image + equation extraction.

Usage:
    pip install PyMuPDF pymupdf4llm Pillow
    python convert.py input.pdf [output_dir]
"""
import sys
import re
import fitz
import pymupdf4llm
from pathlib import Path

# ─── Math font detection ───────────────────────────────────────
MATH_FONT_MARKERS = [
    "Symbol", "CMSY", "CMMI", "CMEX", "CMR", "CMTI",
    "MT Extra", "Math", "Euclid", "Cambria Math", "STIX",
]

MATH_SYMBOLS = set(
    "∀∃∅∈∉∋∏∑−∗√∝∞∠∧∨∩∪∫≈≠≡≤≥⊂⊃⊆⊇⊕⊗⊥⋅±×÷"
    "αβγδεζηθικλμνξπρσςτυφχψω"
    "ΓΔΘΛΞΠΣΦΨΩ∂∇←→↑↓↔⇒⇔"
)


def is_math_font(font_name: str) -> bool:
    upper = font_name.upper()
    return any(m.upper() in upper for m in MATH_FONT_MARKERS)


def get_page_math_fonts(page) -> set[str]:
    fonts = set()
    for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if is_math_font(span["font"]):
                    fonts.add(span["font"])
    return fonts


# ─── Line-level equation detection ─────────────────────────────
def is_equation_line(line: dict, math_fonts: set[str]) -> bool:
    spans = line["spans"]
    if not spans:
        return False
    math_count = sum(1 for s in spans if s["font"] in math_fonts)
    if math_count / len(spans) > 0.5:
        return True
    text = "".join(s["text"] for s in spans)
    math_chars = sum(1 for ch in text if ch in MATH_SYMBOLS or ord(ch) > 0x2200)
    if len(text) > 0 and math_chars / len(text) > 0.3:
        return True
    return False


# ─── Region detection ──────────────────────────────────────────
def find_equation_regions(page, math_fonts: set[str]) -> list[fitz.Rect]:
    regions = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    current = None
    for block in blocks:
        for line in block.get("lines", []):
            bbox = fitz.Rect(line["bbox"])
            if is_equation_line(line, math_fonts):
                if current is None:
                    current = bbox
                elif bbox.y0 - current.y1 < 10:
                    current |= bbox
                else:
                    regions.append(current)
                    current = bbox
            else:
                if current is not None:
                    regions.append(current)
                    current = None
    if current is not None:
        regions.append(current)
    return regions


# ─── Render equation region as PNG ─────────────────────────────
def render_equation(page, rect: fitz.Rect, out_path: str, dpi: int = 300) -> str:
    try:
        padded = rect + (-5, -5, 5, 5)
        padded &= page.rect
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, clip=padded, alpha=False)
        pix.save(out_path)
        return out_path
    except Exception as e:
        print(f"  [warn] Render failed: {e}")
        return ""


# ─── Replace garbled equation text with image refs ─────────────
def replace_equations(md: str, page_num: int, page, math_fonts, img_dir, dpi=300):
    regions = find_equation_regions(page, math_fonts)
    if not regions:
        return md
    for idx, rect in enumerate(regions):
        garbled = page.get_text("text", clip=rect).strip()
        if not garbled:
            continue
        name = f"eq_p{page_num}_{idx+1}.png"
        path = str(Path(img_dir) / name)
        if render_equation(page, rect, path, dpi):
            escaped = re.escape(garbled)
            pattern = re.sub(r"\\s+", r"\\s+", escaped)
            md = re.sub(pattern, f"![equation](images/{name})", md, count=1)
    return md


# ─── Main pipeline ─────────────────────────────────────────────
def convert(pdf_path: str, out_dir: str = "output"):
    img_dir = f"{out_dir}/images"
    Path(img_dir).mkdir(parents=True, exist_ok=True)

    print(f"📄 Extracting: {pdf_path}")

    # Stage 1: pymupdf4llm base extraction
    md = pymupdf4llm.to_markdown(
        pdf_path,
        write_images=True,
        image_path=img_dir,
        image_format="png",
        dpi=200,
    )
    print("  ✅ Base Markdown + images extracted")

    # Stage 2: Equation detection and replacement
    doc = fitz.open(pdf_path)
    eq_count = 0
    for i in range(len(doc)):
        page = doc[i]
        fonts = get_page_math_fonts(page)
        if fonts:
            before = md
            md = replace_equations(md, i + 1, page, fonts, img_dir)
            if md != before:
                eq_count += 1
    doc.close()
    print(f"  ✅ Equations replaced on {eq_count} page(s)")

    # Stage 3: Normalize paths
    md = md.replace(img_dir.replace("\\", "/") + "/", "images/")
    md = md.replace(img_dir.replace("/", "\\") + "\\", "images/")

    # Save
    stem = Path(pdf_path).stem
    md_path = f"{out_dir}/{stem}.md"
    Path(md_path).write_text(md, encoding="utf-8")
    print(f"  ✅ Saved: {md_path}")
    return md_path


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "input.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "output"
    convert(pdf, out)
```

### Run it

```bash
pip install PyMuPDF pymupdf4llm Pillow
python convert.py research_paper.pdf results
```

### Output

```
📄 Extracting: research_paper.pdf
  ✅ Base Markdown + images extracted
  ✅ Equations replaced on 3 page(s)
  ✅ Saved: results/research_paper.md
```

---

## 6. Tuning & Tips

| Setting | Trade-off |
|---|---|
| `dpi=150` for images | Faster, smaller files — good for screenshots and diagrams |
| `dpi=200` for images | Good balance of speed and quality |
| `dpi=300` for equations | Keeps small symbols legible — recommended |
| Padding `(-5, -5, 5, 5)` | Increase to `(-10, -10, 10, 10)` if equations get clipped |
| `MATH_FONT_MARKERS` | Add your PDF's specific fonts if they aren't detected |
| `IMAGE_FORMAT="jpeg"` | Smaller files but lossy — use PNG for equations |

### Debugging equation detection

```python
# Print what the detector sees on each page
doc = fitz.open("paper.pdf")
for i, page in enumerate(doc):
    fonts = get_page_math_fonts(page)
    regions = find_equation_regions(page, fonts)
    if regions:
        print(f"Page {i+1}: {len(regions)} equation(s)")
        for r in regions:
            text = page.get_text("text", clip=r).strip()
            print(f"  rect={r}, text={text[:60]}...")
```
