#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

TEMPLATE = '''{% extends "layout_base.html" %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold mb-6">{{ title }}</h1>
    
    <!-- Add your page content here -->
    <div class="bg-white/5 rounded-xl p-6 backdrop-blur-sm border border-white/10">
        <p>This is the {name} page.</p>
    </div>
</div>
{% endblock %}
'''

ROUTE_TEMPLATE = '''
@app.get("{route}")
def {name}_page(request: Request, current_user: Dict = Depends(require_roles())):
    """Render the {title} page."""
    return templates.TemplateResponse("{name}.html", {{"request": request, "title": "{title}"}})
'''

def create_page(name: str, route: str):
    # Create template
    templates_dir = Path("templates")
    template_path = templates_dir / f"{name}.html"
    
    if template_path.exists():
        print(f"Error: Template {template_path} already exists!")
        return False
        
    template_path.write_text(TEMPLATE.format(name=name))
    print(f"✓ Created template: {template_path}")
    
    # Add route to app.py
    app_path = Path("app.py")
    if not app_path.exists():
        print("Error: app.py not found!")
        return False
        
    app_content = app_path.read_text()
    
    # Format route name and title
    title = name.replace('_', ' ').title()
    
    # Add route before the last line
    lines = app_content.splitlines()
    route_code = ROUTE_TEMPLATE.format(route=route, name=name, title=title)
    
    # Insert before the last line (assuming it's empty or has a final newline)
    lines.insert(-1, route_code)
    
    app_path.write_text('\n'.join(lines))
    print(f"✓ Added route to app.py: {route}")
    
    print(f"\nSuccess! New page created at {route}")
    print("Don't forget to:")
    print("1. Add any required imports")
    print("2. Add the route to protected_paths if needed")
    print("3. Add to NAV_ITEMS if it should appear in the sidebar")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new page template and route")
    parser.add_argument("--name", required=True, help="Page name (used for template and route function)")
    parser.add_argument("--route", required=True, help="URL route (e.g., /orders)")
    
    args = parser.parse_args()
    create_page(args.name, args.route)