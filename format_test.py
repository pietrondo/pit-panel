def fix():
    with open("tests/unit/test_backup.py") as f:
        content = f.read()

    bad = """    with (
        patch("pit_panel.core.backup.perform_app_backup", new_callable=AsyncMock),
        patch("pathlib.Path.unlink", side_effect=Exception("Unlink failed")),
    ):
        with pytest.raises(asyncio.CancelledError):
            await scheduled_backup_loop()"""

    good = """    with (
        patch("pit_panel.core.backup.perform_app_backup", new_callable=AsyncMock),
        patch("pathlib.Path.unlink", side_effect=Exception("Unlink failed")),
        pytest.raises(asyncio.CancelledError),
    ):
        await scheduled_backup_loop()"""

    content = content.replace(bad, good)
    with open("tests/unit/test_backup.py", "w") as f:
        f.write(content)

fix()
