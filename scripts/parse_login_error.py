import re
import os
path = os.path.join(os.environ.get('TEMP', '/tmp'), 'login_final.html')
# Also try alternate paths
if not os.path.exists(path):
    alt_paths = ['/tmp/login_final.html', 'C:\\tmp\\login_final.html', os.path.join(os.environ.get('HOME', '/tmp'), 'login_final.html')]
    for p in alt_paths:
        if os.path.exists(p):
            path = p
            break
print(f'Trying path: {path}')
print(f'Exists: {os.path.exists(path)}')
with open(path, 'r') as f:
    html = f.read()

# Find alert content
match = re.search(r'<div class="auth-alert[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
if match:
    content = match.group(1).strip()
    # Strip HTML tags
    clean = re.sub(r'<[^>]+>', '', content).strip()
    print('Error message:', clean[:200])
else:
    # Check for any flash or alert patterns
    if 'auth-alert' in html:
        idx = html.find('auth-alert')
        print('Context around auth-alert:')
        print(html[idx-30:idx+250])
    else:
        print('No auth-alert found')
        # Check other patterns
        for pattern in ['flash', 'error', 'Invalid', 'Please']:
            if pattern in html:
                idx = html.find(pattern)
                print(f'Found "{pattern}" at position {idx}:')
                print(html[max(0,idx-50):idx+150])
                print('---')
