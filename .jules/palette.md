## $(date +%Y-%m-%d) - Adding aria-labels to missing inputs
**Learning:** In `site_builder_edit.html` dynamic widget form inputs (Heading text, Image URL, Alt text, Button label, Button URL) lack `aria-label`s. Screen reader users navigating through these dynamic forms won't hear what the inputs are for.
**Action:** Always include `aria-label`s on dynamically generated form inputs when visible labels are omitted to save space. I will add `aria-label`s to these 5 inputs.
