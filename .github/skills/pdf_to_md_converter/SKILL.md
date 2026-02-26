---
name: pdf-to-md-converter
description: Converts PDF documents to clean, structured Markdown with text formatting, headings, lists, hyperlinks, images, tables, annotations, bookmarks, and metadata. Use when the user needs to convert PDFs to Markdown, extract PDF content as Markdown, or work with PDF-to-MD conversion, encrypted PDFs, or document extraction.
---

# PDF to Markdown Conversion

## When to use this skill

Use this skill when the user:
- Wants to convert a PDF file to Markdown
- Needs to extract text, tables, or images from a PDF into Markdown
- Asks about PDF-to-MD conversion, PDF extraction, or document conversion
- Works with encrypted PDFs and needs password handling
- Needs structured output (headings, lists, links, TOC) from a PDF

## Quick start

1. **Install** (required): `pip install pymupdf`
2. **Recommended** (for full extraction): `pip install pymupdf4llm Pillow PyYAML`
3. **Run** from repository root:

```bash
python .github/skills/pdf_to_md_converter/scripts/pdf_to_md_converter.py path/to/document.pdf -o output.md --extract-images ./images
```

Or from the skill directory:

```bash
cd .github/skills/pdf_to_md_converter
python scripts/pdf_to_md_converter.py path/to/document.pdf -o output.md --extract-images ./images
```

## How to run the converter

**CLI usage:**

```bash
python scripts/pdf_to_md_converter.py <pdf_path> [-o OUTPUT] [--extract-images DIR] [--password PASSWORD]
```

| Argument | Description |
|----------|-------------|
| `pdf` | Path to the PDF file (positional) |
| `-o`, `--output` | Output Markdown file path |
| `--extract-images DIR` | Directory to save extracted images |
| `--password` | Password for encrypted PDFs |

**Default behavior (no `-o`):** Output is written to `converted/<pdf_stem>/<pdf_stem>.md` relative to the script’s directory. Prefer `-o` and `--extract-images` when running from repo root for predictable paths.

**Examples:**

```bash
# Basic conversion (output under converted/...)
python scripts/pdf_to_md_converter.py document.pdf

# Explicit output and images
python scripts/pdf_to_md_converter.py document.pdf -o docs/report.md --extract-images docs/images

# Encrypted PDF
python scripts/pdf_to_md_converter.py secure.pdf --password mypassword -o out.md
```

## How to extract text / convert a PDF

1. Install `pymupdf` and the recommended stack: `pymupdf4llm`, `Pillow`, `PyYAML`.
2. Run the script with the PDF path. Use `-o` for the desired output path and `--extract-images` for image extraction.
3. For encrypted PDFs, pass `--password`; otherwise the tool exits with "PDF is password-protected".

The tool uses **pymupdf4llm** for extraction, producing Markdown with headings, lists, links, tables, and optional images.

## How to use from Python

Import and call the main conversion function:

```python
import sys
sys.path.insert(0, ".github/skills/pdf_to_md_converter/scripts")
from pdf_to_md_converter import pdf_to_markdown

md_text = pdf_to_markdown(
    pdf_path="path/to/file.pdf",
    output_path="path/to/output.md",  # optional
    image_dir="path/to/images",       # optional
    password="secret"                 # optional, for encrypted PDFs
)
```

Returns the full Markdown string; writes to `output_path` if provided.

## Output and features

- **Metadata:** YAML frontmatter (title, author, pages, subject, creator)
- **Structure:** Headings (by font size), bullet/numbered lists, Markdown tables
- **Links:** External URLs and internal page links (`#page-N`)
- **Images:** Extracted to a folder and referenced in Markdown (`images/` relative path)
- **Annotations:** Comments and highlights as blockquotes/highlights
- **Bookmarks:** PDF outline as a Markdown table of contents
- **Encryption:** Password authentication and permission summary

## Troubleshooting

| Issue | Action |
|-------|--------|
| "PyMuPDF (fitz) is required" | `pip install pymupdf` |
| "PDF is password-protected" | Pass `--password` or provide `password=` in Python |
| "Invalid password" | Wrong password for encrypted PDF |
| Images not showing in output | Use `--extract-images DIR` and keep the .md file and images as siblings (e.g. `-o docs/report.md` and `--extract-images docs/images` so paths like `images/page1_img0.png` resolve from `docs/`). Paths in the .md are normalized relative to the output file. |
| Missing pymupdf4llm / poor output | Install recommended stack: `pip install pymupdf4llm Pillow PyYAML` |

## Additional resources

- Full tool behavior, extractors, and API: [references/complete-guide.md](references/complete-guide.md)
