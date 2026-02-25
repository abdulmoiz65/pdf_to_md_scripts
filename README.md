# 📄 PDF to Markdown Converter

A single-file Python tool that converts PDF documents into clean, well-structured Markdown with images, tables, links, and formatting preserved.

## ✨ Features

- **Text & Formatting** — Bold, italic, underline preserved as Markdown
- **Headings** — Auto-detected via font-size heuristics (H1–H3)
- **Lists** — Bullets and numbered lists normalized to proper Markdown
- **Hyperlinks** — External URLs and internal cross-references (`#page-N`)
- **Images** — Extracted to a separate `images/` directory with relative paths
- **Tables** — Converted to Markdown table syntax
- **Annotations** — Comments and highlights included as blockquotes
- **Bookmarks / TOC** — PDF outline converted to linked Table of Contents
- **Metadata** — Title, author, pages emitted as YAML frontmatter
- **Embedded Files** — Attached files listed with filenames and sizes
- **Encryption** — Password-protected PDFs fully supported

---

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Usage

```bash
python pdf_to_md_converter.py pdfs/your_document.pdf
```

Output is saved to `converted/<pdf_name>/<pdf_name>.md` with images in `converted/<pdf_name>/images/`.

### Other Options

```bash
# Password-protected PDF
python pdf_to_md_converter.py pdfs/secure.pdf --password mypassword

# Custom output path and image directory
python pdf_to_md_converter.py pdfs/report.pdf -o output.md --extract-images ./my_images
```

---

## 📁 Project Structure

```
tool/
├── pdf_to_md_converter.py   # Main converter script
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── converted/                # Default output directory (auto-created)
│   └── <pdf_name>/
│       ├── <pdf_name>.md     # Converted Markdown
│       └── images/           # Extracted images
└── pdfs/                     # Place your input PDFs here
```

---

## ⚙️ CLI Reference

| Argument | Description |
|---|---|
| `pdf` | Path to the PDF file to convert |
| `-o`, `--output` | Custom output Markdown file path |
| `--extract-images DIR` | Custom directory for extracted images |
| `--password` | Password for encrypted PDFs |

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `pymupdf` ≥ 1.23.0 | Core PDF parsing, text/table extraction, link detection |
| `pymupdf4llm` | Image extraction, layout-aware Markdown generation |
| `Pillow` ≥ 10.0.0 | Image resizing and optimization |
| `PyYAML` ≥ 6.0 | YAML metadata frontmatter generation |

Install all at once:

```bash
pip install -r requirements.txt
```

---

## 📝 Output Format

The generated Markdown includes:

```markdown
---
title: "Document Title"
author: "Author Name"
pages: 42
---

<a id="page-1"></a>

# Document Title

Body text with **bold**, *italic*, and [hyperlinks](https://example.com).

- Bullet point one
- Bullet point two

| Column A | Column B |
|----------|----------|
| Cell 1   | Cell 2   |

![](images/page1_img0.png)
```

---

## 📄 License

This project is provided as-is for internal use.
