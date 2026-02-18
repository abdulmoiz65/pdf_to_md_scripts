#!/usr/bin/env python3
"""
Test script to demonstrate batch processing capabilities
"""

import os
import sys
from pathlib import Path

def create_sample_test_structure():
    """Create a sample directory structure for testing"""
    print("📁 Creating sample test structure...")
    
    # Create test directories
    test_dir = Path("test_pdfs")
    test_dir.mkdir(exist_ok=True)
    
    subdir1 = test_dir / "folder1"
    subdir2 = test_dir / "folder2"
    subdir1.mkdir(exist_ok=True)
    subdir2.mkdir(exist_ok=True)
    
    print(f"""
✅ Test structure created:
    
test_pdfs/
├── folder1/
└── folder2/

To test batch processing, add some PDF files to these folders, then run:

# Convert all PDFs (recursive)
python pdf_to_md_Using_pyMuPDF.py test_pdfs/

# Convert to specific output directory
python pdf_to_md_Using_pyMuPDF.py test_pdfs/ -o test_output/

# With image extraction
python pdf_to_md_Using_pyMuPDF.py test_pdfs/ -o test_output/ --extract-images ./test_images

# Non-recursive (only root folder)
python pdf_to_md_Using_pyMuPDF.py test_pdfs/ --no-recursive
    """)

def show_cli_examples():
    """Show all available CLI examples"""
    examples = {
        "GUI Mode": "python pdf_to_md_Using_pyMuPDF.py --gui",
        
        "Single PDF": "python pdf_to_md_Using_pyMuPDF.py document.pdf",
        
        "Single PDF with Output": "python pdf_to_md_Using_pyMuPDF.py document.pdf -o output.md",
        
        "Batch Directory": "python pdf_to_md_Using_pyMuPDF.py ./pdfs/",
        
        "Batch with Output": "python pdf_to_md_Using_pyMuPDF.py ./pdfs/ -o ./output/",
        
        "Batch with Images": "python pdf_to_md_Using_pyMuPDF.py ./pdfs/ --extract-images ./images",
        
        "With Page Breaks": "python pdf_to_md_Using_pyMuPDF.py document.pdf --page-breaks",
        
        "Specific Pages": "python pdf_to_md_Using_pyMuPDF.py document.pdf --pages 1,3,5-8",
        
        "Non-Recursive": "python pdf_to_md_Using_pyMuPDF.py ./pdfs/ --no-recursive",
        
        "All Options": "python pdf_to_md_Using_pyMuPDF.py document.pdf -o output.md --page-breaks --extract-images ./images --pages 1-5",
    }
    
    print("\n" + "=" * 70)
    print("🔥 AVAILABLE COMMANDS".center(70))
    print("=" * 70 + "\n")
    
    for i, (desc, cmd) in enumerate(examples.items(), 1):
        print(f"{i:2d}. {desc}")
        print(f"    $ {cmd}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        create_sample_test_structure()
    else:
        show_cli_examples()
