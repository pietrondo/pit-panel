1. **Update Settings in `config.py`**:
   - Add `backup_enabled: bool = False` to `Settings`.
   - Add `backup_retention_days: int = 7` to `Settings`.
   - Update `save_config_file` to save these new fields.
2. **Extract Backup Logic in `ops.py`**:
   - Extract the core backup logic from `app_backup_run` into a separate function `perform_app_backup(sd, db, settings, user_id, ip, user_agent)`. Note: we can keep it in `ops.py` and import it in `app.py`, but it might be better to put it in a new file `src/pit_panel/core/backup.py` and move `_get_db_service_info` there as well, or just keep it in `ops.py` for now, or move to `backup.py` to avoid circular imports.
   - Let's create `src/pit_panel/core/backup.py` and move `_get_db_service_info` and `perform_app_backup` there.
   - Update `app_backup_run` in `ops.py` to call `perform_app_backup`.
3. **Implement Scheduled Backup Loop**:
   - In `src/pit_panel/core/backup.py`, create `scheduled_backup_loop()`.
   - It will sleep for 24 hours in a loop.
   - Fetch all subdomains with `app_type != None`.
   - Call `perform_app_backup` for each.
   - Implement retention logic: delete files in `backup_dir` older than `settings.backup_retention_days`.
4. **Update `app.py`**:
   - Add `scheduled_backup_loop` to the background tasks in `_lifespan`.
5. **Update Tests**:
   - Add tests for `perform_app_backup` and `scheduled_backup_loop` in a new file `tests/unit/test_backup.py`.
   - Update `tests/unit/test_app.py` for the new background task count.
6. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
