# PDF to Markdown Converter — Complete Technical Guide

This document explains **how the tool works internally** — its architecture, conversion pipeline, every class and function, post-processing steps, and design decisions. Use this as a reference for understanding, debugging, extending, or building AI skills around the tool.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Conversion Pipeline](#conversion-pipeline)
  - [Primary Path: pymupdf4llm](#primary-path-pymupdf4llm)
  - [Fallback Path: Manual Page-by-Page](#fallback-path-manual-page-by-page)
- [Extractor Classes](#extractor-classes)
- [Standalone Functions](#standalone-functions)
- [Post-Processing Pipeline](#post-processing-pipeline)
- [Link Injection System](#link-injection-system)
- [Image Handling](#image-handling)
- [Table Handling](#table-handling)
- [List & Bullet Handling](#list--bullet-handling)
- [Heading Detection](#heading-detection)
- [Password-Protected PDFs](#password-protected-pdfs)
- [CLI & Entry Points](#cli--entry-points)
- [File & Directory Structure](#file--directory-structure)
- [Key Design Decisions](#key-design-decisions)
- [Dependency Map](#dependency-map)
- [Common Patterns & Conventions](#common-patterns--conventions)
- [Extending the Tool](#extending-the-tool)

---

## Architecture Overview

The tool is a **single-file Python script** (`pdf_to_md_converter.py`, ~1100 lines) that converts PDF documents into clean Markdown. It follows a modular design with:

- **14 classes** — extractors, detectors, formatters, and handlers for each content type
- **1 main conversion function** (`pdf_to_markdown()`) — orchestrates the pipeline
- **Post-processing functions** — fix common extraction artifacts
- **CLI wrapper** (`main()`) — handles argument parsing and file I/O

```
┌─────────────────────────────────────────────────────┐
│                    CLI (main())                     │
│         argparse → paths → pdf_to_markdown()        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              pdf_to_markdown()                      │
│                                                     │
│   ┌─────────────────┐   ┌────────────────────────┐  │
│   │  pymupdf4llm    │   │  Manual Fallback       │  │
│   │  (preferred)    │   │  page_to_markdown()    │  │
│   │                 │   │  per page              │  │
│   └────────┬────────┘   └───────────┬────────────┘  │
│            │                        │               │
│            ▼                        ▼               │
│   ┌─────────────────────────────────────────────┐   │
│   │         Post-Processing Pipeline            │   │
│   │  • Image path fixing                        │   │
│   │  • Code-block bullet unwrapping             │   │
│   │  • Orphan list marker merging               │   │
│   │  • Page anchor insertion                    │   │
│   │  • Inline link injection                    │   │
│   │  • Table-cell bullet merging                │   │
│   │  • Blank line cleanup                       │   │
│   └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## Conversion Pipeline

The tool has **two pipelines**. The primary path uses `pymupdf4llm` for better layout fidelity. The fallback runs when `pymupdf4llm` is not installed.

### Primary Path: pymupdf4llm

This is the default and recommended path. Here is the exact execution order:

```
1. Open PDF with fitz, authenticate if encrypted
2. Call pymupdf4llm.to_markdown(doc, page_chunks=True, write_images=True, ...)
   → Returns a list of dicts, each with a "text" key (one per page)
3. For EACH chunk (single loop):
   a. Fix image paths (absolute → relative "images/")
   b. Unwrap code-block bullets (_unwrap_code_block_bullets)
   c. Merge orphaned list markers (_merge_orphan_list_markers)
4. Assemble all chunks with page anchors + inject links (_inject_internal_links)
5. Merge orphaned bullets in table cells (regex)
6. Clean up excessive blank lines
7. Write to output file
```

**Key detail:** `pymupdf4llm.to_markdown()` is called with `page_chunks=True`, which returns a `list[dict]` instead of a single string. Each dict has at minimum a `"text"` key with the Markdown for that page. This is essential because it lets us insert `<a id="page-N"></a>` anchors between pages for internal link navigation.

**Key detail:** The PDF is pre-opened with `fitz.open()` and authenticated *before* being passed to `pymupdf4llm`. This is because `pymupdf4llm` does not correctly handle the `password` parameter on its own — it silently ignores it, leaving the document encrypted and causing extraction failures.

### Fallback Path: Manual Page-by-Page

When `pymupdf4llm` is not installed, the tool uses its own extraction pipeline:

```
1. Open PDF with fitz
2. Check encryption via SecurityHandler
3. Extract metadata → create YAML frontmatter
4. For EACH page:
   a. Insert page anchor <a id="page-N"></a>
   b. Calculate average font size (for heading detection)
   c. Extract images, tables, annotations, links (external + internal)
   d. Process text blocks span-by-span:
      - Apply formatting (bold/italic/underline)
      - Match spans to link rectangles (inline link injection)
      - Detect headings by font-size ratio
      - Detect/normalize list items
   e. Sort all elements by y-position
   f. Render with paragraph breaks based on vertical gaps
   g. Post-process: merge orphan list markers, add soft line breaks
5. Append embedded files section
6. Join all pages, clean up blank lines
7. Write to output file
```

---

## Extractor Classes

Each class is a static utility — no state, no instantiation needed. They all follow the pattern: `ClassName.method(page_or_doc) → extracted_data`.

### PDFMetadataExtractor
- **Method:** `extract(doc) → dict`
- **Purpose:** Extracts title, author, subject, creator, dates, page count, encryption status
- **Used by:** Fallback pipeline only (pymupdf4llm path doesn't emit frontmatter separately)

### URLExtractor
- **Methods:** `find_visible_urls(text)`, `markdown_url(text, url)`
- **Purpose:** Regex-based URL detection in text, Markdown link formatting
- **Pattern:** `https?://[^\s\)]+`

### ListDetector
- **Methods:** `is_bullet_item(text)`, `is_numbered_item(text)`, `normalize_bullet(text)`
- **Purpose:** Detects bullet markers (•, ▪, ◦, -, *, etc.) and numbered markers (1., a), etc.)
- **normalize_bullet:** Replaces any bullet variant with standard Markdown `- `
- **Used by:** Both pipelines, also by `_unwrap_code_block_bullets()`

### TextFormatter
- **Method:** `apply_formatting(span) → str`
- **Purpose:** Converts PyMuPDF span flags to Markdown formatting
- **Flag mapping:**
  - Flag 16 → `**bold**`
  - Flag 2 → `*italic*`
  - Flag 8 → `<u>underline</u>`
  - Flag 16+2 → `***bold italic***`
- **Strips whitespace** before wrapping — returns empty string for blank spans
- **Also has:** `get_hex_color(color_tuple)` for RGB → hex conversion

### HeadingDetector
- **Methods:** `get_average_font_size(page)`, `detect_heading(font_size, avg_size, is_bold)`
- **Purpose:** Heuristic heading detection based on font-size ratio to page average
- **Thresholds:**
  - `ratio ≥ 1.8` → `# ` (H1)
  - `ratio ≥ 1.35` → `## ` (H2)
  - `ratio ≥ 1.15` (or `≥ 1.1` if bold) → `### ` (H3)

### ImageExtractor
- **Method:** `extract_all(page, page_num, output_dir) → list[(md_ref, y_pos)]`
- **Purpose:** Extracts images from page, saves to disk, returns Markdown references with position
- **Image format:** `<img src="images/pageN_imgM.ext" style="width:...in;height:...in" />`
- **Also resizes** images via `resize_image()` (max 600×800px, using Pillow)
- **Used by:** Fallback pipeline only (pymupdf4llm handles images in primary path)

### TableExtractor
- **Methods:** `extract_all(page)`, `to_markdown(data)`, `_escape_cell(cell)`
- **Purpose:** Uses `page.find_tables()` to extract tables, converts to Markdown pipe syntax
- **Cell escaping:** Pipes (`|`) escaped as `\|`, newlines replaced with spaces
- **Used by:** Fallback pipeline only

### DrawingExtractor
- **Method:** `find_horizontal_rules(page) → list[float]`
- **Purpose:** Detects full-width horizontal lines (≥60% page width, <4px tall) from vector graphics
- **Returns:** Sorted y-positions
- **Note:** Currently defined but not actively called in either pipeline

### AnnotationExtractor
- **Method:** `extract_all(page) → list[(markdown, y_pos)]`
- **Purpose:** Extracts text comments (`> 💬 **Note:** ...`) and highlights (`==**Highlight:** ...==`)
- **Used by:** Fallback pipeline only

### LinkExtractor
- **Methods:** `extract_all(page)`, `extract_with_rects(page)`
- **Purpose:** Extracts external hyperlinks (URIs) with their bounding rectangles
- **Skips:** Internal goto links (handled by InternalLinkExtractor)
- **Used by:** Both pipelines — `_inject_internal_links()` uses `extract_with_rects()`

### InternalLinkExtractor
- **Methods:** `extract_with_rects(page)`, `slugify(text)`
- **Purpose:** Extracts internal goto links, returns `(rect, "#page-N", y_pos)` tuples
- **Page numbering:** PyMuPDF uses 0-indexed pages; converted to 1-indexed for anchors
- **Used by:** Both pipelines — primary via `_inject_internal_links()`, fallback via `page_to_markdown()`

### BookmarkExtractor
- **Method:** `extract(doc) → str`
- **Purpose:** Converts PDF outline/bookmarks into a Markdown table of contents
- **Format:** Indented list with `[Title](#page-N)` links
- **Important:** This is NOT called by either pipeline automatically — the TOC comes from `pymupdf4llm` in the primary path. In the fallback, it could be called but currently isn't to avoid duplicate TOCs.

### EmbeddedFileExtractor
- **Method:** `extract(doc) → str`
- **Purpose:** Lists embedded/attached files with filenames and sizes
- **Used by:** Fallback pipeline only

### SecurityHandler
- **Methods:** `check_encryption(doc)`, `authenticate(doc, password)`, `get_permissions_info(doc)`
- **Purpose:** Handle encrypted PDFs — check status, authenticate, report permissions
- **Used by:** Both pipelines for authentication

---

## Standalone Functions

These functions sit outside classes and handle cross-cutting concerns:

### `_rect_overlap(rect_a, rect_b) → bool`
- Tests whether two `(x0, y0, x1, y1)` rectangles overlap
- Used by fallback pipeline to match text spans to link/table bounding boxes
- Returns `False` on any parse error (IndexError, TypeError)

### `create_frontmatter(metadata) → str`
- Generates YAML frontmatter (`---` delimited) from a metadata dict
- Uses `PyYAML` when available; falls back to manual string formatting
- Only called in the **fallback pipeline** (pymupdf4llm path does not emit separate frontmatter)

### `_extract_link_display_text(page, rect) → str`
- Extracts the visible text under a link rectangle via `page.get_text("text", clip=rect)`
- Collapses whitespace with `re.sub(r"\s+", " ", text)`
- Used by `_inject_internal_links()` for both external and internal links

### `page_to_markdown(page, page_num, image_dir) → str`
- Converts a single PDF page to Markdown (fallback pipeline only)
- Orchestrates: page anchor → font sizing → element extraction → span-level link matching → y-position sorting → rendering → orphan marker merging → soft line breaks
- Returns the complete Markdown string for that page

### Soft Line Breaks (inside `page_to_markdown`)

Markdown collapses single newlines into spaces. The fallback pipeline appends **two trailing spaces** (`"  "`) to consecutive non-empty text lines, creating soft `<br>` breaks so each line renders separately. Skipped for lines starting with `|` (tables), `<` (HTML/images), or `>` (blockquotes).

---

## Post-Processing Pipeline

After raw extraction, several post-processing functions clean up common artifacts:

### 1. Image Path Fixing (pymupdf4llm path only)

pymupdf4llm writes images to the specified directory but embeds **absolute paths** in the Markdown. The tool rewrites these to relative `images/` paths:

```python
chunk_text = chunk_text.replace(abs_img + "/", "images/")
chunk_text = chunk_text.replace(abs_img.replace("/", "\\") + "\\", "images/")
chunk_text = chunk_text.replace(rel_img + "/", "images/")
```

Handles both forward-slash and backslash variants for Windows compatibility.

### 2. Code-Block Bullet Unwrapping (`_unwrap_code_block_bullets`)

**Problem:** pymupdf4llm sometimes wraps monospaced list items inside `` ``` `` fenced code blocks, making them render as grey code instead of proper list items.

**Solution:** Scans for fenced code blocks, checks if the content contains list items (via `ListDetector`), and if so, strips the fences and emits the content as normal Markdown list items.

### 3. Orphan List Marker Merging (`_merge_orphan_list_markers`)

**Problem:** PDF extraction often puts a bullet character (`•`) or number (`1.`) on its own line, with the actual text on the next line.

**Solution:** Detects lone markers via `_RE_LONE_BULLET` and `_RE_LONE_NUMBER` regex patterns, finds the next non-empty line, and merges them:

```
Before:          After:
•                - Item text here
Item text here
```

Also handles heading-prefixed markers (`### ◦`) and bold-wrapped markers (`**1.**`).

### 4. Table-Cell Bullet Merging (pymupdf4llm path only)

**Problem:** pymupdf4llm puts bullet characters on their own `<br>` segment inside table cells:

```
•<br>Item text        →    • Item text
<br>•<br>Item text    →    <br>• Item text
```

**Solution:** Two pre-compiled regex patterns:
- `_RE_TABLE_BULLET_BR`: Merges `•<br>text` → `• text`
- `_RE_TABLE_BR_BULLET_BR`: Merges `<br>•<br>text` → `<br>• text`

### 5. Blank Line Cleanup

Collapses 3+ consecutive newlines into exactly 2 (one blank line): `re.sub(r"\n{3,}", "\n\n", result)`

---

## Link Injection System

The most complex post-processing step. Handled by `_inject_internal_links()` in the pymupdf4llm path, and span-level matching in the fallback path.

### How it Works (pymupdf4llm path)

```
1. Assemble all page chunks with <a id="page-N"></a> anchors between them
2. Re-open the PDF with fitz
3. For each page, extract:
   - External links via LinkExtractor.extract_with_rects() → (rect, uri, y_pos)
   - Internal links via InternalLinkExtractor.extract_with_rects() → (rect, anchor, y_pos)
4. For each link:
   - Get the display text under the link rectangle: page.get_text("text", clip=rect)
   - Clean whitespace: re.sub(r"\s+", " ", text)
   - Create replacement pair: ("plain text", "[plain text](url)")
5. Sort replacements longest-first (avoids partial matches)
6. Apply each replacement ONCE using regex with lookbehind/lookahead:
   - (?<!\[) — not already inside a Markdown link
   - (?!\]\() — not already followed by ](
```

**Helper function:** `_extract_link_display_text(page, rect)` handles the text extraction and cleaning, used by both external and internal link processing.

### How it Works (Fallback path)

In `page_to_markdown()`, link matching happens at the **span level**:

```
For each text span on the page:
  1. Build span bounding box from span["bbox"] or span["origin"]
  2. Check if span overlaps any external link rectangle
  3. If no external match, check internal link rectangles
  4. If match found: emit [formatted_text](url) instead of plain text
  5. Track matched indices to avoid duplicate standalone link entries
```

### Page Anchors

Both pipelines insert HTML anchors before each page's content:

```html
<a id="page-1"></a>

[page 1 content...]

<a id="page-2"></a>

[page 2 content...]
```

Internal links use `#page-N` format. TOC entries from BookmarkExtractor also use this format: `[Chapter Title](#page-5)`.

---

## Image Handling

### pymupdf4llm Path (Primary)

- `pymupdf4llm.to_markdown()` with `write_images=True` extracts images automatically
- Images saved as PNG at 150 DPI to the specified `image_dir`
- Markdown references are standard: `![](images/filename.png)`
- Post-processing rewrites absolute paths to relative `images/` prefix

### Fallback Path

- `ImageExtractor.extract_all()` uses `page.get_images()` + `page.parent.extract_image(xref)`
- Images saved to disk, then resized via Pillow (max 600×800px, LANCZOS, 85% quality)
- Markdown reference uses inline HTML for precise sizing:
  ```html
  <img src="images/page1_img0.png" style="width:2.50in;height:3.00in" />
  ```
- Image position (y-coordinate) is used for proper ordering among text elements

---

## Table Handling

### pymupdf4llm Path

pymupdf4llm handles table extraction internally. The tool only post-processes table-cell bullets.

### Fallback Path

- `TableExtractor.extract_all()` uses `page.find_tables()` (PyMuPDF built-in)
- Extracts tabular data as 2D lists
- Converts to Markdown pipe table syntax:
  ```markdown
  | Header 1 | Header 2 |
  | --- | --- |
  | Cell 1 | Cell 2 |
  ```
- Cell escaping: pipes (`|`) → `\|`, newlines → spaces
- Rows shorter than header are padded with empty cells
- Table bboxes are tracked to **skip text blocks** that overlap tables (avoids content duplication)

---

## List & Bullet Handling

### Detection

`ListDetector` recognizes these bullet patterns:
- Characters: `• - * · ▪ ▸ ► → ✓ ◆ ○ ● ◦ – —`
- Indented: `  - item`, `  • item`
- Numbered: `1. item`, `2) item`, `a. item`, `A) item`

### Normalization

All bullet variants are converted to standard Markdown `- `:
```
• Item    →  - Item
▪ Item    →  - Item
* Item    →  - Item
```

### Three-Stage Bullet Fix

1. **Code-block unwrapping** — monospaced bullets freed from ``` fences
2. **Orphan marker merging** — lone markers joined with next line
3. **Table-cell bullet merging** — `<br>`-separated bullets joined (pymupdf4llm path)

---

## Heading Detection

Uses font-size heuristics in `HeadingDetector`:

```python
ratio = font_size / average_font_size

ratio ≥ 1.8             → # H1
ratio ≥ 1.35            → ## H2
ratio ≥ 1.15            → ### H3
ratio ≥ 1.1 AND bold    → ### H3 (bold boost)
```

**Bold stripping:** When a heading is detected, redundant `**bold**` or `***bold italic***` wrapping is removed from the content, since the heading prefix already conveys emphasis.

---

## Password-Protected PDFs

### pymupdf4llm Path

```python
doc = fitz.open(str(pdf_path))
if doc.is_encrypted:
    if password:
        if not doc.authenticate(password):
            raise PermissionError("Invalid password!")
    else:
        raise PermissionError("PDF is password-protected!")
# Pass the authenticated doc object (not path) to pymupdf4llm
chunks = pymupdf4llm.to_markdown(doc, ...)
```

**Critical:** The `doc` object (already authenticated) is passed to `pymupdf4llm`, not the file path. This is because `pymupdf4llm` ignores its own `password` parameter.

### Fallback Path

Uses `SecurityHandler.check_encryption()` and `SecurityHandler.authenticate()`.

### Link Injection Re-authentication

`_inject_internal_links()` re-opens the PDF with fitz for link extraction. If the PDF is encrypted, it re-authenticates using the same password passed via the `password` parameter.

---

## CLI & Entry Points

### main()

```
python pdf_to_md_converter.py <pdf_path> [-o OUTPUT] [--extract-images DIR] [--password PWD]
```

### Default Paths

When no `-o` or `--extract-images` is specified:

```
Input:  pdfs/MyDocument.pdf
Output: converted/MyDocument/MyDocument.md
Images: converted/MyDocument/images/
```

The `converted/` directory is relative to the script's location (`PROJECT_ROOT`).

### pdf_to_markdown()

The main conversion function. Can be called programmatically:

```python
from pdf_to_md_converter import pdf_to_markdown

result = pdf_to_markdown(
    pdf_path="document.pdf",
    output_path="output.md",      # optional: writes to file
    image_dir="./images",          # optional: where to save images
    password="secret"              # optional: for encrypted PDFs
)
```

Returns the full Markdown string regardless of whether `output_path` is set.

---

## File & Directory Structure

```
tool/
├── pdf_to_md_converter.py   # The entire tool (single file)
├── requirements.txt          # pymupdf, pymupdf4llm, Pillow, PyYAML
├── README.md                 # User-facing documentation
├── pdftomd_guide.md          # This guide
├── .gitignore
├── pdfs/                     # Input PDFs (gitignored)
│   └── *.pdf
└── converted/                # Output directory (gitignored, auto-created)
    └── <pdf_name>/
        ├── <pdf_name>.md     # Converted Markdown
        └── images/           # Extracted images
            ├── page1_img0.png
            ├── page2_img1.png
            └── ...
```

---

## Key Design Decisions

### Single-File Architecture
The entire tool is one Python file. This makes it portable, easy to copy, and requires no package structure. All classes are static utilities — no instantiation or state management needed.

### pymupdf4llm as Primary Extractor
pymupdf4llm provides better layout fidelity, automatic image extraction with correct positioning, and proper table rendering. The manual fallback exists for environments where pymupdf4llm cannot be installed.

### Page Chunks, Not Single String
Using `page_chunks=True` with pymupdf4llm returns per-page data, allowing precise page anchor insertion. Without this, all pages merge into one string with no page boundaries — making internal link navigation impossible.

### Pre-Open Authentication
pymupdf4llm silently ignores the `password` parameter. The fix: open the PDF with `fitz`, authenticate it, and pass the **document object** (not file path) to pymupdf4llm.

### Fallback Link Injection via Rectangles
Links in PDFs are defined as rectangles over text regions. The tool extracts these rectangles, then finds the display text underneath each one using `page.get_text("text", clip=rect)`. This approach works regardless of text formatting or line breaks.

### Longest-First Replacement
When injecting links into Markdown text, replacements are sorted longest-first. This prevents shorter text from being matched inside longer overlapping text (e.g., "Page 12" vs "Page 1").

---

## Dependency Map

| Package | Import Name | Purpose | Required |
|---|---|---|---|
| pymupdf | `fitz` | Core PDF engine — parsing, text/image/table extraction, links, annotations | ✅ Yes |
| pymupdf4llm | `pymupdf4llm` | Enhanced layout-aware Markdown generation with image extraction | ✅ Yes |
| Pillow | `PIL.Image` | Image resizing/optimization (fallback path) | ✅ Yes |
| PyYAML | `yaml` | YAML frontmatter generation | ✅ Yes |

### Runtime Feature Flags

```python
HAS_YAML        # True if PyYAML is installed
HAS_PILLOW      # True if Pillow is installed
HAS_PYMUPDF4LLM # True if pymupdf4llm is installed → selects primary pipeline
```

If `HAS_YAML` is False, frontmatter is generated manually. If `HAS_PILLOW` is False, image resizing is skipped. If `HAS_PYMUPDF4LLM` is False, the manual fallback pipeline is used.

---

## Common Patterns & Conventions

### Error Handling

- **Fatal errors** → `raise` exceptions (FileNotFoundError, PermissionError, RuntimeError)
- **Non-fatal warnings** → `print(f"  [warn] ...")` and continue processing
- Every extractor wraps its logic in try/except to ensure one bad page/element doesn't crash the whole conversion

### Coordinate System

- PyMuPDF uses a coordinate system where **(0,0) is top-left**, y increases downward
- All y-positions are in **PDF points** (72 points = 1 inch)
- Elements are sorted by y-position for correct vertical ordering

### Naming Conventions

- Extractor classes: `<Thing>Extractor` (e.g., `ImageExtractor`, `TableExtractor`)
- Private functions: `_underscore_prefix` (e.g., `_inject_internal_links`, `_merge_orphan_list_markers`)
- Pre-compiled regex: `_RE_UPPER_CASE` (e.g., `_RE_LONE_BULLET`, `_RE_TABLE_BULLET_BR`)
- Feature flags: `HAS_UPPER_CASE` (e.g., `HAS_YAML`, `HAS_PILLOW`)

### Element Tuple Format

Elements are collected as tuples for sorting:
- **Text elements:** `(y_pos, "text", content, font_size, is_bold)` — 5 fields
- **Other elements:** `(y_pos, type, content)` — 3 fields
- Types: `"text"`, `"table"`, `"image"`, `"annotation"`, `"link"`

---

## Extending the Tool

### Adding a New Extractor

1. Create a new class following the `<Thing>Extractor` pattern
2. Add a static `extract_all(page)` or `extract(doc)` method
3. In the fallback pipeline (`page_to_markdown()`), call your extractor and append results to `elements` with appropriate y-position and type
4. For the pymupdf4llm path, add post-processing in `pdf_to_markdown()` if needed

### Adding a New Post-Processing Step

1. Define a function with `_underscore_prefix` naming
2. For per-chunk processing: add to the consolidated chunk loop in `pdf_to_markdown()`
3. For full-document processing: add after `_inject_internal_links()` in `pdf_to_markdown()`
4. Pre-compile any regex patterns as module-level `_RE_*` constants

### Modifying Heading Detection Thresholds

Edit the ratio thresholds in `HeadingDetector.detect_heading()`:
```python
if ratio >= 1.8:       # H1 threshold
elif ratio >= 1.35:    # H2 threshold
elif ratio >= 1.15:    # H3 threshold
```

### Adding New Bullet Characters

Add characters to `_BULLET_CHARS` string and update `ListDetector.BULLET_PATTERNS`:
```python
_BULLET_CHARS = r"•\-\*·▪▸►→✓◆○●◦–—"  # add new chars here
```
