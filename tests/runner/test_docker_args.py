from pathlib import Path

import pytest

from pbb.runner.docker import OPEN, STANDARD, docker_run_args


def args(**kw):
    base = dict(
        match_id="m_123",
        seat=0,
        bot_id="b42",
        bots_root=Path("/srv/bots"),
        spec=STANDARD,
        cidfile=Path("/tmp/cid"),
    )
    return docker_run_args(**(base | kw))


def test_security_flags_present():
    a = args()
    for flag in (
        "--runtime=runsc",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=512m",
        "--memory-swap=512m",
        "--pids-limit=64",
        "--cpus=1",
    ):
        assert flag in a
    assert a[a.index("--user") + 1] == "65534:65534"
    assert "noexec" in a[a.index("--tmpfs") + 1]
    assert a[a.index("-v") + 1].endswith(":/bot:ro")
    assert "--privileged" not in a
    assert not any("docker.sock" in x for x in a)


def test_open_ladder_memory():
    a = args(spec=OPEN)
    assert "--memory=2g" in a and "--memory-swap=2g" in a


@pytest.mark.parametrize("bad", ["../etc", "a b", "x;rm", "", "a/b", "a" * 65])
def test_rejects_unsafe_ids(bad):
    with pytest.raises(ValueError):
        args(bot_id=bad)
    with pytest.raises(ValueError):
        args(match_id=bad)


def test_rejects_bad_seat():
    with pytest.raises(ValueError):
        args(seat=2)
