#!/usr/bin/env python3
"""
PDF to Markdown Converter using pyMuPDF
Converts single PDF files or batch processes entire directories.
Handles text, images, links, headings, tables, and lists.

Features:
  - Single PDF conversion
  - Batch processing (entire directories)
  - Recursive directory scanning
  - Image extraction & auto-resize
  - Hyperlink extraction
  - Heading detection
  - List & code block detection
  - Page breaks support
  - GUI + CLI modes

Requirements:
    pip install pymupdf pillow

Usage Examples:
  # GUI mode
  python pdf_to_md_Using_pyMuPDF.py --gui

  # Single file conversion
  python pdf_to_md_Using_pyMuPDF.py document.pdf

  # Single file with output path
  python pdf_to_md_Using_pyMuPDF.py document.pdf -o output.md

  # Batch convert entire directory (recursive)
  python pdf_to_md_Using_pyMuPDF.py /path/to/pdf/folder/

  # Batch with output directory
  python pdf_to_md_Using_pyMuPDF.py /path/to/folder/ -o /output/folder/

  # With image extraction
  python pdf_to_md_Using_pyMuPDF.py document.pdf --extract-images ./images
"""

import re
import sys
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import os
from PIL import Image
import io

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Missing dependency. Install with: pip install pymupdf pillow")
    sys.exit(1)


# ─────────────────────────────────────────────
# Heuristics / helpers
# ─────────────────────────────────────────────

def is_heading(text: str, font_size: float, avg_font_size: float) -> str | None:
    """Return heading level ('# ', '## ', '### ') or None."""
    if font_size == 0:
        return None
    ratio = font_size / avg_font_size if avg_font_size else 1
    if ratio >= 1.8:
        return "# "
    if ratio >= 1.4:
        return "## "
    if ratio >= 1.15:
        return "### "
    return None


def looks_like_list_item(text: str) -> bool:
    return bool(re.match(r"^[\-\•\*\·▪▸►→✓✔]\s+", text)) or bool(
        re.match(r"^\d+[\.\)]\s+", text)
    )


def clean_list_item(text: str) -> str:
    # Normalize bullet to '-'
    text = re.sub(r"^[\•\*\·▪▸►→✓✔]\s+", "- ", text)
    # Normalize numbered list: keep as-is
    return text


# ─────────────────────────────────────────────
# Image & Media Handling
# ─────────────────────────────────────────────

def extract_images(page, page_num: int, output_dir: str) -> list[tuple[str, float]]:
    """
    Extract images from a PDF page using pyMuPDF.
    Returns list of (markdown_image_ref, vertical_position).
    """
    images_data = []
    
    if not output_dir or not Path(output_dir).exists():
        return images_data
    
    try:
        image_list = page.get_images()
        for img_idx, img_ref in enumerate(image_list):
            try:
                # Get image from page
                xref = img_ref[0]
                pix = fitz.Pixmap(page.parent, xref)
                
                # Convert to RGB if needed
                if pix.n - pix.alpha < 4:  # GRAY or RGB
                    img_data = pix.tobytes("png")
                else:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    img_data = pix.tobytes("png")
                
                img_name = f"page{page_num}_img{img_idx}.png"
                img_path = Path(output_dir) / img_name
                
                # Save image
                with open(img_path, "wb") as f:
                    f.write(img_data)
                
                # Resize image if too large
                resize_image(str(img_path), max_width=600, max_height=800)
                
                # Get image position
                img_rect = page.get_image_bbox(img_ref)
                img_top = img_rect.y0 if img_rect else 0
                
                # Create markdown reference
                rel_path = f"images/{img_name}".replace("\\", "/")
                md_ref = f"![Image]({rel_path})"
                images_data.append((md_ref, img_top))
                
            except Exception as e:
                print(f"  [warn] Failed to extract image {img_idx}: {e}")
                continue
    
    except Exception as e:
        print(f"  [warn] Error extracting images: {e}")
    
    return images_data


def resize_image(img_path: str, max_width: int = 600, max_height: int = 800):
    """Resize image to fit within max dimensions."""
    try:
        with Image.open(img_path) as img:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            img.save(img_path, optimize=True, quality=85)
    except Exception as e:
        print(f"  [warn] Could not resize {img_path}: {e}")


# ─────────────────────────────────────────────
# Text Formatting & Links
# ─────────────────────────────────────────────

def extract_hyperlinks(page) -> dict[str, str]:
    """Extract hyperlinks from PDF page."""
    links = {}
    try:
        for link in page.get_links():
            if link.get("uri"):
                links[link.get("uri")] = link.get("uri")
    except Exception as e:
        print(f"  [warn] Could not extract links: {e}")
    return links


def detect_code_block(text: str) -> bool:
    """Detect if text looks like code."""
    code_patterns = [
        r"^\s*(def|class|if|for|while|import|from)\s+",  # Python
        r"^\s*(function|const|let|var|async|await)\s+",  # JavaScript
        r"^\s*(public|private|static|void|int|string)\s+",  # Java/C#
        r"^\s*[{}\[\]();]",  # Common code symbols
        r"^```",  # Already code block
    ]
    for pattern in code_patterns:
        if re.search(pattern, text):
            return True
    return False


def enhance_text_formatting(text: str) -> str:
    """Enhance text with markdown formatting based on heuristics."""
    if text.startswith("`") or detect_code_block(text):
        if not text.startswith("```"):
            return f"`{text}`"
    return text


def preserve_indentation(text: str) -> str:
    """Preserve leading spaces as indentation."""
    leading_spaces = len(text) - len(text.lstrip())
    if leading_spaces > 4:
        indent_str = "  " * (leading_spaces // 4)
        return indent_str + text.lstrip()
    return text


# ─────────────────────────────────────────────
# Table Detection & Conversion
# ─────────────────────────────────────────────

def detect_table_from_position(blocks, y_min: float, y_max: float) -> list[list[str]]:
    """
    Detect and extract table structure from text blocks within a vertical range.
    Returns a simple table if detected, otherwise empty list.
    """
    # Very simple heuristic: if multiple lines with similar x-alignment, might be a table
    # For now, return empty - pyMuPDF doesn't have built-in table detection
    return []


def table_to_markdown(table: list[list]) -> str:
    """Convert a table (list of rows) to Markdown."""
    if not table or len(table) == 0:
        return ""

    header = table[0]
    separator = ["---"] * len(header)
    rows = table[1:] if len(table) > 1 else []

    lines = []
    lines.append("| " + " | ".join(str(h).strip() for h in header) + " |")
    lines.append("| " + " | ".join(separator) + " |")
    for row in rows:
        while len(row) < len(header):
            row.append("")
        lines.append("| " + " | ".join(str(cell).strip() for cell in row[:len(header)]) + " |")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Core converter
# ─────────────────────────────────────────────

def get_avg_font_size(page) -> float:
    """Calculate average font size from text on a page."""
    sizes = []
    try:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 12)
                        if size > 0:
                            sizes.append(size)
    except Exception as e:
        print(f"  [warn] Could not calculate font size: {e}")
    
    return sum(sizes) / len(sizes) if sizes else 12.0


def page_to_markdown(page, page_num: int, include_page_breaks: bool, image_dir: str = None) -> str:
    """Convert a single pyMuPDF page to Markdown text."""
    md_lines = []

    if include_page_breaks and page_num > 1:
        md_lines.append(f"\n---\n*Page {page_num}*\n")

    try:
        avg_size = get_avg_font_size(page)
        
        # Extract images and links
        images_data = extract_images(page, page_num, image_dir) if image_dir else []
        links = extract_hyperlinks(page)
        
        # Get text blocks
        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])
        
        # Process text blocks
        prev_y = None
        for block in blocks:
            if block["type"] == 0:  # Text block
                block_y = block.get("bbox", [0, 0, 0, 0])[1]
                
                # Insert images before this block if positioned above
                images_to_insert = [img for img, img_y in images_data if img_y < block_y]
                for img in images_to_insert:
                    md_lines.append(f"\n{img}\n")
                images_data = [(img, img_y) for img, img_y in images_data if img_y >= block_y]
                
                # Check for paragraph break
                if prev_y is not None and (block_y - prev_y) > 20:
                    md_lines.append("")
                
                # Extract text from block
                for line in block.get("lines", []):
                    line_text = ""
                    font_size = 12
                    
                    for span in line.get("spans", []):
                        line_text += span.get("text", "")
                        font_size = span.get("size", 12)
                    
                    line_text = line_text.strip()
                    if not line_text:
                        continue
                    
                    # Detect heading
                    heading = is_heading(line_text, font_size, avg_size)
                    if heading:
                        md_lines.append(f"\n{heading}{line_text}\n")
                    elif looks_like_list_item(line_text):
                        md_lines.append(clean_list_item(line_text))
                    else:
                        # Enhance formatting
                        line_text = enhance_text_formatting(line_text)
                        line_text = preserve_indentation(line_text)
                        md_lines.append(line_text)
                
                prev_y = block_y
            
            elif block["type"] == 1:  # Image block - handle embedded images
                try:
                    block_y = block.get("bbox", [0, 0, 0, 0])[1]
                    # Try to extract image data
                    if "image" in block:
                        img_top = block_y
                        images_data.append((f"[Image]", img_top))
                except Exception as e:
                    pass
        
        # Append remaining images
        for img, _ in images_data:
            md_lines.append(f"\n{img}\n")
    
    except Exception as e:
        print(f"  [warn] Error processing page {page_num}: {e}")
        return ""

    result = "\n".join(md_lines)
    return result


def pdf_to_markdown(
    pdf_path: str,
    output_path: str | None = None,
    page_breaks: bool = False,
    pages: list[int] | None = None,
    image_dir: str | None = None,
) -> str:
    """
    Convert a PDF file to Markdown using pyMuPDF.

    Args:
        pdf_path:    Path to the input PDF.
        output_path: If given, write Markdown to this file.
        page_breaks: Insert '---' separators between pages.
        pages:       1-based list of page numbers to convert (None = all).
        image_dir:   Directory to save extracted images (None = skip images).

    Returns:
        Markdown string.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    # Create image directory if specified
    if image_dir:
        img_path = Path(image_dir)
        img_path.mkdir(parents=True, exist_ok=True)

    md_sections = []

    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        target_pages = pages if pages else list(range(1, total + 1))

        for page_num in target_pages:
            if page_num < 1 or page_num > total:
                print(f"  [warn] Page {page_num} out of range (1-{total}), skipping.")
                continue
            
            page = doc[page_num - 1]
            md = page_to_markdown(page, page_num, page_breaks, image_dir)
            if md:
                md_sections.append(md)
        
        doc.close()

    except Exception as e:
        raise RuntimeError(f"Error processing PDF: {e}")

    result = "\n\n".join(md_sections)

    # ── Clean up excess blank lines ──
    result = re.sub(r"\n{3,}", "\n\n", result).strip()

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")
        print(f"✅ Saved: {output_path}")

    return result


# ─────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────

class PDFtoMDGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF to Markdown Converter v2.0 (pyMuPDF)")
        self.root.geometry("700x900")
        self.root.resizable(True, True)
        
        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.image_dir = tk.StringVar()
        self.page_breaks = tk.BooleanVar(value=False)
        self.extract_images = tk.BooleanVar(value=True)
        self.custom_pages = tk.StringVar()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Create the GUI layout."""
        # Title
        title_frame = tk.Frame(self.root, bg="#2c3e50")
        title_frame.pack(fill=tk.X, padx=0, pady=0)
        title_label = tk.Label(
            title_frame,
            text="📄 PDF to Markdown Converter v2.0 (pyMuPDF)",
            font=("Arial", 16, "bold"),
            bg="#2c3e50",
            fg="white",
            pady=15
        )
        title_label.pack()
        
        # Main content frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # ── PDF Input ──
        tk.Label(main_frame, text="1. Select PDF File:", font=("Arial", 11, "bold")).pack(anchor=tk.W)
        pdf_frame = tk.Frame(main_frame)
        pdf_frame.pack(fill=tk.X, pady=(5, 15))
        
        tk.Entry(pdf_frame, textvariable=self.pdf_path, state="readonly", width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(pdf_frame, text="Browse", command=self.browse_pdf, width=10).pack(side=tk.LEFT, padx=(10, 0))
        
        # ── Output Path ──
        tk.Label(main_frame, text="2. Output File (optional):", font=("Arial", 11, "bold")).pack(anchor=tk.W)
        output_frame = tk.Frame(main_frame)
        output_frame.pack(fill=tk.X, pady=(5, 15))
        
        tk.Entry(output_frame, textvariable=self.output_path, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(output_frame, text="Browse", command=self.browse_output, width=10).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(main_frame, text="(Leave empty to auto-generate)", foreground="gray", font=("Arial", 9)).pack(anchor=tk.W)
        
        # ── Image Extraction ──
        tk.Label(main_frame, text="3. Image Extraction:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        
        img_check = tk.Checkbutton(
            main_frame,
            text="Extract images from PDF",
            variable=self.extract_images,
            command=self.toggle_image_dir,
            font=("Arial", 10)
        )
        img_check.pack(anchor=tk.W, pady=5)
        
        tk.Label(main_frame, text="Image folder (if extraction enabled):", font=("Arial", 10)).pack(anchor=tk.W, pady=(5, 5))
        img_frame = tk.Frame(main_frame)
        img_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Entry(img_frame, textvariable=self.image_dir, width=50, state="disabled").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.img_browse_btn = tk.Button(img_frame, text="Browse", command=self.browse_image_dir, width=10, state="disabled")
        self.img_browse_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # ── Options ──
        tk.Label(main_frame, text="4. Options:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        
        tk.Checkbutton(
            main_frame,
            text="Add page breaks between pages",
            variable=self.page_breaks,
            font=("Arial", 10)
        ).pack(anchor=tk.W, pady=5)
        
        tk.Label(main_frame, text="Specific pages (optional, e.g., '1,3,5-8'):", font=("Arial", 10)).pack(anchor=tk.W, pady=(10, 5))
        tk.Entry(main_frame, textvariable=self.custom_pages, width=50).pack(fill=tk.X, pady=(0, 15))
        
        # ── Convert Button ──
        convert_btn = tk.Button(
            main_frame,
            text="🔄 Convert PDF to Markdown",
            command=self.convert,
            bg="#27ae60",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10
        )
        convert_btn.pack(pady=20)
        
        # ── Status ──
        tk.Label(main_frame, text="Status:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.status_text = scrolledtext.ScrolledText(
            main_frame,
            height=12,
            width=80,
            font=("Courier", 9),
            state=tk.DISABLED
        )
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # ── Button Frame ──
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        tk.Button(
            button_frame,
            text="Clear",
            command=self.clear_status,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="Exit",
            command=self.root.quit,
            width=10
        ).pack(side=tk.RIGHT, padx=5)
    
    def toggle_image_dir(self):
        """Enable/disable image directory input based on extraction checkbox."""
        state = tk.NORMAL if self.extract_images.get() else tk.DISABLED
        self.img_browse_btn.config(state=state)
        if not self.extract_images.get():
            self.image_dir.set("")
    
    def browse_pdf(self):
        """Open file dialog to select PDF."""
        file_path = filedialog.askopenfilename(
            title="Select PDF File",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if file_path:
            self.pdf_path.set(file_path)
            self.log(f"Selected PDF: {Path(file_path).name}")
    
    def browse_output(self):
        """Open file dialog to select output location."""
        file_path = filedialog.asksaveasfilename(
            title="Save Markdown As",
            defaultextension=".md",
            filetypes=[("Markdown Files", "*.md"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.output_path.set(file_path)
            self.log(f"Output will be saved to: {Path(file_path).name}")
    
    def browse_image_dir(self):
        """Open directory dialog to select image folder."""
        dir_path = filedialog.askdirectory(title="Select Folder for Extracted Images")
        if dir_path:
            self.image_dir.set(dir_path)
            self.log(f"Image folder: {Path(dir_path).name}")
    
    def log(self, message: str):
        """Add message to status text."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update()
    
    def clear_status(self):
        """Clear status text."""
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state=tk.DISABLED)
    
    def convert(self):
        """Convert PDF to Markdown."""
        if not self.pdf_path.get():
            messagebox.showerror("Error", "Please select a PDF file.")
            return
        
        if self.extract_images.get() and not self.image_dir.get():
            messagebox.showerror("Error", "Please select an image folder for extraction.")
            return
        
        thread = threading.Thread(target=self._convert_thread)
        thread.start()
    
    def _convert_thread(self):
        """Thread function for conversion."""
        try:
            pdf_path = self.pdf_path.get()
            output_path = self.output_path.get()
            image_dir = self.image_dir.get() if self.extract_images.get() else None
            page_breaks = self.page_breaks.get()
            pages_str = self.custom_pages.get().strip()
            
            if not Path(pdf_path).exists():
                self.log("❌ Error: PDF file not found.")
                return
            
            pages = None
            if pages_str:
                try:
                    pages = parse_pages(pages_str)
                    self.log(f"📌 Converting pages: {pages}")
                except ValueError as e:
                    self.log(f"❌ Error parsing pages: {e}")
                    return
            
            if not output_path:
                output_path = str(Path(pdf_path).with_suffix(".md"))
                self.log(f"📝 Auto-generated output: {Path(output_path).name}")
            
            if image_dir:
                self.log(f"📸 Images will be saved to: {image_dir}")
            
            self.log(f"⏳ Converting: {Path(pdf_path).name}...")
            
            markdown = pdf_to_markdown(
                pdf_path,
                output_path=output_path,
                page_breaks=page_breaks,
                pages=pages,
                image_dir=image_dir,
            )
            
            self.log(f"✅ Success! Saved to: {output_path}")
            self.log(f"📊 Output size: {len(markdown)} characters")
            if image_dir:
                img_count = len(list(Path(image_dir).glob("*.png")))
                self.log(f"🖼️  Extracted {img_count} images")
            
            self.root.after(0, lambda: self._ask_view(output_path, markdown))
        
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
    
    def _ask_view(self, output_path: str, markdown: str):
        """Ask user if they want to view the output."""
        response = messagebox.askyesno(
            "Success",
            f"Conversion completed!\n\nFile saved to:\n{output_path}\n\nView output?"
        )
        if response:
            self._show_preview(markdown)
    
    def _show_preview(self, markdown: str):
        """Show a preview window of the markdown."""
        preview_win = tk.Toplevel(self.root)
        preview_win.title("Markdown Preview")
        preview_win.geometry("800x600")
        
        text_widget = scrolledtext.ScrolledText(
            preview_win,
            font=("Courier", 10),
            wrap=tk.WORD
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(1.0, markdown)
        text_widget.config(state=tk.DISABLED)
        
        tk.Button(
            preview_win,
            text="Close",
            command=preview_win.destroy
        ).pack(pady=10)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_pages(pages_str: str) -> list[int]:
    """Parse '1,3,5-8' into [1, 3, 5, 6, 7, 8]."""
    pages = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def process_single_pdf(pdf_path: str, output_path: str = None, page_breaks: bool = False, 
                       pages: list = None, image_dir: str = None, print_output: bool = False) -> bool:
    """Process a single PDF file. Returns True if successful."""
    try:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            print(f"❌ Error: PDF not found - {pdf_path}")
            return False
        
        output_path = output_path or str(pdf_path.with_suffix(".md"))
        
        print(f"📄 Converting: {pdf_path.name}...", end=" ")
        markdown = pdf_to_markdown(
            str(pdf_path),
            output_path=str(output_path),
            page_breaks=page_breaks,
            pages=pages,
            image_dir=image_dir,
        )
        
        print(f"✅ Done ({len(markdown)} chars)")
        
        if print_output:
            print("\n" + "=" * 60 + "\n")
            print(markdown)
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def process_directory(directory: str, output_dir: str = None, page_breaks: bool = False,
                     image_dir: str = None, recursive: bool = True) -> None:
    """Process all PDFs in a directory."""
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"❌ Error: Directory not found - {directory}")
        return
    
    # Create output directory if specified
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    if recursive:
        pdf_files = list(dir_path.rglob("*.pdf"))
    else:
        pdf_files = list(dir_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"⚠️  No PDF files found in {directory}")
        return
    
    print(f"\n📂 Found {len(pdf_files)} PDF file(s)")
    print("=" * 60)
    
    successful = 0
    failed = 0
    
    for pdf_file in pdf_files:
        # Determine output path
        if output_dir:
            out_path = Path(output_dir) / pdf_file.stem / "index.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = pdf_file.with_suffix(".md")
        
        # Determine image directory
        img_dir = None
        if image_dir:
            img_dir = Path(image_dir) / pdf_file.stem / "images"
            img_dir.mkdir(parents=True, exist_ok=True)
        
        if process_single_pdf(str(pdf_file), str(out_path), page_breaks, None, str(img_dir) if img_dir else None):
            successful += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"\n✅ Conversion Summary:")
    print(f"   ✔️  Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    if output_dir:
        print(f"   📁 Output: {output_dir}")
    if image_dir:
        print(f"   🖼️  Images: {image_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF files to Markdown using pyMuPDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # GUI mode
  python pdf_to_md_Using_pyMuPDF.py --gui

  # Single PDF conversion
  python pdf_to_md_Using_pyMuPDF.py path/to/file.pdf
  python pdf_to_md_Using_pyMuPDF.py path/to/file.pdf -o output/file.md

  # Batch conversion (all PDFs in directory)
  python pdf_to_md_Using_pyMuPDF.py path/to/directory/
  python pdf_to_md_Using_pyMuPDF.py path/to/directory/ -o output_dir/

  # With image extraction
  python pdf_to_md_Using_pyMuPDF.py path/to/file.pdf --extract-images ./images
  python pdf_to_md_Using_pyMuPDF.py path/to/directory/ --extract-images ./images

  # Advanced options
  python pdf_to_md_Using_pyMuPDF.py file.pdf --page-breaks --pages 1,3,5-8
        """,
    )
    parser.add_argument("path", nargs="?", help="Path to PDF file or directory of PDFs")
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("-o", "--output", help="Output Markdown file or directory")
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert horizontal rules between pages",
    )
    parser.add_argument(
        "--pages",
        help="Specific pages to convert (single file only), e.g. '1,3,5-8'",
        default=None,
    )
    parser.add_argument(
        "--extract-images",
        metavar="DIR",
        help="Extract images to specified directory",
        default=None,
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't search subdirectories when processing a directory",
    )
    parser.add_argument(
        "--print",
        dest="print_output",
        action="store_true",
        help="Print Markdown to stdout (single file only)",
    )

    args = parser.parse_args()
    
    # Launch GUI mode
    if args.gui:
        root = tk.Tk()
        app = PDFtoMDGUI(root)
        root.mainloop()
        return
    
    # CLI mode
    if not args.path:
        parser.print_help()
        sys.exit(1)
    
    input_path = Path(args.path)
    
    # Check if it's a directory or file
    if input_path.is_dir():
        # Batch processing for directory
        print(f"\n🔄 Batch Processing: {input_path}")
        process_directory(
            str(input_path),
            output_dir=args.output,
            page_breaks=args.page_breaks,
            image_dir=args.extract_images,
            recursive=not args.no_recursive,
        )
    else:
        # Single file processing
        pages = parse_pages(args.pages) if args.pages else None
        process_single_pdf(
            str(input_path),
            output_path=args.output,
            page_breaks=args.page_breaks,
            pages=pages,
            image_dir=args.extract_images,
            print_output=args.print_output,
        )


if __name__ == "__main__":
    main()
