#!/usr/bin/env python3
"""
Script to extract the real packing HTML from app.py and create a proper template
"""

def extract_packing_html():
    print("🔧 EXTRACTING REAL PACKING FUNCTIONALITY")
    print("=" * 60)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the packing function
        lines = content.split('\n')
        start_line = None
        end_line = None
        
        for i, line in enumerate(lines):
            if 'def eraya_packing_page(' in line:
                start_line = i
            if start_line and 'return _eraya_style_page("Packing", body)' in line:
                end_line = i
                break
        
        if start_line and end_line:
            print(f"Found packing function from line {start_line + 1} to {end_line + 1}")
            
            # Extract the body content
            body_start = None
            body_end = None
            
            for i in range(start_line, end_line):
                if 'body = """' in lines[i]:
                    body_start = i + 1
                if body_start and '"""' in lines[i] and i > body_start:
                    body_end = i
                    break
            
            if body_start and body_end:
                html_content = '\n'.join(lines[body_start:body_end])
                
                # Create the new template
                template_content = f'''{% extends "layout_base.html" %}
{% block content %}

{html_content}

{% endblock %}'''
                
                # Write the template
                with open('templates/packing_real.html', 'w', encoding='utf-8') as f:
                    f.write(template_content)
                
                print("✅ Created templates/packing_real.html with real functionality")
                
                # Create the new route code
                route_code = '''@app.get("/packing")
def eraya_packing_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    return templates.TemplateResponse("packing_real.html", {
        "request": request,
        "current_user": current_user
    })'''
                
                print("\n🔄 REPLACE YOUR PACKING ROUTE WITH:")
                print("-" * 40)
                print(route_code)
                print()
                
                return True
            else:
                print("❌ Could not find body content in packing function")
        else:
            print("❌ Could not find packing function")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

if __name__ == "__main__":
    success = extract_packing_html()
    if success:
        print("✅ DONE! Use the template and route code above.")
    else:
        print("❌ FAILED! Manual extraction needed.")
