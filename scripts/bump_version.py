import re
with open('app.py', 'r') as f:
    content = f.read()
match = re.search(r"static_version=lambda: '([\d.]+)'", content)
if match:
    ver = match.group(1)
    parts = ver.split('.')
    parts[-1] = str(int(parts[-1]) + 1)
    new_ver = '.'.join(parts)
    content = content.replace("static_version=lambda: '" + ver + "'", "static_version=lambda: '" + new_ver + "'")
    with open('app.py', 'w') as f:
        f.write(content)
    print('Version bumped to ' + new_ver)
else:
    print('Could not find version string')
