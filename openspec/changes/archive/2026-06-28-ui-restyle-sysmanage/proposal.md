# Proposal: UI Restyling and SysManage Integration

## 1. Executive Summary
This proposal outlines the UI/UX revitalization of `pit-panel` and complete integration of the Debian System Management (`SysManage`) page. The changes focus on typography, active state routing feedback, dynamic app status reporting, and terminal outputs restyling.

## 2. Problem Statement
The current interface uses browser default typography, lacks visual feedback for the active sidebar route, hides app container statuses behind detail views, and displays SysManage shell outputs as raw text.

## 3. Proposed Changes
- **Typography & Aesthetics**: Load Google Fonts (`Inter`, `Outfit`, `JetBrains Mono`) in [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html) and add CSS/Tailwind details (gradients, card animations).
- **Sidebar Integration**: Implement inline JS in [base.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/base.html) to dynamically toggle `.active` (indigo highlights) on sidebar links matching `window.location.pathname`.
- **Dynamic App List**: Upgrade `/apps` ([apps.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/apps.html)) to show container counts. Modify [apps.py](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/routes/apps.py) to supply these counts.
- **SysManage Integration**: Restyle tabs and replace the plain `<pre id="result">` in [system_manage.html](file:///C:/Users/pietr/progetti/pit-panel/src/pit_panel/web/templates/system_manage.html) with a retro terminal emulator (window decorations, neon text).

## 4. Capabilities
### New Capabilities
- **Sidebar Active Path Auto-detection**: Automatically highlights sidebar items based on current path.
- **Terminal Emulator Styling**: Faux terminal window skin for shell outputs.

### Modified Capabilities
- **App List Interface**: Real-time container states/badge view.
- **SysManage Layout**: Standardized UI tabs and service control grid.

## 5. Success Criteria
1. Navigation matches sidebar highlights seamlessly (e.g. `/system/manage` highlights).
2. The `/apps` dashboard displays container counts dynamically.
3. System outputs render inside a styled mock terminal component.
4. All existing tests pass via `uv run pytest`.

## 6. Rollback Plan
Since the database schema is unaffected and modifications are frontend templates plus safe async API extensions, rollback is accomplished by reverting commits:
```bash
git checkout main
git revert <commit-hashes>
```
