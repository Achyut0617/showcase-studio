from pathlib import Path

from showcase.sandbox import SandboxLimits, docker_run_args


def pairs(args):
    return list(zip(args, args[1:], strict=False))


def test_default_args_are_locked_down(tmp_path):
    args = docker_run_args("showcase-sandbox:base", tmp_path, ["python", "-V"])
    assert args[:3] == ["docker", "run", "--rm"]
    p = pairs(args)
    assert ("--network", "none") in p
    assert ("--memory", "4g") in p
    assert ("--cpus", "2.0") in p
    assert ("--pids-limit", "256") in p
    assert ("--cap-drop", "ALL") in p
    assert ("--security-opt", "no-new-privileges") in p
    assert ("--user", "runner") in p
    assert args[-3:] == ["showcase-sandbox:base", "python", "-V"]


def test_network_can_be_enabled(tmp_path):
    args = docker_run_args("img", tmp_path, ["true"], SandboxLimits(network=True))
    assert "--network" not in args


def test_only_input_dir_is_mounted_even_with_spaces(tmp_path):
    job_input = tmp_path / "my jobs" / "input"
    job_input.mkdir(parents=True)
    args = docker_run_args("img", job_input, ["true"])
    mounts = [b for a, b in pairs(args) if a == "-v"]
    assert mounts == [f"{job_input.resolve()}:/work"]


def test_relative_input_dir_is_made_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("input").mkdir()
    args = docker_run_args("img", Path("input"), ["true"])
    mounts = [b for a, b in pairs(args) if a == "-v"]
    assert mounts == [f"{(tmp_path / 'input').resolve()}:/work"]


def test_root_filesystem_is_read_only_by_default(tmp_path):
    args = docker_run_args("img", tmp_path, ["true"])
    assert "--read-only" in args
    assert ("--tmpfs", "/tmp:rw,size=512m") in pairs(args)


def test_read_only_can_be_disabled(tmp_path):
    args = docker_run_args("img", tmp_path, ["true"], SandboxLimits(read_only=False))
    assert "--read-only" not in args and "--tmpfs" not in args
