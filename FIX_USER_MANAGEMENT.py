#!/usr/bin/env python3
"""
Fix the User Management page: Add missing route decorator and convert to template system
"""

def fix_user_management():
    print("🔧 FIXING USER MANAGEMENT PAGE")
    print("=" * 60)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if the route decorator is missing
        if 'def user_management_page(' in content and '@app.get("/admin/users")' not in content:
            print("✅ Found the issue: Missing @app.get('/admin/users') decorator!")
            print()
            
            # Find the function and add the decorator
            lines = content.split('\n')
            new_lines = []
            
            for i, line in enumerate(lines):
                if 'def user_management_page(' in line:
                    # Add the missing decorator before the function
                    new_lines.append('@app.get("/admin/users")')
                    new_lines.append(line)
                    print(f"📍 Adding route decorator at line {i + 1}")
                else:
                    new_lines.append(line)
            
            # Write the fixed content
            with open('app_user_mgmt_fixed.py', 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            print("✅ Created app_user_mgmt_fixed.py with route decorator added")
            print()
            print("🔄 NEXT STEP: Convert to template system")
            print("The function still uses _eraya_style_page. We should convert it to:")
            print()
            print("@app.get('/admin/users')")
            print("def user_management_page(request: Request, current_user: Dict = Depends(require_roles('owner', 'admin'))):")
            print("    return templates.TemplateResponse('admin/users.html', {")
            print("        'request': request,")
            print("        'current_user': current_user")
            print("    })")
            print()
            
            return True
        
        elif '@app.get("/admin/users")' in content and 'def user_management_page(' in content:
            print("✅ Route decorator exists!")
            
            # Check if it's using templates or _eraya_style_page
            if '_eraya_style_page("User Management", body)' in content:
                print("⚠️  But still using _eraya_style_page instead of templates")
                print()
                print("Need to convert to:")
                print("    return templates.TemplateResponse('admin/users.html', {")
                print("        'request': request,")
                print("        'current_user': current_user")
                print("    })")
                
                convert_to_template_system(content)
                return True
            else:
                print("✅ Already using template system!")
                return True
        
        else:
            print("❌ Could not find user_management_page function")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def convert_to_template_system(content):
    """Convert the function to use template system"""
    print()
    print("🔄 CONVERTING TO TEMPLATE SYSTEM...")
    
    # Find the user_management_page function and replace it
    lines = content.split('\n')
    new_lines = []
    in_function = False
    function_indent = 0
    
    for i, line in enumerate(lines):
        if '@app.get("/admin/users")' in line or 'def user_management_page(' in line:
            if 'def user_management_page(' in line:
                in_function = True
                function_indent = len(line) - len(line.lstrip())
                
                # Replace the entire function with the new template-based version
                new_lines.append('@app.get("/admin/users")')
                new_lines.append('def user_management_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):')
                new_lines.append('    return templates.TemplateResponse("admin/users.html", {')
                new_lines.append('        "request": request,')
                new_lines.append('        "current_user": current_user')
                new_lines.append('    })')
                new_lines.append('')
                
                print(f"📍 Replacing function starting at line {i + 1}")
            else:
                new_lines.append(line)
        elif in_function:
            # Skip all lines until we're out of the function
            current_indent = len(line) - len(line.lstrip()) if line.strip() else function_indent + 4
            
            # Check if we're out of the function (back to original indent level or less)
            if line.strip() and current_indent <= function_indent:
                in_function = False
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # Write the converted content
    with open('app_user_mgmt_template_fixed.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print("✅ Created app_user_mgmt_template_fixed.py with template conversion")
    print()
    print("📋 MANUAL STEPS:")
    print("1. Replace your app.py with app_user_mgmt_template_fixed.py")
    print("2. Restart your FastAPI server")
    print("3. Visit /admin/users - it should now work with consistent sidebar!")

if __name__ == "__main__":
    fix_user_management()
