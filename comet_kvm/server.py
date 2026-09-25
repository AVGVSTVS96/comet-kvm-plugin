"""Primitive hardware tools, shared by Codex and Claude Code."""

import argparse
import asyncio
import re
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations
from pydantic import Field

from . import CometError
from .client import Comet
from .config import load_config

READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
)

SPECIAL_KEYS = {
    "Enter",
    "Escape",
    "Backspace",
    "Tab",
    "Space",
    "Minus",
    "Equal",
    "BracketLeft",
    "BracketRight",
    "Backslash",
    "Semicolon",
    "Quote",
    "Backquote",
    "Comma",
    "Period",
    "Slash",
    "CapsLock",
    "PrintScreen",
    "ScrollLock",
    "Pause",
    "Insert",
    "Home",
    "PageUp",
    "Delete",
    "End",
    "PageDown",
    "NumLock",
    "ContextMenu",
    "NumpadDivide",
    "NumpadMultiply",
    "NumpadSubtract",
    "NumpadAdd",
    "NumpadEnter",
    "NumpadDecimal",
}
MODIFIERS = {
    side + hand
    for side in ("Control", "Shift", "Alt", "Meta")
    for hand in ("Left", "Right")
}


def build_server(config):
    clients = {name: Comet(endpoint) for name, endpoint in config.comets.items()}

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            await asyncio.gather(*(client.close() for client in clients.values()))

    mcp = FastMCP(
        "comet-kvm",
        lifespan=lifespan,
        instructions=(
            "GL.iNet Comet is a physical HDMI/USB KVM: observe a computer's display and send "
            "keyboard/mouse input even in BIOS, boot menus, installers, or a failed OS. "
            "An attached ATX accessory operates its physical power/reset buttons. "
            "List configured Comets; explicitly name the intended Comet in every operation. "
            "Observe screenshots directly, act in small steps, then observe again. "
            "Input reaches the focused remote application; successful delivery is not proof of its effect. "
            "Connection/authentication/video startup and input release are automatic. "
            "An uncertain action is never automatically replayed. Power/reset may lose unsaved data."
        ),
    )

    def target(comet):
        if comet not in clients:
            raise ValueError("Unknown Comet; use list_comets for configured names")
        return clients[comet]

    @mcp.tool(annotations=READ)
    def list_comets() -> list[str]:
        """List configured Comet names without connecting or exposing credentials."""
        return list(clients)

    @mcp.tool(annotations=READ)
    async def screenshot(
        comet: str, max_width: Annotated[int, Field(ge=320, le=3840)] = 1600
    ) -> Image:
        """Observe the HDMI display as a JPEG. Resize preserves aspect ratio; 3840 is useful for small text.
        A blank/no-signal picture does not establish whether the computer is powered off.
        """
        async with target(comet).operation() as client:
            return Image(data=await client.screenshot(max_width), format="jpeg")

    @mcp.tool(annotations=WRITE)
    async def type_text(
        comet: str, text: Annotated[str, Field(min_length=1, max_length=1024)]
    ) -> str:
        """Type text via USB keyboard using the US layout; remote layout must match.
        Accepts printable ASCII, tab, and newline (which presses Enter). Does not append Enter.
        Unsupported characters are rejected before any input. This is typing, not clipboard paste.
        """
        if any(not (32 <= ord(c) <= 126 or c in "\t\n") for c in text):
            raise ValueError(
                "Only printable ASCII, tab, and newline are supported; no input sent"
            )
        async with target(comet).operation(mutation=True) as client:
            await client.request(
                "POST",
                "/api/hid/print",
                params={
                    "limit": "0",
                    "keymap": "en-us",
                    "slow": "true",
                },
                data=text.encode(),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        return "Text sent once; observe the remote result."

    @mcp.tool(annotations=WRITE)
    async def press_keys(
        comet: str,
        keys: Annotated[list[str], Field(min_length=1, max_length=6)],
        hold_ms: Annotated[int, Field(ge=25, le=2000)] = 50,
    ) -> str:
        """Press and release one key or chord, modifiers first, e.g. [\"ControlLeft\", \"KeyC\"].
        Uses DOM codes: KeyA..KeyZ, Digit0..Digit9, F1..F12, ArrowUp/Down/Left/Right,
        Enter, Escape, Delete, Tab, Space, navigation/punctuation/numpad keys, and
        Control/Shift/Alt/Meta followed by Left or Right. A hold can cause OS auto-repeat.
        All keys are released before return, including after interrupted input.
        """
        if len(set(keys)) != len(keys) or any(
            key not in SPECIAL_KEYS | MODIFIERS
            and not re.fullmatch(
                r"Key[A-Z]|Digit[0-9]|Numpad[0-9]|F(?:[1-9]|1[0-2])|Arrow(?:Up|Down|Left|Right)",
                key,
            )
            for key in keys
        ):
            raise ValueError("Invalid or duplicate DOM key code; no input sent")
        if any(key not in MODIFIERS for key in keys[:-1]):
            raise ValueError("A chord contains modifiers followed by one key")
        async with target(comet).operation(mutation=True) as client:
            await client.keys(keys, hold_ms)
        return "Keys sent and released; observe the remote result."

    @mcp.tool(annotations=WRITE)
    async def move_mouse(
        comet: str,
        x: float,
        y: float,
        mode: Literal["absolute", "relative"] = "absolute",
    ) -> str:
        """Move without clicking. Absolute: x,y in [0,1], (0,0) top-left, (1,1) bottom-right.
        Relative: integer USB deltas [-127,127], positive right/down; OS acceleration applies.
        Selects the matching Comet mouse output automatically; relative helps older BIOSes.
        """
        if mode == "absolute" and not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Absolute coordinates must be between 0 and 1")
        if mode == "relative" and not all(
            -127 <= n <= 127 and n == int(n) for n in (x, y)
        ):
            raise ValueError("Relative deltas must be integers between -127 and 127")
        async with target(comet).operation(mutation=True) as client:
            await client.move(x, y, mode)
        return "Mouse movement sent."

    @mcp.tool(annotations=WRITE)
    async def click_mouse(
        comet: str,
        button: Literal["left", "middle", "right"] = "left",
        count: Annotated[int, Field(ge=1, le=2)] = 1,
    ) -> str:
        """Click at the current remote pointer location; count=2 double-clicks. Always releases the button."""
        async with target(comet).operation(mutation=True) as client:
            await client.click(button, count)
        return "Mouse click sent and released."

    @mcp.tool(annotations=WRITE)
    async def scroll(
        comet: str,
        dx: Annotated[int, Field(ge=-127, le=127)] = 0,
        dy: Annotated[int, Field(ge=-127, le=127)] = 0,
    ) -> str:
        """Send USB wheel steps: positive dy is wheel-up, positive dx wheel-right.
        Remote OS natural-scrolling preferences determine actual content movement.
        """
        async with target(comet).operation(mutation=True) as client:
            await client.send(
                "mouse_wheel", {"delta": {"x": dx, "y": dy}, "squash": False}
            )
            await client.fence()
        return "Scroll sent."

    @mcp.tool(annotations=READ)
    async def power_state(comet: str) -> dict:
        """Read ATX availability, busy state, and motherboard power LED. Requires a wired ATX accessory.
        These signals do not establish OS health or successful boot.
        """
        async with target(comet).operation() as client:
            return await client.request("GET", "/api/atx")

    @mcp.tool(annotations=WRITE)
    async def press_atx(
        comet: str, button: Literal["power", "power_long", "reset"]
    ) -> str:
        """Operate a physical ATX button once. power: short press (power-on or OS-configured action).
        power_long: forced power-off. reset: hardware reset. The latter two can lose data.
        Read power_state first. Returns acknowledgement, not completed shutdown/boot; observe afterward.
        """
        async with target(comet).operation(mutation=True) as client:
            state = await client.request("GET", "/api/atx")
            if state.get("enabled") and not state.get("busy"):
                await client.request(
                    "POST", "/api/atx/click", params={"button": button}
                )
                return "ATX button acknowledged once; observe power state and display."
        # Raised outside the operation so it isn't reported as a possible partial action.
        raise CometError("ATX unavailable or busy; no button pressed")

    return mcp


def main():
    parser = argparse.ArgumentParser(description="Comet KVM MCP server (stdio)")
    parser.add_argument(
        "--config",
        help="JSON configuration; defaults to COMET_KVM_CONFIG or ~/.config/comet-kvm/config.json",
    )
    args = parser.parse_args()
    build_server(load_config(args.config)).run()


if __name__ == "__main__":
    main()
