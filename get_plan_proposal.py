plan = """
I will fix the UX/a11y issues found by adding ARIA labels to buttons lacking textual descriptions and ensuring proper button states.

1.  **Add ARIA label to "Cancel" in file upload modal** in `src/pit_panel/web/templates/file_manager.html`.
    - I'll replace `<button @click="uploadOpen = false" class="btn btn-ghost">Cancel</button>` with `<button aria-label="Cancel file upload" @click="uploadOpen = false" class="btn btn-ghost">Cancel</button>`.
2.  **Add ARIA label to "Sblocca" in security unban form** in `src/pit_panel/web/templates/security.html`.
    - I'll replace `<button class="text-green-600 hover:text-green-800 font-medium">Sblocca</button>` with `<button aria-label="Sblocca IP" class="text-green-600 hover:text-green-800 font-medium">Sblocca</button>`.
3.  **Add ARIA label to "Revoca" in security session revoke form** in `src/pit_panel/web/templates/security.html`.
    - I'll replace `<button class="text-red-600 hover:text-red-800 font-medium">Revoca</button>` with `<button aria-label="Revoca Sessione" class="text-red-600 hover:text-red-800 font-medium">Revoca</button>`.
4.  **Add ARIA label to "Clear" button** in `src/pit_panel/web/templates/system_manage.html` (if missing or incorrect label context, although "Clear" was found to have an aria-label). I will skip if it's there. Actually, I will add `aria-label` to the 'x' buttons in `src/pit_panel/web/templates/site_builder_edit.html`.
    - `site_builder_edit.html` has multiple `&times;` (x) buttons for removing columns and widgets. I will add `aria-label="Remove column"` and `aria-label="Remove widget"`.
5.  **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
6.  **Submit PR using Bolt's PR title syntax.** But wait, I'm Palette! So I will use Palette's PR format.
    - Submit branch `jules/palette-a11y-labels` with a PR using Palette's format `🎨 Palette: [UX improvement]`.
"""
print(plan)
