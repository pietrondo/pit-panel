import re

with open('src/pit_panel/web/routes/security_ddos.py', 'r', encoding='utf-8') as f:
    content = f.read()

# E501 errors are just line length on rules. We can just add # noqa: E501 to them.
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'DDOS_CHAIN' in line and '["-A"' in line and len(line) > 100 and '# noqa' not in line:
        lines[i] = line + "  # noqa: E501"

with open('src/pit_panel/web/routes/security_ddos.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
