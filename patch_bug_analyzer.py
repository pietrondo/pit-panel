with open('src/pit_panel/security/bug_analyzer.py', 'r') as f:
    content = f.read()

old_block = """    (
        "critical",
        re.compile(r"(?i)\b(CRITICAL|ExceptionGroup|Traceback \(most recent call last\)|panic:|segmentation fault|fatal error)\b"),
        "Crash o eccezione non gestita: controlla stack trace e ultimo deploy.",
    ),"""

new_block = """    (
        "critical",
        re.compile(
            r"(?i)\b(CRITICAL|ExceptionGroup|Traceback \(most recent call last\)|"
            r"panic:|segmentation fault|fatal error)\b"
        ),
        "Crash o eccezione non gestita: controlla stack trace e ultimo deploy.",
    ),"""

content = content.replace(old_block, new_block)

with open('src/pit_panel/security/bug_analyzer.py', 'w') as f:
    f.write(content)
