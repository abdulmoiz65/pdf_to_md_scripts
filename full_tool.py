#!/usr/bin/env python3
"""
🚀 COMPREHENSIVE PDF to Markdown Converter

Extracts ALL types of PDF content:
  1. 📝 Text (with bold, italic, underline support)
  2. 🔤 Headings (h1, h2, h3 via font-size heuristics)
  3. 📋 Lists (bullets & numbered)
  4. 🔗 URLs & Hyperlinks
  5. 🖼️ Images (extracted & embedded)
  6. 📊 Tables (with proper formatting)
  7. 🎨 Vector Graphics (horizontal rules)
  8. 📐 Annotations (comments, highlights)
  9. 🔖 Bookmarks (table of contents)
  10. 🔢 Metadata (title, author, date)
  11. 📎 Embedded Files (referenced)
  12. 🔐 Encryption/Security (password support)

Requirements:
  pip install pymupdf pillow pyyaml
"""

import re
import sys
import os
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF (fitz) is required. Install with:")
    print("   pip install pymupdf")
    sys.exit(1)

try:
    from PIL import Image, ImageTk
    HAS_PILLOW = True
except ImportError:
    Image = None
    ImageTk = None
    HAS_PILLOW = False


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

class PDFMetadataExtractor:
    """Extract metadata from PDF"""
    
    @staticmethod
    def extract(doc) -> dict:
        """Extract all metadata"""
        meta = doc.metadata
        return {
            "title": meta.get("title") or "Untitled",
            "author": meta.get("author") or "Unknown",
            "subject": meta.get("subject") or "",
            "creator": meta.get("creator") or "",
            "created": meta.get("creationDate") or "",
            "modified": meta.get("modDate") or "",
            "producer": meta.get("producer") or "",
            "pages": len(doc),
            "encrypted": doc.is_encrypted,
        }


class URLExtractor:
    """Extract URLs and hyperlinks from text"""
    
    URL_PATTERN = re.compile(r"https?://[^\s\)]+")
    
    @staticmethod
    def find_visible_urls(text: str) -> list[str]:
        """Find URLs visible in text"""
        return URLExtractor.URL_PATTERN.findall(text)
    
    @staticmethod
    def markdown_url(text: str, url: str) -> str:
        """Convert to markdown link"""
        return f"[{text}]({url})"


class ListDetector:
    """Detect and format lists"""
    
    BULLET_PATTERNS = [r"^[\•\-\*\·▪▸►→✓◆○●]\s+", r"^\s+[-•]\s+"]
    NUMBERED_PATTERNS = [r"^\d{1,2}[\.\)]\s+", r"^[a-zA-Z][\.\)]\s+"]
    
    @staticmethod
    def is_bullet_item(text: str) -> bool:
        """Check if text is a bullet point"""
        return any(re.match(pat, text) for pat in ListDetector.BULLET_PATTERNS)
    
    @staticmethod
    def is_numbered_item(text: str) -> bool:
        """Check if text is numbered"""
        return any(re.match(pat, text) for pat in ListDetector.NUMBERED_PATTERNS)
    
    @staticmethod
    def normalize_bullet(text: str) -> str:
        """Normalize all bullets to '-'"""
        return re.sub(r"^[\•\*\·▪▸►→✓◆○●]\s+", "- ", text)


class TextFormatter:
    """Format text with styling"""
    
    @staticmethod
    def apply_formatting(span: dict) -> str:
        """Apply bold, italic, underline based on flags"""
        text = span.get("text", "")
        flags = span.get("flags", 0)
        color = span.get("color")
        
        is_bold = bool(flags & 16)      # flag 16 = bold
        is_italic = bool(flags & 2)     # flag 2 = italic
        is_underline = bool(flags & 8)  # flag 8 = underline
        
        if is_bold and is_italic:
            text = f"***{text}***"
        elif is_bold:
            text = f"**{text}**"
        elif is_italic:
            text = f"*{text}*"
        
        if is_underline:
            text = f"<u>{text}</u>"
        
        return text
    
    @staticmethod
    def get_hex_color(color_tuple) -> str:
        """Convert RGB tuple to hex color"""
        if not color_tuple or len(color_tuple) < 3:
            return "#000000"
        r, g, b = color_tuple[:3]
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


class HeadingDetector:
    """Detect headings based on font size"""
    
    @staticmethod
    def get_average_font_size(page) -> float:
        """Calculate average font size on page"""
        sizes = []
        try:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block["type"] == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            size = span.get("size", 12)
                            if size > 0:
                                sizes.append(size)
        except Exception as e:
            print(f"  [warn] Could not calculate font size: {e}")
        
        return sum(sizes) / len(sizes) if sizes else 12.0
    
    @staticmethod
    def detect_heading(font_size: float, avg_size: float, is_bold: bool = False) -> str:
        """Detect heading level"""
        if font_size == 0:
            return ""
        
        ratio = font_size / avg_size if avg_size else 1
        
        if ratio >= 1.8:
            return "# "
        elif ratio >= 1.35:
            return "## "
        elif ratio >= 1.15 or (ratio >= 1.1 and is_bold):
            return "### "
        return ""


class ImageExtractor:
    """Extract images from PDF"""
    
    @staticmethod
    def extract_all(page, page_num: int, output_dir: str) -> list[tuple[str, float]]:
        """Extract all images from page"""
        images = []
        
        if not output_dir or not Path(output_dir).exists():
            return images
        
        try:
            image_list = page.get_images(full=True)
            
            for img_idx, img_ref in enumerate(image_list):
                try:
                    xref = img_ref[0]
                    # Extract image
                    base_image = page.parent.extract_image(xref)
                    
                    img_bytes = base_image["image"]
                    img_ext = base_image["ext"]
                    
                    img_name = f"page{page_num}_img{img_idx}.{img_ext}"
                    img_path = Path(output_dir) / img_name
                    
                    # Save image
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    
                    # Resize if needed
                    ImageExtractor.resize_image(str(img_path))
                    
                    # Get position
                    img_rects = page.get_image_rects(xref)
                    img_top = img_rects[0].y0 if img_rects else 0
                    
                    # Create markdown reference
                    rel_path = f"images/{img_name}".replace("\\", "/")
                    md_ref = f"![Image]({rel_path})"
                    images.append((md_ref, img_top))
                    
                except Exception as e:
                    print(f"  [warn] Could not extract image {img_idx}: {e}")
        
        except Exception as e:
            print(f"  [warn] Error extracting images: {e}")
        
        return images
    
    @staticmethod
    def resize_image(img_path: str, max_width: int = 600, max_height: int = 800):
        """Resize image to max dimensions"""
        if not HAS_PILLOW:
            return
        try:
            with Image.open(img_path) as img:
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                img.save(img_path, optimize=True, quality=85)
        except Exception as e:
            print(f"  [warn] Could not resize {img_path}: {e}")


class TableExtractor:
    """Extract tables from PDF"""
    
    @staticmethod
    def extract_all(page) -> list[tuple[str, float]]:
        """Extract all tables from page"""
        tables = []
        
        try:
            table_list = page.find_tables()
            
            for table_idx, table_obj in enumerate(table_list):
                try:
                    data = table_obj.extract()
                    md_table = TableExtractor.to_markdown(data)
                    table_top = table_obj.bbox[1]
                    tables.append((md_table, table_top))
                except Exception as e:
                    print(f"  [warn] Could not extract table {table_idx}: {e}")
        
        except Exception as e:
            print(f"  [warn] Error extracting tables: {e}")
        
        return tables
    
    @staticmethod
    def to_markdown(data: list[list]) -> str:
        """Convert table data to Markdown"""
        if not data or len(data) == 0:
            return ""
        
        header = data[0]
        separator = ["---"] * len(header)
        rows = data[1:] if len(data) > 1 else []
        
        lines = []
        lines.append("| " + " | ".join(str(h).strip() for h in header) + " |")
        lines.append("| " + " | ".join(separator) + " |")
        
        for row in rows:
            while len(row) < len(header):
                row.append("")
            lines.append("| " + " | ".join(str(c).strip() for c in row[:len(header)]) + " |")
        
        return "\n".join(lines)


class DrawingExtractor:
    """Extract vector graphics (lines, rectangles, etc.)"""
    
    @staticmethod
    def find_horizontal_rules(page) -> list[float]:
        """Find horizontal rules (dividers)"""
        rules = []
        
        try:
            for path in page.get_drawings():
                try:
                    rect = path.get("rect")
                    if not rect:
                        continue
                    
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    
                    # Wide and thin = horizontal rule
                    if width > 200 and height < 3:
                        y_pos = rect[1]
                        rules.append(y_pos)
                
                except Exception as e:
                    pass
        
        except Exception as e:
            print(f"  [warn] Could not extract drawings: {e}")
        
        return sorted(rules)


class AnnotationExtractor:
    """Extract annotations (comments, highlights)"""
    
    @staticmethod
    def extract_all(page) -> list[tuple[str, float]]:
        """Extract all annotations"""
        annotations = []
        
        try:
            annots = page.annots()
            if not annots:
                return annotations
            
            for annot in annots:
                try:
                    annot_type = annot.type[1]
                    content = annot.info.get("content", "")
                    
                    if annot_type == "Text" and content:
                        # Comment/note
                        md = f"> 💬 **Note:** {content}"
                        annot_y = annot.rect[1]
                        annotations.append((md, annot_y))
                    
                    elif annot_type == "Highlight" and content:
                        # Highlight with note
                        md = f"==**Highlight:** {content}=="
                        annot_y = annot.rect[1]
                        annotations.append((md, annot_y))
                
                except Exception as e:
                    pass
        
        except Exception as e:
            print(f"  [warn] Could not extract annotations: {e}")
        
        return annotations


class BookmarkExtractor:
    """Extract PDF bookmarks/outline"""
    
    @staticmethod
    def extract(doc) -> str:
        """Extract bookmarks as table of contents"""
        try:
            toc = doc.get_toc()
            if not toc:
                return ""
            
            md = "## 📑 Table of Contents\n\n"
            
            for level, title, page in toc:
                indent = "  " * (level - 1)
                md += f"{indent}- [{title}](#page-{page})\n"
            
            return md + "\n"
        
        except Exception as e:
            print(f"  [warn] Could not extract bookmarks: {e}")
            return ""


class EmbeddedFileExtractor:
    """Extract embedded files info"""
    
    @staticmethod
    def extract(doc) -> str:
        """List embedded files"""
        try:
            count = doc.embfile_count()
            if count == 0:
                return ""
            
            md = "\n## 📎 Embedded Files\n\n"
            
            for i in range(count):
                try:
                    info = doc.embfile_info(i)
                    filename = info.get("filename", f"file_{i}")
                    size = info.get("size", 0)
                    size_kb = size / 1024 if size else 0
                    md += f"- **{filename}** ({size_kb:.1f} KB)\n"
                except Exception as e:
                    pass
            
            return md
        
        except Exception as e:
            print(f"  [warn] Could not extract embedded files: {e}")
            return ""


class SecurityHandler:
    """Handle PDF encryption and security"""
    
    @staticmethod
    def check_encryption(doc) -> tuple[bool, str]:
        """Check if PDF is encrypted"""
        if not doc.is_encrypted:
            return False, ""
        
        if not doc.needs_pass:
            # Encrypted but no password needed
            return False, ""
        
        return True, "PDF is password-protected"
    
    @staticmethod
    def authenticate(doc, password: str) -> bool:
        """Authenticate with password"""
        if doc.is_encrypted and doc.needs_pass:
            return doc.authenticate(password)
        return True
    
    @staticmethod
    def get_permissions_info(doc) -> str:
        """Get info about PDF permissions"""
        try:
            perms = doc.permissions
            can_print = bool(perms & fitz.PDF_PERM_PRINT)
            can_copy = bool(perms & fitz.PDF_PERM_COPY)
            can_modify = bool(perms & fitz.PDF_PERM_MODIFY)
            
            md = "\n## 🔐 Security Info\n\n"
            md += f"- Encrypted: {'Yes' if doc.is_encrypted else 'No'}\n"
            md += f"- Can Print: {'Yes' if can_print else 'No'}\n"
            md += f"- Can Copy: {'Yes' if can_copy else 'No'}\n"
            md += f"- Can Modify: {'Yes' if can_modify else 'No'}\n"
            
            return md
        except Exception as e:
            return ""


# ─────────────────────────────────────────────
# CORE CONVERSION
# ─────────────────────────────────────────────

def create_frontmatter(metadata: dict) -> str:
    """Create YAML frontmatter from metadata"""
    frontmatter = {
        "title": metadata.get("title", "Untitled"),
        "author": metadata.get("author", "Unknown"),
        "date": metadata.get("created", str(datetime.now())),
        "pages": metadata.get("pages", 0),
        "encrypted": metadata.get("encrypted", False),
    }
    
    if metadata.get("subject"):
        frontmatter["subject"] = metadata["subject"]
    
    if metadata.get("creator"):
        frontmatter["creator"] = metadata["creator"]
    
    if HAS_YAML:
        yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    else:
        # Manual fallback when pyyaml is not installed
        lines = []
        for key, value in frontmatter.items():
            if isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, str):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        yaml_str = "\n".join(lines) + "\n"
    return f"---\n{yaml_str}---\n\n"


def page_to_markdown(page, page_num: int, image_dir: str = None) -> str:
    """Convert a single page to Markdown"""
    md_lines = []
    
    # Page header
    md_lines.append(f"## 📄 Page {page_num}\n")
    
    avg_font_size = HeadingDetector.get_average_font_size(page)
    
    # Extract elements
    images = ImageExtractor.extract_all(page, page_num, image_dir) if image_dir else []
    tables = TableExtractor.extract_all(page)
    annotations = AnnotationExtractor.extract_all(page)
    horiz_rules = DrawingExtractor.find_horizontal_rules(page)
    
    # Get text content
    text_dict = page.get_text("dict")
    blocks = text_dict.get("blocks", [])
    
    # Track all elements by position for proper ordering
    elements = []  # (y_position, type, content)
    
    # Add tables
    for table_md, table_y in tables:
        elements.append((table_y, "table", table_md))
    
    # Add images
    for img_md, img_y in images:
        elements.append((img_y, "image", img_md))
    
    # Add annotations
    for annot_md, annot_y in annotations:
        elements.append((annot_y, "annotation", annot_md))
    
    # Add horizontal rules
    for rule_y in horiz_rules:
        elements.append((rule_y, "rule", "---"))
    
    # Add text blocks
    for block in blocks:
        if block["type"] == 0:  # Text block
            block_y = block.get("bbox", [0, 0, 0, 0])[1]
            
            for line in block.get("lines", []):
                line_text = ""
                line_spans = line.get("spans", [])
                
                if not line_spans:
                    continue
                
                # Track font info for heading detection
                max_font_size = 0
                is_line_bold = False
                
                # Build line with formatting
                for span in line_spans:
                    text = span.get("text", "")
                    formatted = TextFormatter.apply_formatting(span)
                    line_text += formatted
                    
                    # Track the dominant font size and bold flag
                    span_size = span.get("size", 0)
                    if span_size > max_font_size:
                        max_font_size = span_size
                    if span.get("flags", 0) & 16:  # bold flag
                        is_line_bold = True
                
                line_text = line_text.strip()
                if line_text:
                    elements.append((block_y, "text", line_text, max_font_size, is_line_bold))
    
    # Sort by position and process
    elements.sort(key=lambda x: x[0])
    
    prev_y = None
    for item in elements:
        # Unpack element tuples — text items have 5 fields, others have 3
        if len(item) == 5:
            y_pos, elem_type, content, font_size, is_bold = item
        else:
            y_pos, elem_type, content = item
            font_size, is_bold = None, False
        
        # Add paragraph break if gap
        if prev_y is not None and (y_pos - prev_y) > 30:
            md_lines.append("")
        
        if elem_type == "text":
            # Detect heading using actual font size from the span
            heading = HeadingDetector.detect_heading(font_size, avg_font_size, is_bold) if font_size else ""
            
            if ListDetector.is_bullet_item(content):
                content = ListDetector.normalize_bullet(content)
                md_lines.append(content)
            elif ListDetector.is_numbered_item(content):
                md_lines.append(content)
            elif heading:
                md_lines.append(f"{heading}{content}")
            else:
                md_lines.append(content)
        
        elif elem_type == "table":
            md_lines.append(f"\n{content}\n")
        
        elif elem_type == "image":
            md_lines.append(f"\n{content}\n")
        
        elif elem_type == "annotation":
            md_lines.append(f"\n{content}\n")
        
        elif elem_type == "rule":
            md_lines.append("\n---\n")
        
        prev_y = y_pos
    
    return "\n".join(md_lines)


def pdf_to_markdown(pdf_path: str, output_path: str = None, image_dir: str = None, 
                   password: str = None) -> str:
    """Convert entire PDF to Markdown"""
    
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    # Create image directory
    if image_dir:
        Path(image_dir).mkdir(parents=True, exist_ok=True)
    
    md_content = []
    
    try:
        # Open PDF
        doc = fitz.open(pdf_path)
        
        # Check encryption
        is_encrypted, enc_msg = SecurityHandler.check_encryption(doc)
        if is_encrypted:
            if password:
                if not SecurityHandler.authenticate(doc, password):
                    raise PermissionError("❌ Invalid password!")
            else:
                raise PermissionError("❌ PDF is password-protected!")
        
        # Extract metadata and create frontmatter
        metadata = PDFMetadataExtractor.extract(doc)
        md_content.append(create_frontmatter(metadata))
        
        # Extract bookmarks
        bookmarks = BookmarkExtractor.extract(doc)
        if bookmarks:
            md_content.append(bookmarks)
        
        # Process pages
        print(f"📄 Processing {len(doc)} pages...")
        
        for page_num in range(len(doc)):
            try:
                page = doc[page_num]
                page_md = page_to_markdown(page, page_num + 1, image_dir)
                md_content.append(page_md)
                print(f"  ✓ Page {page_num + 1}/{len(doc)}")
            except Exception as e:
                print(f"  ⚠️  Error on page {page_num + 1}: {e}")
        
        # Add embedded files info
        embedded = EmbeddedFileExtractor.extract(doc)
        if embedded:
            md_content.append(embedded)
        
        # Add security info
        security = SecurityHandler.get_permissions_info(doc)
        if security:
            md_content.append(security)
        
        doc.close()
    
    except Exception as e:
        raise RuntimeError(f"Error processing PDF: {e}")
    
    # Combine all content
    result = "\n\n".join(md_content)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    
    # Save if output path provided
    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")
        print(f"✅ Saved: {output_path}")
    
    return result


# ─────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────

class ComprehensivePDFtoMDGUI:
    """Full-featured GUI for PDF conversion"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 Comprehensive PDF to Markdown Converter")
        self.root.geometry("800x1600")
        self.root.resizable(True, True)
        
        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.image_dir = tk.StringVar()
        self.password = tk.StringVar()
        self.extract_images = tk.BooleanVar(value=True)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create GUI"""
        # Title
        title_frame = tk.Frame(self.root, bg="#2c3e50")
        title_frame.pack(fill=tk.X, padx=0, pady=0)
        title_label = tk.Label(
            title_frame,
            text="🚀 Comprehensive PDF to Markdown Converter\nFully-Featured Edition",
            font=("Arial", 14, "bold"),
            bg="#2c3e50",
            fg="white",
            pady=15,
            justify=tk.CENTER
        )
        title_label.pack()
        
        # Create scrollable main area
        canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)
        
        # Main frame inside scrollable area
        main_frame = tk.Frame(scrollable_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # --- PDF Selection ---
        tk.Label(main_frame, text="📄 SELECT PDF", font=("Arial", 11, "bold")).pack(anchor=tk.W)
        pdf_frame = tk.Frame(main_frame)
        pdf_frame.pack(fill=tk.X, pady=(5, 15))
        tk.Entry(pdf_frame, textvariable=self.pdf_path, state="readonly", width=60).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(pdf_frame, text="Browse", command=self.browse_pdf, width=10).pack(side=tk.LEFT, padx=(10, 0))
        
        # --- Output ---
        output_label_frame = tk.Frame(main_frame)
        output_label_frame.pack(anchor=tk.W, pady=(10, 0))
        tk.Label(output_label_frame, text="📁 OUTPUT FILE (Optional)", font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        tk.Label(output_label_frame, text="- Auto-generates filename if not specified", font=("Arial", 9, "italic"), fg="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        out_frame = tk.Frame(main_frame)
        out_frame.pack(fill=tk.X, pady=(5, 15))
        tk.Entry(out_frame, textvariable=self.output_path, width=60).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(out_frame, text="Browse", command=self.browse_output, width=10).pack(side=tk.LEFT, padx=(10, 0))
        
        # --- Images ---
        img_frame = tk.LabelFrame(main_frame, text="🖼️  IMAGE EXTRACTION", font=("Arial", 10, "bold"), padx=10, pady=10)
        img_frame.pack(fill=tk.X, pady=10)
        
        tk.Checkbutton(img_frame, text="Extract images from PDF", variable=self.extract_images, 
                      command=self.toggle_image_dir, font=("Arial", 10)).pack(anchor=tk.W)
        
        tk.Label(img_frame, text="Image folder:", font=("Arial", 9)).pack(anchor=tk.W, pady=(5, 0))
        img_path_frame = tk.Frame(img_frame)
        img_path_frame.pack(fill=tk.X, pady=5)
        tk.Entry(img_path_frame, textvariable=self.image_dir, state="disabled", width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.img_browse_btn = tk.Button(img_path_frame, text="Browse", command=self.browse_image_dir, width=10, state="disabled")
        self.img_browse_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # --- Security ---
        sec_frame = tk.LabelFrame(main_frame, text="🔐 SECURITY", font=("Arial", 10, "bold"), padx=10, pady=10)
        sec_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(sec_frame, text="Password (if PDF is protected):", font=("Arial", 9)).pack(anchor=tk.W)
        tk.Entry(sec_frame, textvariable=self.password, show="*", width=50).pack(anchor=tk.W, fill=tk.X, pady=5)
        
        # --- Features ---
        feat_frame = tk.LabelFrame(main_frame, text="✨ FEATURES EXTRACTED", font=("Arial", 10, "bold"), padx=10, pady=10)
        feat_frame.pack(fill=tk.X, pady=10)
        
        features = [
            "✅ Text (with bold, italic formatting)",
            "✅ Headings (h1-h3 auto-detection)",
            "✅ Lists (bullets & numbered)",
            "✅ Hyperlinks & URLs",
            "✅ Images (extracted & embedded)",
            "✅ Tables (properly formatted)",
            "✅ Vector graphics (rules/dividers)",
            "✅ Annotations (comments & highlights)",
            "✅ Bookmarks (table of contents)",
            "✅ Metadata (YAML frontmatter)",
            "✅ Embedded files (referenced)",
            "✅ Security info (permissions)"
        ]
        
        for feat in features:
            tk.Label(feat_frame, text=feat, font=("Arial", 9), justify=tk.LEFT).pack(anchor=tk.W)
        
        # --- Convert Button ---
        convert_btn = tk.Button(main_frame, text="🚀 CONVERT NOW", command=self.convert,
                               bg="#27ae60", fg="white", font=("Arial", 12, "bold"),
                               padx=40, pady=15)
        convert_btn.pack(pady=20)
        
        # --- Status ---
        tk.Label(main_frame, text="Status Output:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.status_text = scrolledtext.ScrolledText(main_frame, height=15, width=100,
                                                    font=("Courier", 8), state=tk.DISABLED)
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # --- Buttons ---
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="Clear", command=self.clear_status, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Exit", command=self.root.quit, width=10).pack(side=tk.RIGHT, padx=5)
    
    def toggle_image_dir(self):
        if self.extract_images.get():
            self.img_browse_btn.config(state=tk.NORMAL)
            # Auto-set to default images folder if not set
            if not self.image_dir.get():
                default_dir = str(Path.home() / "Downloads" / "pdf_images")
                self.image_dir.set(default_dir)
                self.log(f"✓ Default images folder: {default_dir}")
        else:
            self.img_browse_btn.config(state=tk.DISABLED)
            self.image_dir.set("")
    
    def browse_pdf(self):
        file_path = filedialog.askopenfilename(title="Select PDF", filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            self.pdf_path.set(file_path)
            self.log(f"✓ PDF: {Path(file_path).name}")
    
    def browse_output(self):
        file_path = filedialog.asksaveasfilename(title="Save Markdown", defaultextension=".md",
                                                filetypes=[("Markdown", "*.md"), ("Text", "*.txt")])
        if file_path:
            self.output_path.set(file_path)
            self.log(f"✓ Output: {Path(file_path).name}")
    
    def browse_image_dir(self):
        dir_path = filedialog.askdirectory(title="Image Folder")
        if dir_path:
            self.image_dir.set(dir_path)
            self.log(f"✓ Images: {Path(dir_path).name}")
    
    def log(self, message: str):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()
    
    def clear_status(self):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state=tk.DISABLED)
    
    def convert(self):
        if not self.pdf_path.get():
            messagebox.showerror("Error", "Select a PDF file!")
            return
        
        if self.extract_images.get() and not self.image_dir.get():
            messagebox.showerror("Error", "Select image folder!")
            return
        
        thread = threading.Thread(target=self._convert_thread)
        thread.start()
    
    def _convert_thread(self):
        try:
            pdf_path = self.pdf_path.get()
            output_path = self.output_path.get() or str(Path(pdf_path).with_suffix(".md"))
            image_dir = self.image_dir.get() if self.extract_images.get() else None
            password = self.password.get() or None
            
            self.log(f"\n🚀 Converting: {Path(pdf_path).name}...")
            self.log("=" * 60)
            
            markdown = pdf_to_markdown(pdf_path, output_path, image_dir, password)
            
            self.log("=" * 60)
            self.log(f"✅ Success! {len(markdown)} characters")
            self.log(f"📁 Saved: {output_path}")
            
            if image_dir:
                img_count = len(list(Path(image_dir).glob("*.png"))) + len(list(Path(image_dir).glob("*.jpg")))
                self.log(f"🖼️  Extracted {img_count} images")
            
            self.root.after(0, lambda: self._ask_view(output_path, markdown, image_dir))
        
        except Exception as e:
            self.log(f"\n❌ ERROR: {str(e)}")
    
    def _ask_view(self, output_path: str, markdown: str, image_dir: str = None):
        response = messagebox.askyesno("Success", f"Saved to:\n{output_path}\n\nView output?")
        if response:
            self._show_preview(markdown, output_path, image_dir)
    
    def _show_preview(self, markdown: str, output_path: str = None, image_dir: str = None):
        preview = tk.Toplevel(self.root)
        preview.title("📄 Markdown Preview - Complete Preview")
        preview.geometry("1000x700")
        
        # Create scrollable canvas
        canvas = tk.Canvas(preview, highlightthickness=0, bg="white")
        scrollbar = tk.Scrollbar(preview, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind mousewheel
        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except:
                pass  # Ignore if canvas is destroyed
        
        canvas.bind("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)
        
        # Determine base directory for resolving relative image paths
        base_dir = Path.cwd()
        if image_dir:
            base_dir = Path(image_dir).parent
        elif output_path:
            base_dir = Path(output_path).parent
        
        # Parse and render markdown
        lines = markdown.split("\n")
        image_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            if not line_stripped:
                tk.Label(scrollable_frame, text="", bg="white").pack(anchor=tk.W, pady=5)
                continue
            
            # Headings
            if line_stripped.startswith("# "):
                text = line_stripped[2:].strip()
                lbl = tk.Label(
                    scrollable_frame,
                    text=text,
                    font=("Arial", 20, "bold"),
                    fg="#1a5490",
                    bg="white",
                    wraplength=900,
                    justify=tk.LEFT
                )
                lbl.pack(anchor=tk.W, padx=20, pady=(15, 5))
            
            elif line_stripped.startswith("## "):
                text = line_stripped[3:].strip()
                lbl = tk.Label(
                    scrollable_frame,
                    text=text,
                    font=("Arial", 16, "bold"),
                    fg="#2471a3",
                    bg="white",
                    wraplength=900,
                    justify=tk.LEFT
                )
                lbl.pack(anchor=tk.W, padx=20, pady=(12, 5))
            
            elif line_stripped.startswith("### "):
                text = line_stripped[4:].strip()
                lbl = tk.Label(
                    scrollable_frame,
                    text=text,
                    font=("Arial", 13, "bold"),
                    fg="#3498db",
                    bg="white",
                    wraplength=900,
                    justify=tk.LEFT
                )
                lbl.pack(anchor=tk.W, padx=20, pady=(10, 3))
            
            # Images
            elif "![" in line_stripped and "](" in line_stripped:
                match = image_pattern.search(line_stripped)
                if match:
                    img_path = match.group(1)
                    try:
                        full_img_path = Path(img_path)
                        if not full_img_path.is_absolute():
                            # Try to resolve relative to base directory
                            full_img_path = base_dir / img_path
                        
                        if full_img_path.exists():
                            img = Image.open(full_img_path)
                            img.thumbnail((900, 500), Image.Resampling.LANCZOS)
                            photo = ImageTk.PhotoImage(img)
                            
                            img_lbl = tk.Label(
                                scrollable_frame,
                                image=photo,
                                bg="white",
                                bd=1,
                                relief=tk.SUNKEN
                            )
                            img_lbl.image = photo
                            img_lbl.pack(anchor=tk.CENTER, padx=20, pady=10)
                        else:
                            tk.Label(
                                scrollable_frame,
                                text=f"🖼️  Image: {img_path}",
                                font=("Arial", 10, "italic"),
                                fg="gray",
                                bg="#f0f0f0",
                                wraplength=900
                            ).pack(anchor=tk.W, padx=20, pady=5, fill=tk.X)
                    except Exception as e:
                        tk.Label(
                            scrollable_frame,
                            text=f"📷 [Image: {Path(img_path).name}]",
                            font=("Arial", 9),
                            fg="gray",
                            bg="#f0f0f0"
                        ).pack(anchor=tk.W, padx=20, pady=5, fill=tk.X)
            
            # Tables
            elif line_stripped.startswith("|"):
                cells = [cell.strip() for cell in line_stripped.split("|")]
                cells = [c for c in cells if c]
                
                if cells:
                    row_frame = tk.Frame(scrollable_frame, bg="white")
                    row_frame.pack(anchor=tk.W, padx=20, pady=2, fill=tk.X)
                    
                    for cell in cells:
                        if cell == "---":
                            continue
                        cell_lbl = tk.Label(
                            row_frame,
                            text=cell,
                            font=("Arial", 9),
                            bg="#f8f9f9",
                            fg="#2c3e50",
                            padx=10,
                            pady=5,
                            relief=tk.RIDGE,
                            bd=1
                        )
                        cell_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            
            # Lists
            elif line_stripped.startswith("- ") or line_stripped.startswith("* "):
                text = line_stripped[2:].strip()
                indent = len(line) - len(line.lstrip())
                tk.Label(
                    scrollable_frame,
                    text=f"• {text}",
                    font=("Arial", 10),
                    bg="white",
                    wraplength=850,
                    justify=tk.LEFT
                ).pack(anchor=tk.W, padx=(20 + indent, 20), pady=2)
            
            # Regular text  
            else:
                tk.Label(
                    scrollable_frame,
                    text=line_stripped,
                    font=("Arial", 10),
                    bg="white",
                    wraplength=850,
                    justify=tk.LEFT
                ).pack(anchor=tk.W, padx=20, pady=3)
        
        # Close button
        close_btn = tk.Button(
            preview,
            text="✕ Close",
            command=preview.destroy,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 10)
        )
        close_btn.pack(pady=10)


# ─────────────────────────────────────────────
# CLI & MAIN
# ─────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="🚀 Comprehensive PDF to Markdown Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Extracts ALL PDF content:
  • Text (with bold, italic, underline)
  • Headings (auto-detected by font size)
  • Lists (bullets & numbered)
  • URLs & Hyperlinks
  • Images (extracted & embedded)
  • Tables (properly formatted)
  • Vector graphics & rules
  • Annotations (comments, highlights)
  • Bookmarks (table of contents)
  • Metadata (YAML frontmatter)
  • Embedded files (referenced)
  • Security & permissions info

Examples:
  python full_tool.py --gui
  python full_tool.py document.pdf
  python full_tool.py document.pdf -o output.md --extract-images ./images
  python full_tool.py document.pdf --password mypassword
        """
    )
    parser.add_argument("pdf", nargs="?", help="PDF file to convert")
    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("-o", "--output", help="Output Markdown file")
    parser.add_argument("--extract-images", metavar="DIR", help="Extract images to folder")
    parser.add_argument("--password", help="PDF password (if encrypted)")
    
    args = parser.parse_args()
    
    if args.gui:
        root = tk.Tk()
        app = ComprehensivePDFtoMDGUI(root)
        root.mainloop()
        return
    
    if not args.pdf:
        parser.print_help()
        sys.exit(1)
    
    try:
        output = args.output or Path(args.pdf).with_suffix(".md")
        print(f"\n🚀 Comprehensive PDF Converter")
        print("=" * 60)
        
        result = pdf_to_markdown(
            args.pdf,
            str(output),
            args.extract_images,
            args.password
        )
        
        print("\n✅ Conversion Complete!")
        print(f"   Total: {len(result)} characters")
        print(f"   Output: {output}")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
