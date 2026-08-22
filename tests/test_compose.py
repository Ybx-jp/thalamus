"""
The compose file against the code that dials what it brings up.

Interfaces: docker-compose.yml, config/gremlin-server.yaml, and
substrate.writer.DEFAULT_URL.
Infrastructure: YAML parsing only — no Docker, no daemon, no pull. The live check
is `thalamus init --check`, which probes the running graph; this is the static half,
and it is the half that can run anywhere.
Scope: the port and the config path, which are each spelled independently in four
places and reconciled nowhere. `docker compose up -d` is the second command in the
documented sequence and the first that a first-time user cannot debug: a port
changed on one side reaches them as a connection error at step four, pointing at the
step that already succeeded.
"""

import re
from pathlib import Path

import pytest
import yaml

from thalamus.substrate import writer

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def graph_service() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]["graph"]


def _published(service: dict) -> tuple[str, int, int]:
    """The one published port, as (host, host_port, container_port).

    Long-form and short-form entries are both legal compose; only the short form
    is written here, and a rewrite into the long form should fail loudly rather
    than be quietly parsed into a different claim.
    """
    ports = service["ports"]
    assert len(ports) == 1, f"expected exactly one published port, got {ports}"
    match = re.fullmatch(r"([\d.]+):(\d+):(\d+)", str(ports[0]))
    assert match, f"published port is not host:hostport:containerport — {ports[0]!r}"
    return match.group(1), int(match.group(2)), int(match.group(3))


def test_the_published_port_is_the_one_the_writer_dials(graph_service):
    """The reconciliation nothing else performs.

    `DEFAULT_URL` is what every surface falls back to — the MCP registration, the
    CLI's `--url` default, `thalamus init --check`'s probe — so a port changed in
    the compose file and not here brings up a graph that nothing in the project
    talks to, and the failure surfaces one step later as "nothing listening".
    """
    _, host_port, container_port = _published(graph_service)
    _, dialled = writer.split_ws(writer.DEFAULT_URL)

    assert host_port == dialled
    assert container_port == dialled


def test_the_graph_is_published_on_loopback_only(graph_service):
    """A bare `8182:8182` publishes on every interface.

    Gremlin Server here runs with no authentication, so the bind address is the
    whole of the access control: anything that can reach the port can read and
    rewrite the operator's memory.
    """
    host, _, _ = _published(graph_service)

    assert host == "127.0.0.1"


def test_the_healthcheck_probes_the_port_the_server_binds(graph_service):
    """A healthcheck on the wrong port reports a container that never came up as up."""
    _, _, container_port = _published(graph_service)
    probe = " ".join(graph_service["healthcheck"]["test"])

    assert str(container_port) in probe


def test_the_served_config_declares_the_same_port(graph_service):
    """The container listens on what its own YAML says, not on what compose maps.

    The entrypoint is bypassed on purpose (the image's script rewrites this file,
    which is mounted read-only), so nothing in the image reconciles the two either.
    """
    _, _, container_port = _published(graph_service)
    mount = next(v for v in graph_service["volumes"] if v.startswith("./config:"))
    mounted_at = mount.split(":")[1]
    served = graph_service["command"][0]

    assert served.endswith(".yaml")
    on_disk = REPO_ROOT / "config" / Path(served).name
    assert on_disk.is_file(), f"compose serves {served}, which is not in config/"
    assert mounted_at.rstrip("/").endswith(Path(served).parent.name), (
        f"compose serves {served}, but ./config is mounted at {mounted_at}")
    assert yaml.safe_load(on_disk.read_text())["port"] == container_port


def test_the_image_is_pinned_to_a_tag(graph_service):
    """`latest` would make the graph a moving target across boxes and across time."""
    image = graph_service["image"]

    assert ":" in image, f"image is untagged: {image}"
    assert not image.endswith(":latest")


@pytest.mark.parametrize("doc", ["README.md", "docs/getting-started.md"])
def test_the_documented_address_matches_the_published_one(graph_service, doc):
    """The address a reader types is part of the contract, not commentary."""
    host, host_port, _ = _published(graph_service)
    text = (REPO_ROOT / doc).read_text()

    assert f"{host}:{host_port}" in text, f"{doc} does not name {host}:{host_port}"
