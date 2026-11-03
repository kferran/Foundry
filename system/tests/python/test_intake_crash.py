"""intake.py's own tick turns an escaping exception into exit 70 and one alert a day (#436, the F6 crash gaps)."""
import os
import subprocess
import sys

DRIVER = """
import runpy, sys
import vaultlib.intake as m
def boom(self):
    raise RuntimeError("injected")
m.Intake.run = boom
sys.argv = [sys.argv[1]] + sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def run_intake(vault, *args):
    scripts = vault / "system" / "scripts"
    env = {k: v for k, v in os.environ.items() if k != "VAULT_ROOT"}
    env["PYTHONPATH"] = str(scripts)
    return subprocess.run([sys.executable, "-c", DRIVER, str(scripts / "intake.py"), *args],
                          cwd=vault, env=env, capture_output=True, text=True)


def crash_lines(vault):
    return [line for p in (vault / "system" / "logs").glob("alerts_*.md")
            for line in p.read_text().splitlines() if "foundry-intake crashed:" in line]


def test_the_tick_exits_70_and_alerts_once_a_day(vault, cli):
    (vault / "system" / "logs").mkdir(parents=True, exist_ok=True)
    first = run_intake(vault)
    assert first.returncode == 70, first.stderr
    assert "RuntimeError: injected" in first.stderr   # the traceback reaches the journal
    assert len(crash_lines(vault)) == 1
    assert "[intake] foundry-intake crashed: RuntimeError; journalctl --user -u foundry-intake" in crash_lines(vault)[0]
    assert run_intake(vault).returncode == 70
    assert len(crash_lines(vault)) == 1   # once a day


def test_a_command_from_a_person_or_the_prep_does_not_take_the_guard(vault, cli):
    (vault / "system" / "logs").mkdir(parents=True, exist_ok=True)
    out = run_intake(vault, "--quarantine")
    assert out.returncode == 0, out.stderr
    assert crash_lines(vault) == []
