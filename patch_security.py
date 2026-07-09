with open('src/pit_panel/web/routes/security.py', 'r') as f:
    content = f.read()

old_block = """async def _rollback_after_db_panel_error(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass"""

new_block = """async def _rollback_after_db_panel_error(db: AsyncSession) -> None:
    import contextlib
    with contextlib.suppress(Exception):
        await db.rollback()"""

content = content.replace(old_block, new_block)

with open('src/pit_panel/web/routes/security.py', 'w') as f:
    f.write(content)
