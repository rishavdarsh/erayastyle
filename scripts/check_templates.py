#!/usr/bin/env python3
import os
from pathlib import Path

def check_templates():
    templates_dir = Path("templates")
    errors = []
    
    # Check all .html files except those in partials/
    for template in templates_dir.glob("**/*.html"):
        if "partials" in str(template):
            continue
            
        content = template.read_text()
        if not content.strip().startswith('{% extends "layout_base.html" %}'):
            errors.append(str(template))
    
    if errors:
        print("Error: The following templates don't extend layout_base.html:")
        for template in errors:
            print(f"  - {template}")
        exit(1)
    else:
        print("✓ All templates correctly extend layout_base.html")
        exit(0)

if __name__ == "__main__":
    check_templates()