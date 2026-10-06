import os
import re
import shutil
import subprocess

import pytest
import yaml

from routeiq import demo
from routeiq.config import ROOT

SCRIPT = ROOT / "scripts" / "publish_space.sh"
SPACE_README = ROOT / "deploy" / "huggingface" / "README.md"
DEPLOY_GUIDE = ROOT / "deploy" / "huggingface" / "DEPLOY.md"

FRONT_MATTER = "---\ntitle: Demo\nsdk: docker\napp_port: 8000\n---\n\n# the space\n"


def isolated_env():
    """An environment in which git can reach nobody: no saved passwords (keychain helper), no ssh keys or
    agent, no prompts. The script under test can push, so whatever goes wrong with it, nothing may leave
    this machine. (Once a test run with a deliberately broken script force-pushed over a real repository.)"""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SSH_", "GIT_", "GH_", "GITHUB_", "HF_"))}
    env.update(
        HOME="/nonexistent-home", XDG_CONFIG_HOME="/nonexistent-home",
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="false", GIT_SSH_COMMAND="false",
    )
    return env


def run(*args, cwd=None):
    return subprocess.run(["bash", *map(str, args)], capture_output=True, text=True, cwd=cwd, env=isolated_env())


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo, check=True, capture_output=True, env=isolated_env(),
    )


@pytest.fixture
def repo(tmp_path):
    """A small git repository with the script in it, the way it is used. It is a test fixture: the
    commits made here are in a temporary folder."""
    folder = tmp_path / "repo"
    (folder / "scripts").mkdir(parents=True)
    (folder / "deploy" / "huggingface").mkdir(parents=True)
    shutil.copy(SCRIPT, folder / "scripts" / "publish_space.sh")
    (folder / "Dockerfile").write_text("FROM python:3.13-slim\nCMD [\"uvicorn\"]\n")
    (folder / "README.md").write_text("# the project readme\n")
    (folder / "app.py").write_text("print('app')\n")
    (folder / ".gitignore").write_text(".env\n.venv/\n")
    (folder / "deploy" / "huggingface" / "README.md").write_text(FRONT_MATTER)
    git(folder, "init", "-q", "-b", "main")
    git(folder, "add", "-A")
    git(folder, "commit", "-q", "-m", "first")
    (folder / ".env").write_text("OPENROUTER_API_KEY=sk-secret\n")          # untracked, ignored
    return folder


def preview(repo, tmp_path, name="out"):
    out = tmp_path / name
    result = run(repo / "scripts" / "publish_space.sh", "--dry-run", out)
    return result, out


# --- what would be sent ----------------------------------------------------------------------------------

def test_the_space_gets_its_own_readme_in_place_of_the_project_readme(repo, tmp_path):
    result, out = preview(repo, tmp_path)
    assert result.returncode == 0, result.stderr
    assert (out / "README.md").read_text() == FRONT_MATTER


def test_the_dockerfile_gets_a_last_line_that_switches_demo_mode_on(repo, tmp_path):
    _, out = preview(repo, tmp_path)
    lines = (out / "Dockerfile").read_text().splitlines()
    assert lines[:2] == ["FROM python:3.13-slim", 'CMD ["uvicorn"]']
    assert lines[-1] == "ENV ROUTEIQ_DEMO=1"


def test_the_repository_itself_is_not_changed(repo, tmp_path):
    preview(repo, tmp_path)
    assert (repo / "README.md").read_text() == "# the project readme\n"
    assert "ROUTEIQ_DEMO" not in (repo / "Dockerfile").read_text()


def test_the_committed_files_go_along(repo, tmp_path):
    _, out = preview(repo, tmp_path)
    assert (out / "app.py").read_text() == "print('app')\n"
    assert (out / "deploy" / "huggingface" / "README.md").exists()


def test_a_secret_that_is_not_committed_never_goes(repo, tmp_path):
    _, out = preview(repo, tmp_path)
    assert not (out / ".env").exists()
    assert "sk-secret" not in "".join(p.read_text() for p in out.rglob("*") if p.is_file())


def test_a_file_that_is_not_committed_does_not_go(repo, tmp_path):
    (repo / "notes.txt").write_text("draft\n")
    _, out = preview(repo, tmp_path)
    assert not (out / "notes.txt").exists()


def test_a_change_that_is_not_committed_does_not_go_and_the_script_says_so(repo, tmp_path):
    (repo / "app.py").write_text("print('changed')\n")
    result, out = preview(repo, tmp_path)
    assert (out / "app.py").read_text() == "print('app')\n"
    assert "uncommitted changes" in result.stderr and "NOT published" in result.stderr


def test_a_clean_repository_gets_no_warning(repo, tmp_path):
    result, _ = preview(repo, tmp_path)
    assert result.stderr == ""
    assert "Built what would be sent" in result.stdout


# --- what it refuses ------------------------------------------------------------------------------------------

def test_a_folder_that_is_not_empty_is_refused(repo, tmp_path):
    out = tmp_path / "taken"
    out.mkdir()
    (out / "something").write_text("x")
    result = run(repo / "scripts" / "publish_space.sh", "--dry-run", out)
    assert result.returncode == 1 and "is not empty" in result.stderr
    assert (out / "something").read_text() == "x"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/ebubekirylmaz/routeiq.git",
        "git@github.com:ebubekirylmaz/routeiq.git",
        "https://huggingface.co/ebubekirylmaz/some-model",
        "https://huggingface.co/spaces/only-a-user",
        "../elsewhere",
        "",
    ],
)
def test_it_will_not_push_to_anything_that_is_not_a_space(repo, url):
    result = run(repo / "scripts" / "publish_space.sh", url)
    assert result.returncode == 1
    assert "does not look like a Hugging Face Space" in result.stderr


def test_without_arguments_it_explains_how_to_use_it(repo):
    result = run(repo / "scripts" / "publish_space.sh")
    assert result.returncode == 2 and "usage:" in result.stderr


def test_the_dry_run_needs_a_folder(repo):
    assert run(repo / "scripts" / "publish_space.sh", "--dry-run").returncode == 2


def test_it_stops_when_the_space_readme_is_not_committed(repo, tmp_path):
    git(repo, "rm", "-q", "deploy/huggingface/README.md")
    git(repo, "commit", "-q", "-m", "remove")
    result, _ = preview(repo, tmp_path)
    assert result.returncode == 1 and "deploy/huggingface/README.md is not committed" in result.stderr


def test_it_stops_in_a_folder_that_is_not_a_repository(tmp_path):
    folder = tmp_path / "plain"
    (folder / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, folder / "scripts" / "publish_space.sh")
    result = run(folder / "scripts" / "publish_space.sh", "--dry-run", tmp_path / "out")
    assert result.returncode == 1 and "is not a git repository" in result.stderr


# --- the files of this repository -------------------------------------------------------------------------------

def front_matter(path):
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "the README of the Space must start with its settings between --- lines"
    return yaml.safe_load(match.group(1))


def test_the_space_readme_asks_for_a_docker_space_on_the_port_of_the_service():
    settings = front_matter(SPACE_README)
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert settings["sdk"] == "docker"
    assert settings["app_port"] == int(re.search(r"^EXPOSE (\d+)", dockerfile, re.M).group(1))
    assert f"--port\", \"{settings['app_port']}\"" in dockerfile


def test_the_space_settings_are_complete_and_within_the_limits_of_the_platform():
    settings = front_matter(SPACE_README)
    assert {"title", "emoji", "colorFrom", "colorTo", "sdk", "app_port", "license", "short_description"} <= set(settings)
    assert len(settings["short_description"]) <= 60
    assert settings["license"] == "mit"


def test_the_space_readme_tells_visitors_what_happens_to_what_they_type():
    text = SPACE_README.read_text()
    for promise in ("stored", "everyone using this demo", "personal data", "resets", "500 characters", "CC BY 3.0"):
        assert promise in text, promise


def test_the_regular_dockerfile_does_not_switch_demo_mode_on():
    assert "ROUTEIQ_DEMO" not in (ROOT / "Dockerfile").read_text()


def test_the_guide_names_every_setting_of_the_demo():
    guide = DEPLOY_GUIDE.read_text()
    for name, _kind in demo.ENVIRONMENT.values():
        assert name in guide, name
    assert "ROUTEIQ_DEMO_DB" in guide and "ROUTEIQ_DEMO=1" in guide


def test_the_guide_defaults_are_the_ones_in_the_code():
    guide, defaults = DEPLOY_GUIDE.read_text(), demo.DemoSettings()
    assert f"{defaults.routes_per_minute} a minute" in guide
    assert f"{defaults.routes_per_day} a day" in guide
    assert f"{defaults.writes_per_minute} a minute" in guide
    assert f"{defaults.max_text} characters" in guide
    assert f"every {int(defaults.reset_hours)} hours" in guide
    assert f"{defaults.max_body // 1024} KB" in guide


def test_the_script_is_executable_and_refuses_what_it_should_in_this_repository(tmp_path):
    assert SCRIPT.stat().st_mode & 0o111
    result = run(SCRIPT, "https://github.com/ebubekirylmaz/routeiq.git")
    assert result.returncode == 1


def test_the_isolated_environment_has_no_way_to_log_in_anywhere(tmp_path):
    """The guarantee the other tests rest on: git run in it has no credential helper, no ssh and no prompt."""
    env = isolated_env()
    helpers = subprocess.run(["git", "config", "--get-all", "credential.helper"], capture_output=True, text=True, env=env)
    assert helpers.stdout.strip() == ""
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_SSH_COMMAND"] == "false"
    assert not any(name.startswith("SSH_") for name in env)
    assert env["HOME"] == "/nonexistent-home"

