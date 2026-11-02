"""LICENSE едет в образ движка (Dockerfile читается как текст, Docker не нужен)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _stages(text: str) -> list[list[str]]:
    stages: list[list[str]] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("FROM "):
            stages.append([])
        elif stages and s and not s.startswith("#"):
            stages[-1].append(s)
    return stages


def _dockerfile() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_build_stage_copies_license_with_pyproject():
    build = _stages(_dockerfile())[0]
    lines = [x for x in build if x.startswith("COPY") and "pyproject.toml" in x]
    assert lines and all("LICENSE" in x.split() for x in lines)


def test_final_stage_copies_license_before_user():
    assert _final_ok(_dockerfile())


def _final_ok(text: str) -> bool:
    final = _stages(text)[-1]
    if "COPY LICENSE /opt/heron/LICENSE" not in final:
        return False
    user = next(i for i, x in enumerate(final) if x.startswith("USER "))
    return final.index("COPY LICENSE /opt/heron/LICENSE") < user


def test_mutation_without_final_license_fails():
    mutated = _dockerfile().replace("COPY LICENSE /opt/heron/LICENSE\n", "")
    assert not _final_ok(mutated)


def test_dockerignore_keeps_license():
    for raw in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith(("#", "!")):
            assert s.strip("/*") != "LICENSE"
            assert s not in ("LICENSE*", "*LICENSE", "*")
