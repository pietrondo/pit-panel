The goal is to improve test coverage by continuously adding new functional tests and code, per the "Crea sempri nuove tests di funzionamento e codice" user directive. I've focused on `src/pit_panel/web/routes/app_routes/main.py`.

I've written a number of targeted unit tests covering several untested functions in `main.py`, specifically:
- `_patch_vite_allowed_hosts`
- `_get_db_password`
- `_has_db_container`
- `app_analyze_repo`
- `_resolve_subdomain`
- `_render_apps_error`
- `_auto_setup_wordpress`

The coverage of `main.py` has successfully increased from 45% (219 missed statements) to 56% (175 missed statements) when run against my temporary scratchpad test file `tests/unit/routes/app_routes/test_main_script.py`.

My plan is to persist these tests by creating `tests/unit/routes/app_routes/test_main_script.py` and submit the changes to increase the overall test coverage.

```
1. Add new functional tests in `tests/unit/routes/app_routes/test_main_script.py` using `run_in_bash_session`.
2. Verify tests and coverage using `run_in_bash_session`.
3. Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.
4. Submit the branch.
```
