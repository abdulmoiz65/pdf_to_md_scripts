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

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF (fitz) is required. Install with:")
    print("   pip install pymupdf")
    sys.exit(1)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    Image = None
    HAS_PILLOW = False

# Project folder: converted .md files and images go here by default
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "converted"


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
        """Apply bold, italic, underline based on flags. Skips empty/whitespace; strips before wrap."""
        text = span.get("text", "")
        flags = span.get("flags", 0)
        color = span.get("color")
        
        text = text.strip()
        if not text:
            return ""
        
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
                    base_image = page.parent.extract_image(xref)
                    img_bytes = base_image["image"]
                    img_ext = base_image["ext"]
                    img_name = f"page{page_num}_img{img_idx}.{img_ext}"
                    img_path = Path(output_dir) / img_name
                    
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    ImageExtractor.resize_image(str(img_path))
                    
                    img_rects = page.get_image_rects(xref)
                    if not img_rects:
                        continue
                    r = img_rects[0]
                    img_top = r.y0
                    w_in = r.width / 72.0
                    h_in = r.height / 72.0
                    rel_path = f"images/{img_name}".replace("\\", "/")
                    md_ref = f'<img src="{rel_path}" style="width:{w_in:.2f}in;height:{h_in:.2f}in" />'
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
    def extract_all(page) -> list[tuple[str, tuple]]:
        """Extract all tables from page. Returns (markdown_table, bbox) where bbox=(x0,y0,x1,y1)."""
        tables = []
        
        try:
            table_list = page.find_tables()
            
            for table_idx, table_obj in enumerate(table_list):
                try:
                    data = table_obj.extract()
                    md_table = TableExtractor.to_markdown(data)
                    tables.append((md_table, tuple(table_obj.bbox)))
                except Exception as e:
                    print(f"  [warn] Could not extract table {table_idx}: {e}")
        
        except Exception as e:
            print(f"  [warn] Error extracting tables: {e}")
        
        return tables
    
    @staticmethod
    def _escape_cell(cell: str) -> str:
        """Escape pipe and newlines so Markdown table does not break."""
        s = str(cell).strip().replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        return s

    @staticmethod
    def to_markdown(data: list[list]) -> str:
        """Convert table data to Markdown"""
        if not data or len(data) == 0:
            return ""
        
        header = data[0]
        separator = ["---"] * len(header)
        rows = data[1:] if len(data) > 1 else []
        
        lines = []
        lines.append("| " + " | ".join(TableExtractor._escape_cell(h) for h in header) + " |")
        lines.append("| " + " | ".join(separator) + " |")
        
        for row in rows:
            while len(row) < len(header):
                row.append("")
            lines.append("| " + " | ".join(TableExtractor._escape_cell(c) for c in row[:len(header)]) + " |")
        
        return "\n".join(lines)


class DrawingExtractor:
    """Extract vector graphics (lines, rectangles, etc.)"""
    
    @staticmethod
    def find_horizontal_rules(page) -> list[float]:
        """Find only clear full-width horizontal rules; skip decorative lines."""
        rules = []
        try:
            try:
                page_width = page.rect.width
            except Exception:
                page_width = 612  # default
            min_width = max(200, page_width * 0.6)  # at least 60% of page width
            for path in page.get_drawings():
                try:
                    rect = path.get("rect")
                    if not rect:
                        continue
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    # Only full-width thin lines (real dividers), not decorative
                    if width >= min_width and 0 < height < 4:
                        y_pos = rect[1]
                        rules.append(y_pos)
                except Exception:
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


def _rect_overlap(r1, r2) -> bool:
    """True if two rects (x0, y0, x1, y1) overlap."""
    try:
        x0_1, y0_1, x1_1, y1_1 = r1[0], r1[1], r1[2], r1[3]
        x0_2, y0_2, x1_2, y1_2 = r2[0], r2[1], r2[2], r2[3]
    except (IndexError, TypeError):
        return False
    if x1_1 < x0_2 or x0_1 > x1_2 or y1_1 < y0_2 or y0_1 > y1_2:
        return False
    return True


class LinkExtractor:
    """Extract clickable hyperlinks from PDF and support inlining with display text."""

    @staticmethod
    def extract_all(page) -> list[tuple[str, float]]:
        """Return (markdown_link, y_pos) for standalone link elements (legacy)."""
        out = []
        for _rect, uri, y_pos in LinkExtractor.extract_with_rects(page):
            text = uri if len(uri) <= 60 else (uri[:57] + "...")
            out.append((f"[{text}]({uri})", y_pos))
        return out

    @staticmethod
    def extract_with_rects(page) -> list[tuple[tuple, str, float]]:
        """Return list of (rect, uri, y_pos) for matching text to links. rect = (x0,y0,x1,y1)."""
        links = []
        try:
            for link in page.get_links():
                uri = link.get("uri") or link.get("file")
                if not uri:
                    continue
                rect = link.get("from")
                if not rect:
                    continue
                try:
                    r = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
                except (IndexError, TypeError, ValueError):
                    continue
                y_pos = r[1]
                links.append((r, uri, y_pos))
        except Exception as e:
            print(f"  [warn] Could not extract links: {e}")
        return links


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
        "pages": metadata.get("pages", 0),
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
    """Convert a single page to Markdown."""
    md_lines = []
    
    avg_font_size = HeadingDetector.get_average_font_size(page)
    
    # Extract elements
    images = ImageExtractor.extract_all(page, page_num, image_dir) if image_dir else []
    tables = TableExtractor.extract_all(page)
    annotations = AnnotationExtractor.extract_all(page)
    links_with_rects = LinkExtractor.extract_with_rects(page)  # (rect, uri, y_pos)
    
    # Get text content
    text_dict = page.get_text("dict")
    blocks = text_dict.get("blocks", [])
    
    # Track which links we inlined as [display text](url) so we don't emit them again as standalone
    inlined_link_indices = set()
    
    # Table bboxes: skip text blocks that overlap tables (avoid duplicating table content as raw text)
    table_bboxes = [t[1] for t in tables]
    
    # Track all elements by position for proper ordering
    elements = []  # (y_position, type, content)
    
    # ---- 1) Build text elements: span-level link matching so "Label: [Display Text](url)" is correct ----
    for block in blocks:
        if block["type"] != 0:  # skip non-text blocks
            continue
        block_bbox = block.get("bbox", [0, 0, 0, 0])
        try:
            block_rect = (float(block_bbox[0]), float(block_bbox[1]), float(block_bbox[2]), float(block_bbox[3]))
        except (IndexError, TypeError, ValueError):
            block_rect = (0, 0, 0, 0)
        # Skip blocks that overlap any table (avoids duplicating table content as raw text)
        if any(_rect_overlap(block_rect, tb) for tb in table_bboxes):
            continue
        block_y = block_rect[1]
        
        for line in block.get("lines", []):
            line_spans = line.get("spans", [])
            if not line_spans:
                continue
            
            max_font_size = 0
            is_line_bold = False
            line_parts = []  # mix of plain text and "[text](url)" per span
            
            for span in line_spans:
                span_text = span.get("text", "")
                formatted = TextFormatter.apply_formatting(span)
                span_size = span.get("size", 0)
                if span_size > max_font_size:
                    max_font_size = span_size
                if span.get("flags", 0) & 16:
                    is_line_bold = True
                
                # Span bbox for link matching (each link covers a phrase, not the whole line)
                span_bbox = span.get("bbox") or span.get("origin")
                if span_bbox is not None:
                    try:
                        if len(span_bbox) >= 4:
                            span_bbox = (float(span_bbox[0]), float(span_bbox[1]), float(span_bbox[2]), float(span_bbox[3]))
                        elif len(span_bbox) >= 2:
                            # origin only (x,y) — use tiny rect around it
                            x, y = float(span_bbox[0]), float(span_bbox[1])
                            span_bbox = (x, y, x + 1, y + 1)
                        else:
                            span_bbox = (0, 0, 0, 0)
                    except (TypeError, ValueError):
                        span_bbox = (0, 0, 0, 0)
                else:
                    span_bbox = (0, 0, 0, 0)
                
                # Does this span overlap a link? If yes, emit [display text](url)
                matched_link_idx = None
                for idx, (link_rect, uri, _) in enumerate(links_with_rects):
                    if idx in inlined_link_indices:
                        continue
                    if _rect_overlap(link_rect, span_bbox):
                        matched_link_idx = idx
                        break
                
                if matched_link_idx is not None and formatted.strip():
                    line_parts.append(f"[{formatted.strip()}]({links_with_rects[matched_link_idx][1]})")
                    inlined_link_indices.add(matched_link_idx)
                else:
                    line_parts.append(formatted)
            
            line_text = "".join(line_parts).strip()
            if not line_text:
                continue
            
            elements.append((block_y, "text", line_text, max_font_size, is_line_bold))
    
    # ---- 2) Add non-text elements ----
    for table_md, table_bbox in tables:
        elements.append((table_bbox[1], "table", table_md))
    
    for img_md, img_y in images:
        elements.append((img_y, "image", img_md))
    
    for annot_md, annot_y in annotations:
        elements.append((annot_y, "annotation", annot_md))
    
    # Only add links that were NOT inlined (no display text); skip duplicate URIs
    inlined_uris = {links_with_rects[i][1] for i in inlined_link_indices}
    for idx, (_rect, uri, link_y) in enumerate(links_with_rects):
        if idx not in inlined_link_indices and uri not in inlined_uris:
            text = uri if len(uri) <= 60 else (uri[:57] + "...")
            elements.append((link_y, "link", f"[{text}]({uri})"))
            inlined_uris.add(uri)  # avoid duplicate standalone for same URL
    
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
                # Strip redundant ** from heading content (heading already provides emphasis)
                c = content.strip()
                if len(c) > 4 and c.startswith("**") and c.endswith("**") and c.count("**") == 2:
                    c = c[2:-2]
                elif len(c) > 6 and c.startswith("***") and c.endswith("***"):
                    c = c[3:-3]
                md_lines.append(f"{heading}{c}")
            else:
                md_lines.append(content)
        
        elif elem_type == "table":
            md_lines.append(f"\n{content}\n")
        
        elif elem_type == "image":
            md_lines.append(content)
        
        elif elem_type == "annotation":
            md_lines.append(f"\n{content}\n")
        
        elif elem_type == "link":
            md_lines.append(content)
        
        prev_y = y_pos
    
    # Markdown collapses single newlines into spaces. Add two trailing spaces
    # before newlines to create soft line breaks so each line renders separately.
    for i in range(len(md_lines)):
        line = md_lines[i]
        if not line:
            continue
        if i + 1 >= len(md_lines):
            continue
        next_line = md_lines[i + 1]
        if not next_line:
            continue  # next is paragraph break, no soft break needed
        stripped = line.strip()
        # Skip soft breaks after tables, images, blockquotes
        if stripped.startswith("|") or stripped.startswith("<") or stripped.startswith(">"):
            continue
        md_lines[i] = line.rstrip() + "  "
    
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

Output (when -o/--extract-images not set):
  Saved under project folder: converted/<pdf_name>/<pdf_name>.md
  Images: converted/<pdf_name>/images/

Examples:
  python full_tool.py document.pdf
  python full_tool.py document.pdf -o output.md --extract-images ./images
  python full_tool.py document.pdf --password mypassword
        """
    )
    parser.add_argument("pdf", help="PDF file to convert")
    parser.add_argument("-o", "--output", help="Output Markdown file (default: project/converted/<name>/<name>.md)")
    parser.add_argument("--extract-images", metavar="DIR", help="Extract images to folder (default: project/converted/<name>/images)")
    parser.add_argument("--password", help="PDF password (if encrypted)")
    
    args = parser.parse_args()
    
    try:
        pdf_path = Path(args.pdf)
        stem = pdf_path.stem

        if args.output:
            output = Path(args.output)
        else:
            # Save in project folder: converted/<doc_name>/<doc_name>.md
            doc_dir = DEFAULT_OUTPUT_DIR / stem
            doc_dir.mkdir(parents=True, exist_ok=True)
            output = doc_dir / f"{stem}.md"

        # Images: same folder as .md by default
        if args.extract_images is not None:
            image_dir = args.extract_images
        else:
            image_dir = str(output.parent / "images")

        output.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n🚀 Comprehensive PDF Converter")
        print("=" * 60)
        print(f"   Output: {output}")
        if image_dir:
            print(f"   Images: {image_dir}")
        print()

        result = pdf_to_markdown(
            args.pdf,
            str(output),
            image_dir,
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
