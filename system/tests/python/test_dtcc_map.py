import subprocess
from pathlib import Path

from helpers import concept, write
from vaultlib import dtcc_map

MAP = """partition: work
hub: '[[Dtcc]]'
notice_keywords: ['\\bI&RS\\b']
codebases:
  app: {ref: HEAD}
products:
  stl:
    page: settlement-processing-for-insurance-stl
    notice_codes: [STL]
    codebase: app
    paths: [src/stl/, docs/gone.xlsx]
    pin: v25-3
    notes: ['[[StlBackground]]']
ignore: [PAR]
"""


def repo(tmp_path: Path) -> Path:
    r = tmp_path / "app"
    (r / "src" / "stl").mkdir(parents=True)
    (r / "src" / "stl" / "a.cs").write_text("x")
    for args in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "i"]):
        subprocess.run(["git", "-C", str(r), *args], check=True)
    return r


def setup_vault(vault: Path, tmp_path: Path, text: str = MAP) -> None:
    r = repo(tmp_path)
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: "app"\npath: "{r}"\npartition: "work"\nsearch_globs: ["*"]\n---\n')
    write(vault, "wiki/work/entities/Dtcc.md", concept("work", "DTCC"))
    write(vault, "wiki/work/concepts/StlBackground.md", concept("work", "STL"))
    write(vault, dtcc_map.MAP, text)


def test_no_map(vault: Path):
    assert dtcc_map.load(vault) == (None, None)


def test_bad_yaml(vault: Path):
    write(vault, dtcc_map.MAP, "partition: [")
    m, err = dtcc_map.load(vault)
    assert m is None and err


def test_valid_map(vault: Path, tmp_path: Path):
    setup_vault(vault, tmp_path)
    m, err = dtcc_map.load(vault)
    assert err is None
    assert dtcc_map.validate(m, vault) == []


def test_invalid_map_lists_every_problem(vault: Path, tmp_path: Path):
    setup_vault(vault, tmp_path, MAP.replace("v25-3", "25.3")
                .replace("[[StlBackground]]", "[[Missing]]").replace("ref: HEAD", "ref: no-such-ref"))
    errs = dtcc_map.validate(dtcc_map.load(vault)[0], vault)
    assert any("pin" in e for e in errs)
    assert any("Missing" in e for e in errs)
    assert any("no-such-ref" in e for e in errs)


def test_bad_partition(vault: Path, tmp_path: Path):
    setup_vault(vault, tmp_path, MAP.replace("partition: work", "partition: nope"))
    assert any("partition" in e for e in dtcc_map.validate(dtcc_map.load(vault)[0], vault))


def test_stale_paths(vault: Path, tmp_path: Path):
    setup_vault(vault, tmp_path)
    m, _ = dtcc_map.load(vault)
    assert dtcc_map.stale_paths(m, vault) == [("stl", "docs/gone.xlsx", "HEAD")]
