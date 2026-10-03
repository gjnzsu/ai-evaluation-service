"""Check the README contract for the maintained POC design diagrams."""

import re
from pathlib import Path

DIAGRAMS = (
    "docs/diagrams/ai-evaluation-service-poc-english-architecture.drawio.svg",
    "docs/diagrams/ai-evaluation-service-poc-english-async-flow.drawio.svg",
    "docs/diagrams/ai-evaluation-service-poc-english-state-hitl.drawio.svg",
    "docs/diagrams/ai-evaluation-service-poc-english.drawio",
    "docs/diagrams/ai-evaluation-service-poc.drawio",
)


def check_design_docs(root: Path) -> list[str]:
    readme_path = root / "README.md"
    if not readme_path.is_file():
        return ["missing README.md"]

    readme = readme_path.read_text(encoding="utf-8")
    errors = []
    architecture = DIAGRAMS[0]
    if not re.search(r"!\[[^\]]*\]\(" + re.escape(architecture) + r"\)", readme):
        errors.append("architecture preview must be embedded")

    for diagram in DIAGRAMS:
        if f"]({diagram})" not in readme:
            errors.append(f"README does not link: {diagram}")
        if not (root / diagram).is_file():
            errors.append(f"missing diagram file: {diagram}")
    return errors
