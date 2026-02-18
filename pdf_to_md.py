#!/usr/bin/env python3
"""
PDF to Markdown Converter
Converts PDF files to well-structured Markdown documents.
Handles text, headings, tables, and lists.

Requirements:
    pip install pdfplumber pypdf
"""

import re
import sys
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import os
from PIL import Image, ImageTk

try:
    import pdfplumber
except ImportError:
    print("Missing dependency. Install with: pip install pdfplumber pypdf pillow")
    sys.exit(1)


# ─────────────────────────────────────────────
# Heuristics / helpers
# ─────────────────────────────────────────────

def is_heading(text: str, font_size: float | None, avg_font_size: float) -> str | None:
    """Return heading level ('# ', '## ', '### ') or None."""
    if font_size is None:
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
    Extract images from a PDF page.
    Returns list of (markdown_image_ref, top_position).
    """
    images_data = []
    
    if not output_dir or not Path(output_dir).exists():
        return images_data
    
    try:
        for img_idx, img in enumerate(page.images):
            try:
                # Get image from page
                image_data = img.get("stream").get_rawdata()
                img_name = f"page{page_num}_img{img_idx}.png"
                img_path = Path(output_dir) / img_name
                
                # Save original image
                with open(img_path, "wb") as f:
                    f.write(image_data)
                
                # Resize image if too large
                resize_image(str(img_path), max_width=600, max_height=800)
                
                # Get image position (top y coordinate)
                img_top = img.get("top", 0)
                
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
            # Calculate new size while preserving aspect ratio
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
        for link in page.hyperlinks:
            if link.get("uri"):
                links[link.get("uri")] = link.get("uri")
    except Exception as e:
        print(f"  [warn] Could not extract links: {e}")
    return links


def detect_code_block(text: str) -> bool:
    """Detect if text looks like code."""
    # Check for common code patterns
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
    # Don't over-process - just handle obvious cases
    
    # Preserve code blocks (backticks)
    if text.startswith("`") or detect_code_block(text):
        if not text.startswith("```"):
            return f"`{text}`"
    
    return text


def preserve_indentation(text: str) -> str:
    """Preserve leading spaces as indentation."""
    leading_spaces = len(text) - len(text.lstrip())
    if leading_spaces > 4:  # Significant indentation
        # Use markdown code block for indented content
        indent_str = "  " * (leading_spaces // 4)
        return indent_str + text.lstrip()
    return text


def table_to_markdown(table: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to a Markdown table."""
    if not table:
        return ""

    # Clean cells
    cleaned = []
    for row in table:
        cleaned.append([str(cell).strip() if cell is not None else "" for cell in row])

    # Use first row as header
    header = cleaned[0]
    separator = ["---"] * len(header)
    rows = cleaned[1:]

    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(separator) + " |")
    for row in rows:
        # Pad row if columns differ
        while len(row) < len(header):
            row.append("")
        lines.append("| " + " | ".join(row[:len(header)]) + " |")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Core converter
# ─────────────────────────────────────────────

def get_avg_font_size(page) -> float:
    """Calculate average font size from words on a page."""
    sizes = []
    for word in page.extract_words(extra_attrs=["size"]):
        if "size" in word and word["size"]:
            sizes.append(word["size"])
    return sum(sizes) / len(sizes) if sizes else 12.0


def page_to_markdown(page, page_num: int, include_page_breaks: bool, image_dir: str = None) -> str:
    """Convert a single pdfplumber page to Markdown text."""
    md_lines = []

    if include_page_breaks and page_num > 1:
        md_lines.append(f"\n---\n*Page {page_num}*\n")

    avg_size = get_avg_font_size(page)
    
    # Extract images and links
    images_data = extract_images(page, page_num, image_dir) if image_dir else []
    links = extract_hyperlinks(page)

    # ── Detect tables and their bounding boxes ──
    tables = page.extract_tables()
    table_bboxes = []
    for table_obj in page.find_tables():
        table_bboxes.append(table_obj.bbox)  # (x0, top, x1, bottom)

    def in_table(word) -> bool:
        wx0, wy0, wx1, wy1 = word["x0"], word["top"], word["x1"], word["bottom"]
        for bx0, by0, bx1, by1 in table_bboxes:
            if wx0 >= bx0 - 2 and wx1 <= bx1 + 2 and wy0 >= by0 - 2 and wy1 <= by1 + 2:
                return True
        return False

    # ── Emit tables at their vertical position ──
    # Build a sorted list of (top_y, markdown_table)
    table_entries = []
    for table_obj, table_data in zip(page.find_tables(), tables):
        md_table = table_to_markdown(table_data)
        table_entries.append((table_obj.bbox[1], md_table))  # sort by top y
    table_entries.sort(key=lambda x: x[0])
    table_idx = 0

    # ── Extract words grouped into lines ──
    words = page.extract_words(extra_attrs=["size", "fontname"])
    words = [w for w in words if not in_table(w)]

    # Group words into lines by their vertical position (top)
    lines: dict[float, list] = {}
    for word in words:
        key = round(word["top"], 1)
        lines.setdefault(key, []).append(word)

    sorted_tops = sorted(lines.keys())
    prev_top = None

    for top in sorted_tops:
        # Insert any tables that appear before this line
        while table_idx < len(table_entries) and table_entries[table_idx][0] < top:
            md_lines.append("\n" + table_entries[table_idx][1] + "\n")
            table_idx += 1
        
        # Insert images that appear before this line
        images_to_insert = [img for img, img_top in images_data if img_top < top]
        for img in images_to_insert:
            md_lines.append(f"\n{img}\n")
        images_data = [(img, img_top) for img, img_top in images_data if img_top >= top]

        line_words = sorted(lines[top], key=lambda w: w["x0"])
        line_text = " ".join(w["text"] for w in line_words).strip()

        if not line_text:
            continue

        # Detect blank-line gap (paragraph break)
        if prev_top is not None and (top - prev_top) > 20:
            md_lines.append("")

        # Determine font size (use first word's size)
        font_size = line_words[0].get("size")

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

        prev_top = top

    # Append any remaining tables and images
    while table_idx < len(table_entries):
        md_lines.append("\n" + table_entries[table_idx][1] + "\n")
        table_idx += 1
    
    for img, _ in images_data:
        md_lines.append(f"\n{img}\n")

    return "\n".join(md_lines)


def pdf_to_markdown(
    pdf_path: str,
    output_path: str | None = None,
    page_breaks: bool = False,
    pages: list[int] | None = None,
    image_dir: str | None = None,
) -> str:
    """
    Convert a PDF file to Markdown.

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

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        target_pages = pages if pages else list(range(1, total + 1))

        for page_num in target_pages:
            if page_num < 1 or page_num > total:
                print(f"  [warn] Page {page_num} out of range (1-{total}), skipping.")
                continue
            page = pdf.pages[page_num - 1]
            md = page_to_markdown(page, page_num, page_breaks, image_dir)
            md_sections.append(md)

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
        self.root.title("PDF to Markdown Converter v2.0")
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
            text="📄 PDF to Markdown Converter v2.0",
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
        # Clear image directory if unchecked
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
        
        # Run conversion in a separate thread to avoid freezing the UI
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
            
            # Validate PDF exists
            if not Path(pdf_path).exists():
                self.log("❌ Error: PDF file not found.")
                return
            
            # Parse pages if provided
            pages = None
            if pages_str:
                try:
                    pages = parse_pages(pages_str)
                    self.log(f"📌 Converting pages: {pages}")
                except ValueError as e:
                    self.log(f"❌ Error parsing pages: {e}")
                    return
            
            # Auto-generate output path if not provided
            if not output_path:
                output_path = str(Path(pdf_path).with_suffix(".md"))
                self.log(f"📝 Auto-generated output: {Path(output_path).name}")
            
            if image_dir:
                self.log(f"📸 Images will be saved to: {image_dir}")
            
            self.log(f"⏳ Converting: {Path(pdf_path).name}...")
            
            # Convert
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
            
            # Ask if user wants to view the file
            self.root.after(0, lambda: self._ask_view(output_path, markdown, image_dir))
        
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
    
    def _ask_view(self, output_path: str, markdown: str, image_dir: str = None):
        response = messagebox.askyesno(
            "Success",
            f"Conversion completed!\n\nFile saved to:\n{output_path}\n\nView output?"
        )
        if response:
            self._show_preview(markdown, output_path, image_dir)
    
    def _show_preview(self, markdown: str, output_path: str = None, image_dir: str = None):
        """Show a formatted preview window of the markdown."""
        preview_win = tk.Toplevel(self.root)
        preview_win.title("📄 Markdown Preview - Complete Preview")
        preview_win.geometry("1000x700")
        
        # Create scrollable canvas
        canvas = tk.Canvas(preview_win, highlightthickness=0, bg="white")
        scrollbar = tk.Scrollbar(preview_win, orient="vertical", command=canvas.yview)
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
            
            if not line_stripped:
                # Empty line = padding
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
                    # Try to display image
                    try:
                        full_img_path = Path(img_path)
                        if not full_img_path.is_absolute():
                            # Try relative to base directory
                            full_img_path = base_dir / img_path
                        
                        if full_img_path.exists():
                            img = Image.open(full_img_path)
                            # Resize to fit preview width
                            img.thumbnail((900, 500), Image.Resampling.LANCZOS)
                            photo = ImageTk.PhotoImage(img)
                            
                            img_lbl = tk.Label(
                                scrollable_frame,
                                image=photo,
                                bg="white",
                                bd=1,
                                relief=tk.SUNKEN
                            )
                            img_lbl.image = photo  # Keep reference
                            img_lbl.pack(anchor=tk.CENTER, padx=20, pady=10)
                        else:
                            # Image not found, show placeholder
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
                # Table row
                cells = [cell.strip() for cell in line_stripped.split("|")]
                cells = [c for c in cells if c]  # Remove empty cells
                
                if cells:
                    row_frame = tk.Frame(scrollable_frame, bg="white")
                    row_frame.pack(anchor=tk.W, padx=20, pady=2, fill=tk.X)
                    
                    for cell in cells:
                        if cell == "---":
                            continue  # Skip separator rows
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
            
            # Code blocks
            elif line_stripped.startswith("```"):
                code_block = []
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith("```"):
                    code_block.append(lines[j])
                    j += 1
                
                if code_block:
                    code_text = "\n".join(code_block)
                    code_widget = tk.Text(
                        scrollable_frame,
                        height=min(10, len(code_block) + 2),
                        width=100,
                        font=("Courier New", 9),
                        bg="#2c3e50",
                        fg="#ecf0f1",
                        padx=10,
                        pady=10
                    )
                    code_widget.pack(padx=20, pady=10, fill=tk.BOTH)
                    code_widget.insert(1.0, code_text)
                    code_widget.config(state=tk.DISABLED)
            
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
            
            elif re.match(r"^\d+[\.\)]\s+", line_stripped):
                # Numbered list
                text = re.sub(r"^\d+[\.\)]\s+", "", line_stripped)
                indent = len(line) - len(line.lstrip())
                tk.Label(
                    scrollable_frame,
                    text=f"{line_stripped}",
                    font=("Arial", 10),
                    bg="white",
                    wraplength=850,
                    justify=tk.LEFT
                ).pack(anchor=tk.W, padx=(20 + indent, 20), pady=2)
            
            # Bold/Italic text (simple rendering)
            elif "**" in line_stripped or "*" in line_stripped:
                # Simple bold/italic detection
                text = line_stripped
                # Replace **text** with bold indicators
                text_widget = tk.Label(
                    scrollable_frame,
                    text=text,
                    font=("Arial", 10),
                    bg="white",
                    wraplength=850,
                    justify=tk.LEFT
                )
                text_widget.pack(anchor=tk.W, padx=20, pady=3)
            
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
            preview_win,
            text="✕ Close",
            command=preview_win.destroy,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 10)
        )
        close_btn.pack(pady=10)


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


def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF file to Markdown with advanced formatting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdf_to_md.py --gui
  python pdf_to_md.py report.pdf
  python pdf_to_md.py report.pdf -o report.md --extract-images ./images
  python pdf_to_md.py report.pdf --page-breaks --extract-images ./images
  python pdf_to_md.py report.pdf --pages 1,3,5-8
        """,
    )
    parser.add_argument("pdf", nargs="?", help="Input PDF file path")
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("-o", "--output", help="Output Markdown file (default: <pdf_name>.md)")
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert horizontal rules between pages",
    )
    parser.add_argument(
        "--pages",
        help="Specific pages to convert, e.g. '1,3,5-8'",
        default=None,
    )
    parser.add_argument(
        "--extract-images",
        metavar="DIR",
        help="Extract images to specified directory",
        default=None,
    )
    parser.add_argument(
        "--print",
        dest="print_output",
        action="store_true",
        help="Print Markdown to stdout instead of (or in addition to) saving",
    )

    args = parser.parse_args()
    
    # Launch GUI mode
    if args.gui:
        root = tk.Tk()
        app = PDFtoMDGUI(root)
        root.mainloop()
        return
    
    # CLI mode
    if not args.pdf:
        parser.print_help()
        sys.exit(1)

    pdf_path = Path(args.pdf)
    output_path = args.output or pdf_path.with_suffix(".md")
    pages = parse_pages(args.pages) if args.pages else None

    print(f"📄 Converting: {pdf_path}")
    markdown = pdf_to_markdown(
        str(pdf_path),
        output_path=str(output_path),
        page_breaks=args.page_breaks,
        pages=pages,
        image_dir=args.extract_images,
    )

    if args.print_output:
        print("\n" + "=" * 60 + "\n")
        print(markdown)


if __name__ == "__main__":
    main()
