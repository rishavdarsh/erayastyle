#!/usr/bin/env python3
"""
Quick fix: Add CSS link to existing packing function to fix styling
"""

def fix_packing_css():
    print("🔧 QUICK CSS FIX FOR PACKING PAGE")
    print("=" * 50)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find and replace the packing function
        old_pattern = '''@app.get("/packing")
def eraya_packing_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    return templates.TemplateResponse("packing.html", {
        "request": request,
        "current_user": current_user
    })'''
        
        # Check if this pattern exists (user already converted)
        if old_pattern in content:
            print("⚠️  Route is already converted to templates.TemplateResponse")
            print("The issue is that templates/packing.html has placeholder content.")
            print()
            print("SOLUTION: Revert to the original function structure with CSS fix")
            print()
            
            # Let's search for where the original body content might be
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'body = """' in line and i > 4800 and i < 5500:  # Around packing area
                    print(f"Found body definition at line {i + 1}")
                    print("This contains your original packing functionality.")
                    break
            
            print("\n📋 MANUAL STEPS NEEDED:")
            print("1. Find the original packing HTML (body = \"\"\"...\"\"\") around line 4880-5300")
            print("2. Add this line at the very beginning of the HTML:")
            print('   <link rel="stylesheet" href="/static/css/app.css">')
            print("3. Change the route back to use _eraya_style_page with the updated body")
            print()
            
        else:
            print("✅ Will search for original _eraya_style_page function")
            
            # Search for the _eraya_style_page call for packing
            if '_eraya_style_page("Packing", body)' in content:
                print("Found original packing function with _eraya_style_page")
                
                # Find the function and add CSS
                lines = content.split('\n')
                new_lines = []
                in_packing_body = False
                body_found = False
                
                for i, line in enumerate(lines):
                    if 'def eraya_packing_page(' in line:
                        in_packing_body = True
                    
                    if in_packing_body and 'body = """' in line:
                        new_lines.append(line)
                        # Add the CSS link right after the opening """
                        new_lines.append('    <link rel="stylesheet" href="/static/css/app.css">')
                        body_found = True
                    else:
                        new_lines.append(line)
                    
                    if in_packing_body and '_eraya_style_page("Packing", body)' in line:
                        in_packing_body = False
                
                if body_found:
                    # Write the fixed content
                    with open('app_fixed.py', 'w', encoding='utf-8') as f:
                        f.write('\n'.join(new_lines))
                    
                    print("✅ Created app_fixed.py with CSS fix applied")
                    print("📋 Replace your app.py with app_fixed.py")
                else:
                    print("❌ Could not find body definition in packing function")
            else:
                print("❌ Could not find _eraya_style_page call for packing")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_packing_css()
