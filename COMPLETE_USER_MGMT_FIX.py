#!/usr/bin/env python3
"""
Complete fix for User Management page: Add route decorator + convert to template system
"""

def complete_user_management_fix():
    print("🔧 COMPLETE USER MANAGEMENT FIX")
    print("=" * 50)
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the user_management_page function
        lines = content.split('\n')
        new_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for the user_management_page function
            if 'def user_management_page(' in line:
                print(f"📍 Found user_management_page function at line {i + 1}")
                
                # Check if it already has the route decorator above it
                has_decorator = False
                if i > 0 and '@app.get("/admin/users")' in lines[i - 1]:
                    has_decorator = True
                    print("✅ Route decorator already exists")
                else:
                    print("⚠️  Missing route decorator - adding it")
                    # Add the decorator
                    new_lines.append('@app.get("/admin/users")')
                
                # Replace the entire function with template-based version
                print("🔄 Converting to template system...")
                
                new_lines.append('def user_management_page(request: Request, current_user: Dict = Depends(require_roles("owner", "admin"))):')
                new_lines.append('    return templates.TemplateResponse("admin/users.html", {')
                new_lines.append('        "request": request,')
                new_lines.append('        "current_user": current_user')
                new_lines.append('    })')
                new_lines.append('')
                
                # Skip the entire old function (until we find the next function or end)
                i += 1
                function_indent = len(lines[i-1]) - len(lines[i-1].lstrip()) if i > 0 else 0
                
                while i < len(lines):
                    current_line = lines[i]
                    
                    # If we hit another function definition or decorator, we're done
                    if (current_line.strip().startswith('def ') or 
                        current_line.strip().startswith('@app.') or
                        current_line.strip().startswith('@router.') or
                        (current_line.strip() and 
                         len(current_line) - len(current_line.lstrip()) <= function_indent and
                         not current_line.startswith(' '))):
                        break
                    i += 1
                
                print(f"✅ Replaced function (skipped to line {i + 1})")
                continue
                
            else:
                new_lines.append(line)
                
            i += 1
        
        # Write the fixed file
        with open('app_complete_user_mgmt_fix.py', 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ Created app_complete_user_mgmt_fix.py")
        print()
        print("📋 APPLY THE FIX:")
        print("1. Replace your app.py:")
        print("   copy app_complete_user_mgmt_fix.py app.py")
        print()
        print("2. Restart FastAPI server")
        print()
        print("3. Visit http://127.0.0.1:8000/admin/users")
        print("   Should now show with consistent sidebar!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    complete_user_management_fix()
