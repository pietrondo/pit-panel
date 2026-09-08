import subprocess
import json

def create_pr():
    title = "🎨 Palette: Improve file upload accessibility"
    description = """💡 What: Replaced `class="hidden"` with `class="sr-only"` on the file upload input and added focus-within styles to the surrounding label.
🎯 Why: `class="hidden"` prevents the input from receiving keyboard focus, making it inaccessible to keyboard users and screen readers.
📸 Before/After: Visual focus ring now appears when navigating via keyboard.
♿ Accessibility: Ensures keyboard accessibility and proper focus state for the file upload input."""

    print("Creating PR...")
    print(f"Title: {title}")
    print(f"Description:\n{description}")

if __name__ == "__main__":
    create_pr()
