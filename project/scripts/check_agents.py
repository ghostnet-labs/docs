"""Validate agent instructions as a maintained Markdown entry point."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
path = root / "AGENTS.md"
text = path.read_text(encoding="utf-8")
if not text.strip() or not re.search(r"(?m)^# \S", text):
    raise SystemExit("AGENTS.md needs a title and nonempty instructions")
if text.count("```") % 2:
    raise SystemExit("AGENTS.md has an unclosed fenced block")
for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
    if "://" in link or link.startswith("#"):
        continue
    target = (root / link.split("#")[0]).resolve()
    if not target.is_relative_to(root) or not target.exists():
        raise SystemExit("Broken or out-of-repository AGENTS.md link: " + link)
print("AGENTS.md is readable Markdown with valid local links")
