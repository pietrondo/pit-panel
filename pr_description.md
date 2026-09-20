💡 What: Added `aria-live="polite"` to the loading state message on the system upgrade button.
🎯 Why: Without `aria-live`, screen readers would not proactively announce the text change to "Upgrading..." when the user clicks the button. This ensures that users relying on screen readers receive immediate feedback that the long-running upgrade process has started.
♿ Accessibility: Ensures the dynamic loading text update is announced by screen readers.
