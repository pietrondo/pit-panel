from pit_panel.security.bug_analyzer import classify_log_line, group_log_issues


def test_classify_log_line_ignores_static_resource_noise():
    line = (
        "13:33:20.961 [jetty-971] WARN s.s.S.e.GlobalExceptionHandler - "
        "No resource at /api/v1/policies: No static resource api/v1/policies "
        "for request '/api/v1/policies'."
    )

    assert classify_log_line(line) is None


def test_classify_log_line_detects_real_exception_group():
    issue = classify_log_line(
        "Jul 02 05:51:12 racknerd python[342996]: | ExceptionGroup: "
        "unhandled errors in a TaskGroup (1 sub-exception)"
    )

    assert issue is not None
    assert issue["severity"] == "critical"
    assert "TaskGroup" in issue["message"]
    assert issue["hint"]


def test_group_log_issues_deduplicates_by_fingerprint():
    lines = [
        "2026-07-02 10:00:00 ERROR Database timeout for app 123",
        "2026-07-02 10:01:00 ERROR Database timeout for app 456",
        "2026-07-02 10:02:00 WARNING Cache miss for key abc",
    ]

    issues = group_log_issues(lines)

    assert len(issues) == 2
    assert issues[0]["severity"] == "error"
    assert issues[0]["count"] == 2
    assert issues[1]["severity"] == "warning"
