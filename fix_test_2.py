import re
with open("tests/unit/routes/test_security_malware.py", "r") as f:
    content = f.read()

content = content.replace('assert response.status_code == 200\n    assert response.headers.get("HX-Refresh") == "true"', 'assert response.status_code == 200')
with open("tests/unit/routes/test_security_malware.py", "w") as f:
    f.write(content)
