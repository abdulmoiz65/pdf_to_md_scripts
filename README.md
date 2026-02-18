# PDF to Markdown Converter - Implementation Guide

This tool has two implementations:

## 📋 Implementations Comparison

### 1. **pdf_to_md.py** (Using pdfplumber)
- Excellent for text extraction
- Better at detecting text relationships
- Good for structured documents
- Slower processing speed
- Better layout preservation
- Dependencies: `pdfplumber`, `pypdf`, `Pillow`

### 2. **pdf_to_md_Using_pyMuPDF.py** (Using pyMuPDF/fitz)
- ⚡ Faster processing
- Better for image extraction
- Lightweight and efficient
- More flexible PDF manipulation
- Better performance on large files
- Dependencies: `pymupdf`, `Pillow`

---

## 🚀 Quick Start

### Installation

**Option 1: pyMuPDF (Recommended - Faster)**
```bash
pip install -r requirements_pymupdf.txt
```

**Option 2: pdfplumber**
```bash
pip install -r requirements.txt
```

### GUI Mode

**Using pyMuPDF:**
```bash
python pdf_to_md_Using_pyMuPDF.py --gui
```

**Using pdfplumber:**
```bash
python pdf_to_md.py --gui
```

### CLI Mode

**Convert PDF to Markdown:**
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf
```

**Extract images:**
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf --extract-images ./images
```

**Convert specific pages:**
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf --pages 1,3,5-8
```

**With page breaks:**
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf --page-breaks
```

**Full example:**
```bash
python pdf_to_md_Using_pyMuPDF.py report.pdf -o output.md --page-breaks --extract-images ./images --pages 1,5-10
```

---

## ✨ Features (Both Implementations)

### Text Processing
- ✅ Automatic heading detection (h1, h2, h3)
- ✅ List detection (bullets & numbered)
- ✅ Code block detection
- ✅ Indentation preservation
- ✅ Text formatting enhancement

### Images & Media
- 🖼️ Extract images from PDFs
- 📸 Auto-resize images (max 600x800px)
- 💾 Save to custom folder
- 🔗 Embed in Markdown

### Links & Metadata
- 🔗 Hyperlink extraction
- 📖 Bookmark detection
- 📋 Page breaks support

### Output
- 📄 Save to .md files
- 🎨 Clean formatting
- 📊 Multiple page support
- 🖨️ Print to stdout

---

## 🎯 When to Use Which?

### Use **pyMuPDF** if:
- ⚡ You need **fast processing**
- 📦 You want **lightweight dependencies**
- 🖼️ **Image extraction** is important
- 🔄 Processing **large PDFs** frequently
- 💾 **Disk space** is limited

### Use **pdfplumber** if:
- 📋 PDFs have **complex layouts**
- 📊 **Accurate text positioning** matters
- 🎯 Working with **structured documents**
- ✅ You need **high accuracy** on complex PDFs
- 📐 **Table detection** is important

---

## 📊 Performance Comparison

| Feature | pyMuPDF | pdfplumber |
|---------|---------|-----------|
| Speed | ⚡⚡⚡ | ⚡⚡ |
| Text Extraction | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Image Extraction | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Layout Preservation | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Dependency Size | Small | Medium |
| Memory Usage | Low | Medium |

---

## 🛠️ Advanced Usage

### Batch Processing
```bash
for file in *.pdf; do
    python pdf_to_md_Using_pyMuPDF.py "$file" --extract-images ./images
done
```

### Extract only pages 1-10
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf -o output.md --pages 1-10
```

### Print output to console
```bash
python pdf_to_md_Using_pyMuPDF.py input.pdf --print
```

---

## 🐛 Troubleshooting

### Installation Issues
```bash
# Clear pip cache and reinstall
pip cache purge
pip install --upgrade -r requirements_pymupdf.txt
```

### Image Extraction Not Working
- Ensure folder path exists
- Check write permissions
- Verify PDF has extractable images

### Text Not Converting Properly
- Try the alternative implementation
- Check if PDF is password-protected
- Verify PDF is not corrupted

---

## 📝 Examples

### Example 1: Simple Conversion
```bash
python pdf_to_md_Using_pyMuPDF.py document.pdf
# Creates: document.md
```

### Example 2: With Images
```bash
python pdf_to_md_Using_pyMuPDF.py document.pdf -o output.md --extract-images ./images
# Creates: output.md + images in ./images folder
```

### Example 3: Select Pages
```bash
python pdf_to_md_Using_pyMuPDF.py document.pdf --pages 1,2,3,5-8
# Converts pages 1,2,3,5,6,7,8
```

---

## 📚 Dependencies

**pyMuPDF Version:**
- `pymupdf` - PDF processing library
- `Pillow` - Image processing

**pdfplumber Version:**
- `pdfplumber` - PDF extraction
- `pypdf` - PDF manipulation
- `Pillow` - Image processing

---

## 💡 Tips

1. **GUI Mode** - Best for interactive use
2. **CLI Mode** - Best for automation and scripting
3. **Batch Processing** - Use with `--extract-images` for full content
4. **Large Files** - Consider using pyMuPDF for better performance
5. **Complex Layouts** - Use pdfplumber for more accurate results

---

## 🚀 Future Improvements

- [ ] OCR support for scanned PDFs
- [ ] Batch processing UI
- [ ] PDF annotation extraction
- [ ] Custom CSS for HTML export
- [ ] Parallel processing for large PDFs
- [ ] Configuration file support
- [ ] Dark mode GUI

---

## 📄 License

This tool is open source and free to use.

---

**Last Updated:** February 18, 2026  
**Current Version:** 2.0
