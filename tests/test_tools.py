import asyncio
import base64
import io
import json
import os
import sys

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from PIL import Image

from comet_kvm import turn
from comet_kvm.config import load_config

pytestmark = pytest.mark.anyio


async def call(fake, tool, **arguments):
    return await fake.mcp.call_tool(tool, {"comet": "lab", **arguments})


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("type_text", {"text": "café"}),
        ("press_keys", {"keys": ["KeyA", "ControlLeft"]}),
        ("press_keys", {"keys": ["KeyA", "KeyA"]}),
        ("press_keys", {"keys": ["Hyper"]}),
        ("move_mouse", {"x": 1.5, "y": 0.5}),
        ("move_mouse", {"x": 0.5, "y": 3, "mode": "relative"}),
        ("screenshot", {"comet": "missing"}),
    ],
)
async def test_invalid_requests_never_connect(comet, tool, arguments):
    with pytest.raises(ToolError):
        await call(comet, tool, **arguments)
    assert comet.logins == 0


async def test_screenshot_resizes_preserving_aspect(comet):
    [content] = await call(comet, "screenshot", max_width=400)
    with Image.open(io.BytesIO(base64.b64decode(content.data))) as image:
        assert (image.format, image.size) == ("JPEG", (400, 200))


async def test_chord_presses_in_order_and_releases_in_reverse(comet):
    await call(comet, "press_keys", keys=["ControlLeft", "ShiftLeft", "KeyT"])
    keys = [
        (e["key"], e["state"], e["finish"]) for kind, e in comet.events if kind == "key"
    ]
    assert keys == [
        ("ControlLeft", True, False),
        ("ShiftLeft", True, False),
        ("KeyT", True, False),
        ("KeyT", False, True),
        ("ShiftLeft", False, True),
        ("ControlLeft", False, True),
    ]


async def test_cancelled_hold_releases_every_key(comet):
    task = asyncio.create_task(
        call(comet, "press_keys", keys=["AltLeft", "F4"], hold_ms=2000)
    )
    while len(comet.events) < 2:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.1)
    assert [(e["key"], e["state"]) for _, e in comet.events[2:]] == [
        ("F4", False),
        ("AltLeft", False),
    ]


async def test_expired_session_reauthenticates_before_input(comet):
    await call(comet, "type_text", text="one\n")
    comet.tokens.clear()
    await call(comet, "type_text", text="two")
    assert comet.logins == 2
    assert [e for kind, e in comet.events if kind == "print"] == ["one\n", "two"]


async def test_relative_mouse_switches_output_first(comet):
    await call(comet, "move_mouse", x=-5, y=7, mode="relative")
    assert comet.mouse_output == "usb_rel"
    assert comet.events == [
        ("mouse_relative", {"delta": {"x": -5, "y": 7}, "squash": False})
    ]


async def test_lost_atx_acknowledgement_is_never_replayed(comet):
    comet.drop_atx = True
    with pytest.raises(ToolError, match="observe before retrying"):
        await call(comet, "press_atx", button="power")
    assert comet.atx_posts == 1


async def test_busy_atx_presses_nothing(comet):
    comet.atx["busy"] = True
    with pytest.raises(ToolError) as error:
        await call(comet, "press_atx", button="reset")
    assert "no button pressed" in str(error.value)
    assert "partially" not in str(error.value)
    assert comet.atx_posts == 0


def test_config_errors_name_fields_without_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"comets": {"lab": {"url": "ftp://kvm", "password": "hunter2", "extra": 1}}}
        )
    )
    with pytest.raises(RuntimeError) as error:
        load_config(str(path))
    message = str(error.value)
    assert "comets.lab" in message and "extra" in message
    assert "hunter2" not in message and "ftp" not in message


async def run(comet, tmp_path, agent, *arguments, stdin=None):
    """One agent's process, as each agent's MCP server or `call` is."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps(comet.config))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from comet_kvm.server import main; main()",
        *arguments,
        env=os.environ | {"COMET_KVM_CONFIG": str(config), "COMET_KVM_AGENT": agent},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, error = await process.communicate(stdin)
    return process.returncode, out.decode() + error.decode()


TYPE = """
import asyncio, sys
from comet_kvm.config import load_config
from comet_kvm.server import build_server

async def main():
    mcp = build_server(load_config())
    async with mcp.settings.lifespan(mcp):
        await mcp.call_tool("type_text", {"comet": "lab", "text": sys.argv[1]})

asyncio.run(main())
"""


async def test_two_agents_typing_at_once_never_mix_keys(comet, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(comet.config))

    async def types(agent, text):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            TYPE,
            text,
            env=os.environ
            | {"COMET_KVM_CONFIG": str(config), "COMET_KVM_AGENT": agent},
            stderr=asyncio.subprocess.PIPE,
        )
        return (await process.communicate())[1].decode()

    first, second = "a" * 40, "b" * 40
    errors = await asyncio.gather(types("one", first), types("two", second))
    assert comet.received in (first, second)
    [refused] = filter(None, errors)
    assert "Another agent" in refused and "No input sent" in refused
    assert "partially" not in refused


async def test_another_agent_waits_for_quiet_while_the_same_one_continues(
    comet, monkeypatch
):
    await call(comet, "type_text", text="one")
    await call(comet, "press_keys", keys=["Enter"])
    monkeypatch.setenv("COMET_KVM_AGENT", "other")
    with pytest.raises(ToolError, match=r"Another agent \(tester\)"):
        await call(comet, "press_atx", button="power")
    [content] = await call(comet, "screenshot")
    assert content.type == "image"
    monkeypatch.setattr(turn, "QUIET", 0)
    await call(comet, "type_text", text="two")
    assert comet.received == "onetwo" and comet.atx_posts == 0


async def test_call_types_a_piped_secret_without_enter(comet, tmp_path):
    code, out = await run(
        comet,
        tmp_path,
        "cli",
        "call",
        "type_text",
        '{"comet": "lab"}',
        "--stdin",
        "text",
        stdin=b"hunter2\n",
    )
    assert (code, comet.received) == (0, "hunter2")
    assert "hunter2" not in out


async def test_call_writes_a_screenshot_and_reports_a_refusal(comet, tmp_path):
    shot = tmp_path / "shot.jpg"
    code, out = await run(
        comet,
        tmp_path,
        "cli",
        "call",
        "screenshot",
        '{"comet": "lab"}',
        "--out",
        str(shot),
    )
    with Image.open(shot) as image:
        assert (code, image.format) == (0, "JPEG")
    await call(comet, "type_text", text="mine")
    code, out = await run(
        comet,
        tmp_path,
        "cli",
        "call",
        "press_keys",
        '{"comet": "lab", "keys": ["Enter"]}',
    )
    assert code == 1 and "Another agent (tester)" in out
    assert [kind for kind, _ in comet.events] == ["print"]


async def test_address_reaches_a_comet_its_url_name_does_not_resolve_to(
    comet, tmp_path
):
    lab = comet.config["comets"]["lab"]
    lab["address"], lab["url"] = (
        "127.0.0.1",
        lab["url"].replace("127.0.0.1", "comet.invalid"),
    )
    code, out = await run(
        comet, tmp_path, "cli", "call", "power_state", '{"comet": "lab"}'
    )
    assert code == 0 and json.loads(out) == comet.atx
