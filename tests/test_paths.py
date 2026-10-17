"""
Where this install is, and how it runs itself, from a checkout and from a wheel.

Interfaces: contract/paths (PACKAGE_DIR, CHECKOUT, cli_argv, mcp_argv,
default_project_dir) and contract/manifest.config_root's fallback.
Infrastructure: none — the installed half is the same functions with CHECKOUT
patched to None, and tests/qe/install's `installed-wheel` cell drives a real wheel.
Scope: the two modes give different answers for exactly the facts that depend on a
checkout, and the same answer for the package's own files.
"""

import sys
from pathlib import Path

from thalamus.contract import manifest, paths

REPO = Path(__file__).resolve().parents[1]


def test_the_package_dir_is_the_package_these_modules_were_loaded_from():
    assert paths.PACKAGE_DIR == REPO / "src" / "thalamus"
    assert (paths.PACKAGE_DIR / "harness" / "hooks" / "claude-code").is_dir()


def test_run_from_this_checkout_the_checkout_is_found():
    assert paths.CHECKOUT == REPO
    assert paths.INSTALL_IDENTITY == str(REPO)


def test_a_package_outside_a_src_tree_has_no_checkout(tmp_path, monkeypatch):
    """The wheel layout: `site-packages/thalamus/`, whose parent is not `src`. A
    `pyproject.toml` two levels up does not make it one."""
    pkg = tmp_path / "lib" / "site-packages" / "thalamus"
    pkg.mkdir(parents=True)
    (tmp_path / "lib" / "pyproject.toml").write_text("")
    monkeypatch.setattr(paths, "PACKAGE_DIR", pkg)

    assert paths._checkout() is None


def test_a_src_tree_without_pyproject_is_not_a_checkout(tmp_path, monkeypatch):
    pkg = tmp_path / "src" / "thalamus"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(paths, "PACKAGE_DIR", pkg)

    assert paths._checkout() is None
    (tmp_path / "pyproject.toml").write_text("")
    assert paths._checkout() == tmp_path, "the control: the same tree with the file is one"


class TestTheCommandThatRunsThisInstall:
    def test_a_checkout_runs_through_uv_against_itself(self):
        assert paths.cli_argv("extract") == ["uv", "run", "--project", str(REPO),
                                             "thalamus", "extract"]
        assert paths.mcp_argv() == ["uv", "run", "--project", str(REPO), "thalamus-mcp"]

    def test_an_installed_wheel_runs_under_its_own_interpreter(self, monkeypatch):
        monkeypatch.setattr(paths, "CHECKOUT", None)

        assert paths.cli_argv("extract") == [sys.executable, "-m", "thalamus", "extract"]
        assert paths.mcp_argv() == [sys.executable, "-m", "thalamus.harness.mcp_server"]

    def test_both_module_forms_are_runnable(self):
        """`-m thalamus` needs a `__main__`, and the MCP module needs its own guard."""
        assert (paths.PACKAGE_DIR / "__main__.py").is_file()
        source = (paths.PACKAGE_DIR / "harness" / "mcp_server.py").read_text()
        assert 'if __name__ == "__main__":' in source


class TestWhereASessionOpens:
    def test_from_a_checkout_it_is_the_checkout(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert paths.default_project_dir() == REPO

    def test_from_a_wheel_it_is_where_the_command_was_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "CHECKOUT", None)
        monkeypatch.chdir(tmp_path)
        assert paths.default_project_dir() == tmp_path


def test_a_wheel_reads_the_users_config_when_nothing_names_one(tmp_path, monkeypatch):
    monkeypatch.delenv("THALAMUS_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(paths, "CHECKOUT", None)

    assert manifest.config_root() == tmp_path / ".thalamus" / "config"
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", "/elsewhere")
    assert manifest.config_root() == Path("/elsewhere"), "the override still wins"
