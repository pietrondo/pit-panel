import re
with open("tests/unit/test_system.py", "r") as f:
    content = f.read()

# I am assuming the test fails because it checks for b"OK" in response.content, which was present when the button showed "Upgrading..." conditionally, but we changed the markup.
# Let's check what response.content actually contains. It's an HTML fragment or full page?
# The route system/upgrade in `src/pit_panel/web/routes/system.py` probably returns a fragment or text.
