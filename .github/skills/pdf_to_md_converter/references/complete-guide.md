# Complete guide: PDF to Markdown converter

This reference documents the PDF-to-Markdown converter used by the pdf-to-md-converter skill: behavior, dependencies, CLI, Python API, and extractors.

## Dependencies

| Package        | Required | Purpose                                   |
|----------------|----------|-------------------------------------------|
| pymupdf (fitz) | Yes      | PDF open, text, images, links, tables      |
| pymupdf4llm    | Recommended | Extraction pipeline (headings, lists, tables, images) |
| Pillow         | Recommended | Image resize/optimization                  |
| PyYAML         | Recommended | YAML frontmatter                          |

**Install:**

```bash
pip install pymupdf
# Recommended for this skill:
pip install pymupdf4llm Pillow PyYAML
```

## CLI

```text
python pdf_to_md_converter.py <pdf> [-o OUTPUT] [--extract-images DIR] [--password PASSWORD]
```

- **pdf** (positional): Input PDF path.
- **-o, --output**: Output Markdown file. Default: `converted/<pdf_stem>/<pdf_stem>.md` (relative to script directory).
- **--extract-images DIR**: Directory for extracted images. Default when not set: `converted/<pdf_stem>/images`.
- **--password**: Password for encrypted PDFs.

## Python API

**Main entry point:**

```python
def pdf_to_markdown(
    pdf_path: str,
    output_path: str = None,
    image_dir: str = None,
    password: str = None
) -> str
```

- Converts the PDF to Markdown and returns the full Markdown string.
- If `output_path` is set, also writes the result to that file.
- If `image_dir` is set, creates it and saves images there; references in Markdown use a relative `images/` path.

## Extractors

The converter is built from focused extractors:

| Extractor              | Role |
|------------------------|------|
| PDFMetadataExtractor   | Document metadata (title, author, subject, creator, dates, page count, encryption). |
| TextFormatter         | Span-level bold/italic/underline → Markdown/HTML. |
| HeadingDetector       | Font size vs page average → `#`, `##`, `###`. |
| ListDetector          | Bullet and numbered list detection; normalizes bullets to `- `. |
| ImageExtractor        | Extracts images from pages, saves to directory, emits `<img>` with relative path; optional resize via Pillow. |
| TableExtractor        | Finds tables (PyMuPDF), outputs Markdown table syntax. |
| LinkExtractor         | External links (URI) with rects for inline replacement. |
| InternalLinkExtractor | Internal goto links → `#page-N` anchors. |
| AnnotationExtractor  | Text and Highlight annotations → blockquote/highlight Markdown. |
| BookmarkExtractor     | PDF outline → Markdown TOC with `#page-N` links. |
| EmbeddedFileExtractor | Lists embedded files in a section. |
| SecurityHandler       | Encryption check, password auth, permissions summary. |

## Pipeline

The converter uses **pymupdf4llm** with `pymupdf4llm.to_markdown(..., write_images=True, page_chunks=True)`, then:

- Normalizes image paths to `images/`
- Unwraps code-block bullets, merges orphan list markers
- Injects page anchors and inline external/internal links
- Cleans table-cell bullets and excess blank lines

## Output structure

- **Frontmatter:** YAML with title, author, pages; optional subject, creator.
- **Page anchors:** `<a id="page-N"></a>` for internal links.
- **Headings:** Inferred from font size (and bold when close to threshold).
- **Lists:** Bullets normalized to `- `; numbered/lettered preserved.
- **Tables:** Markdown `| ... |` with escaped pipes and newlines in cells.
- **Images:** `<img src="images/...">` with optional size style.
- **Links:** `[text](url)` or `[text](#page-N)`.
- **Annotations:** `> 💬 **Note:** ...` and `==**Highlight:** ...==`.

## Troubleshooting

- **PyMuPDF (fitz) required:** Install with `pip install pymupdf`.
- **PDF is password-protected:** Provide password via `--password` or `password=` in Python.
- **Invalid password:** Wrong password for an encrypted PDF.
- **Images not visible:** Ensure `--extract-images` (or `image_dir`) is set. Image paths in the Markdown are normalized to be **relative to the output .md file’s directory** (e.g. `images/page1_img0.png`), so the images folder must sit next to (or under) the .md file—e.g. `-o docs/report.md` and `--extract-images docs/images`.
- **Paths on Windows:** Use forward slashes in paths passed to the script or API when possible; the script normalizes image paths to `images/` for portability.
