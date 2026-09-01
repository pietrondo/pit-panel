🚨 Severity: HIGH
💡 Vulnerability: Python's `re.match` with the `$` anchor allows trailing newlines (e.g., `input\n`) to pass validation. This could potentially allow command injection or bypass of input filters if the trailing newline causes the string to be evaluated unsafely downstream in shell commands or configuration files.
🎯 Impact: Attackers could bypass strict alphanumeric/domain validations by appending a newline to their input, leading to unauthorized actions or invalid configuration generation.
🔧 Fix: Upgraded all security and input validation regular expressions from `re.match` to `re.fullmatch` to strictly enforce that the entire string matches the pattern, effectively blocking trailing newlines and other hidden characters.
✅ Verification: Ran `pytest` locally to ensure no regressions were introduced.
