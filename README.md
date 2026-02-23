# PDF to Markdown Converter - Full Tool

A comprehensive PDF to Markdown converter that extracts **all 12 types** of content: text, headings, lists, hyperlinks, images, tables, graphics, annotations, bookmarks, metadata, embedded files, and security info.

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Usage

**Convert a PDF:**
```bash
python full_tool.py document.pdf
```

**With custom output and images:**
```bash
python full_tool.py document.pdf -o output.md --extract-images ./images
```

**Password-protected PDF:**
```bash
python full_tool.py secure.pdf --password mypassword
```

Output is saved under `converted/<pdf_name>/` by default.

## 📚 Documentation

See **[FULL_TOOL_GUIDE.md](FULL_TOOL_GUIDE.md)** for complete documentation.

## 📦 Dependencies

- `pymupdf` - PDF processing
- `Pillow` - Image extraction and resizing
- `PyYAML` - Metadata frontmatter
