from pathlib import Path

from scripts.check_design_docs import check_design_docs


def _fixture_repo(tmp_path: Path) -> Path:
    diagrams = tmp_path / "docs" / "diagrams"
    diagrams.mkdir(parents=True)
    for name in (
        "ai-evaluation-service-poc-english-01 Service Architecture.drawio.png",
        "ai-evaluation-service-poc-english-architecture.drawio.svg",
        "ai-evaluation-service-poc-english-async-flow.drawio.svg",
        "ai-evaluation-service-poc-english-state-hitl.drawio.svg",
        "ai-evaluation-service-poc-english.drawio",
        "ai-evaluation-service-poc.drawio",
    ):
        (diagrams / name).write_text("diagram", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "![Architecture](docs/diagrams/ai-evaluation-service-poc-english-01%20Service%20Architecture.drawio.png)\n"
        "[SVG](docs/diagrams/ai-evaluation-service-poc-english-architecture.drawio.svg)\n"
        "[Flow](docs/diagrams/ai-evaluation-service-poc-english-async-flow.drawio.svg)\n"
        "[HITL](docs/diagrams/ai-evaluation-service-poc-english-state-hitl.drawio.svg)\n"
        "[English](docs/diagrams/ai-evaluation-service-poc-english.drawio)\n"
        "[Chinese](docs/diagrams/ai-evaluation-service-poc.drawio)\n",
        encoding="utf-8",
    )
    return tmp_path


def test_current_readme_links_all_maintained_design_artifacts() -> None:
    assert check_design_docs(Path(__file__).resolve().parents[2]) == []


def test_missing_architecture_embed_is_reported(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("![Architecture]", "[Architecture]"),
        encoding="utf-8",
    )

    assert "architecture preview must be embedded" in check_design_docs(repo)


def test_missing_diagram_file_is_reported(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    (repo / "docs/diagrams/ai-evaluation-service-poc-english-async-flow.drawio.svg").unlink()

    assert (
        "missing diagram file: "
        "docs/diagrams/ai-evaluation-service-poc-english-async-flow.drawio.svg"
    ) in check_design_docs(repo)
