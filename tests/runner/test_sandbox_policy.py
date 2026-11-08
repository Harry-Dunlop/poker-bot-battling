"""Sandbox policy guard (design-doc §4.1).

If a test here fails, someone weakened the bot sandbox. Fix the sandbox, not the
test. Loosening a rule here needs Harry's explicit sign-off in docs/claude-context.md.
"""

from pathlib import Path

import pytest

from pbb.runner.docker import OPEN, STANDARD, THREAD_ENV, docker_run_args

SPECS = {"standard": STANDARD, "open": OPEN}

# Hard ceilings per ladder. Raising one is a design decision, not a refactor.
CEILINGS = {
    "standard": {"memory": "512m", "pids": 64, "cpus": 1.0},
    "open": {"memory": "2g", "pids": 64, "cpus": 1.0},
}

REQUIRED = (
    "--runtime=runsc",
    "--network=none",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--rm",
)

# Any argument starting with one of these must never appear.
FORBIDDEN_PREFIXES = (
    "--privileged",
    "--cap-add",
    "--device",
    "--pid",
    "--ipc",
    "--uts",
    "--userns",
    "--cgroupns",
    "--cgroup-parent",
    "--network=host",
    "--net",
    "--publish",
    "-p",
    "--expose",
    "--mount",
    "--volumes-from",
    "--env-file",
    "--add-host",
    "--dns",
    "--sysctl",
    "--ulimit",
    "--oom-kill-disable",
    "--security-opt=seccomp",
    "--security-opt=apparmor",
    "--security-opt=label",
    "--security-opt=systempaths",
    "--group-add",
    "--entrypoint",
)


def _args(spec):
    return docker_run_args(
        match_id="m1",
        seat=0,
        bot_id="b1",
        bots_root=Path("/srv/bots"),
        spec=spec,
        cidfile=Path("/tmp/cid"),
    )


def _values(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


def _flag_value(args, name):
    vals = [a.split("=", 1)[1] for a in args if a.startswith(name + "=")]
    assert len(vals) == 1, f"{name} must appear exactly once"
    return vals[0]


_UNITS = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30}


def _bytes(size):
    return int(size[:-1]) * _UNITS[size[-1].lower()]


@pytest.fixture(params=sorted(SPECS))
def ladder(request):
    return request.param


def test_required_flags(ladder):
    args = _args(SPECS[ladder])
    for flag in REQUIRED:
        assert args.count(flag) == 1, f"missing or duplicated {flag}"


def test_no_forbidden_flags(ladder):
    args = _args(SPECS[ladder])
    image_at = args.index(SPECS[ladder].image)
    for a in args[:image_at]:  # everything before the image is a docker option
        if a == "--network=none":
            continue
        for bad in FORBIDDEN_PREFIXES:
            assert not (a == bad or a.startswith(bad + "=")), f"forbidden docker flag {a}"
    assert "--network=none" in args and not any(
        a.startswith("--network=") and a != "--network=none" for a in args
    )


def test_runs_as_nobody(ladder):
    assert _values(_args(SPECS[ladder]), "--user") == ["65534:65534"]


def test_only_mount_is_bot_dir_read_only(ladder):
    args = _args(SPECS[ladder])
    assert _values(args, "-v") == [f"{Path('/srv/bots') / 'b1'}:/bot:ro"]
    assert "--volume" not in args
    assert not any("docker.sock" in a for a in args)


def test_tmpfs_is_small_and_noexec(ladder):
    args = _args(SPECS[ladder])
    (tmpfs,) = _values(args, "--tmpfs")
    path, opts = tmpfs.split(":", 1)
    opts = dict(o.split("=", 1) if "=" in o else (o, "") for o in opts.split(","))
    assert path == "/tmp"
    assert {"noexec", "nosuid", "nodev"} <= opts.keys()
    assert _bytes(opts["size"]) <= 64 << 20


def test_resource_ceilings(ladder):
    args, cap = _args(SPECS[ladder]), CEILINGS[ladder]
    mem = _flag_value(args, "--memory")
    assert _bytes(mem) <= _bytes(cap["memory"])
    assert _flag_value(args, "--memory-swap") == mem  # no swap on top of memory
    assert 0 < int(_flag_value(args, "--pids-limit")) <= cap["pids"]
    assert 0 < float(_flag_value(args, "--cpus")) <= cap["cpus"]


def test_env_is_only_thread_settings(ladder):
    # Nothing secret (tokens, keys, DB URLs) may ever be passed into a bot.
    envs = _values(_args(SPECS[ladder]), "-e")
    assert envs == [f"{k}={v}" for k, v in THREAD_ENV.items()]
    assert all(v == "1" for v in THREAD_ENV.values())


def test_command_is_fixed(ladder):
    args = _args(SPECS[ladder])
    assert args[args.index(SPECS[ladder].image) :] == [
        SPECS[ladder].image,
        "python",
        "-u",
        "/bot/main.py",
    ]


def test_starts_with_plain_docker_run(ladder):
    assert _args(SPECS[ladder])[:4] == ["docker", "run", "-i", "--rm"]
