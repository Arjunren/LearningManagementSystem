import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "templates")

for root, dirs, files in os.walk(templates_dir):
    for file in files:
        if file.endswith(".html"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "<form" in content and "csrf_token" not in content:
                content = re.sub(r'(<form[^>]*>)', r'\1\n<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">', content)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Updated {path}")
