🎯 **What:**
Fixed a directory traversal vulnerability in `AppManager.deploy_template` where `stack_type` parameter was not properly validated.

⚠️ **Risk:**
The `stack_type` parameter was directly concatenated with `TEMPLATES_DIR` without validation. If an attacker controlled this parameter, they could provide a malicious input like `../../../etc/passwd` to traverse out of the templates directory. Depending on how the method is used and if it processes arbitrary files, this could lead to reading arbitrary files or overriding critical files.

🛡️ **Solution:**
Added strict validation by resolving both the `template_dir` and the `TEMPLATES_DIR` to absolute paths and enforcing that the `template_dir` is an exact child of `TEMPLATES_DIR` (using `template_dir.parent == base_dir`). This blocks any input containing multiple directories or absolute paths.
Also added unit tests to assert the correct behavior for traversal payloads.
