"""Guard against docker-compose referencing a build context with no Dockerfile."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def _build_contexts(compose: dict) -> list[Path]:
    contexts = []
    for service in compose.get("services", {}).values():
        build = service.get("build")
        if not build:
            continue
        # build may be a string path or a mapping with a `context` key.
        ctx = build if isinstance(build, str) else build.get("context", ".")
        contexts.append((REPO_ROOT / ctx).resolve())
    return contexts


def test_compose_file_exists():
    assert COMPOSE_FILE.is_file(), "docker-compose.yml missing from repo root"


def test_every_build_context_has_a_dockerfile():
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    contexts = _build_contexts(compose)
    assert contexts, "expected at least one service with a build context"
    for ctx in contexts:
        dockerfile = ctx / "Dockerfile"
        assert dockerfile.is_file(), f"build context {ctx} has no Dockerfile"


def test_backend_dockerfile_exposes_the_app():
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    # The compose command runs `uvicorn app.main:app`, so the image must install
    # deps, copy the app package, and provide tesseract for OCR.
    assert "requirements.txt" in dockerfile
    assert "COPY app" in dockerfile
    assert "tesseract-ocr" in dockerfile
