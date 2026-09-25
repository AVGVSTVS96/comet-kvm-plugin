"""Comet protocol mechanics. One serialized session per configured endpoint."""

import asyncio
import json
from contextlib import asynccontextmanager, suppress

import aiohttp
import anyio

from . import CometError
from .capture import capture
from .config import Endpoint


class Comet:
    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint
        self.lock = asyncio.Lock()
        self.ping_lock = asyncio.Lock()
        self.http = None
        self.ws = None
        self.tasks = []
        self.pong = asyncio.Event()

    async def request(self, method, path, **kwargs):
        async with self.http.request(
            method, self.endpoint.url + path, allow_redirects=False, **kwargs
        ) as response:
            if response.status != 200:
                raise CometError(f"Comet returned HTTP {response.status} for {path}")
            body = await response.json()
            if body.get("ok") is not True:
                raise CometError(f"Comet did not accept {path}")
            return body["result"]

    async def connect(self):
        await self.close()
        self.http = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.endpoint.tls_context()),
            cookie_jar=aiohttp.DummyCookieJar(),
            timeout=aiohttp.ClientTimeout(total=60, connect=10),
        )
        try:
            result = await self.request(
                "POST",
                "/api/auth/login",
                data={
                    "user": self.endpoint.username,
                    "passwd": await self.endpoint.resolve_password(),
                },
            )
            token = result.get("token")
            if not isinstance(token, str) or not token:
                raise CometError(
                    "Login returned no session token; check credentials or two-factor authentication"
                )
            self.http.headers["Cookie"] = "auth_token=" + token
            self.ws = await self.http.ws_connect(
                self.endpoint.url + "/api/ws?stream=true",
                max_msg_size=16 * 1024 * 1024,
            )
            self.tasks = [
                asyncio.create_task(self.receive()),
                asyncio.create_task(self.keepalive()),
            ]
            await self.fence()
        except BaseException:
            await self.close()
            raise

    async def receive(self):
        try:
            async for message in self.ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    kind = json.loads(message.data).get("event_type")
                    if kind == "pong":
                        self.pong.set()
                    elif kind == "kickout":
                        break
                elif message.type == aiohttp.WSMsgType.ERROR:
                    break
        finally:
            await self.ws.close()

    async def keepalive(self):
        while not self.ws.closed:
            await asyncio.sleep(3)
            try:
                await self.fence()
            except (aiohttp.ClientError, TimeoutError):
                await self.ws.close()
                return

    async def send(self, kind, event):
        await self.ws.send_json({"event_type": kind, "event": event})

    async def fence(self):
        # The server handles this after preceding HID messages. It confirms
        # transport delivery, not the effect on the attached computer.
        # Serialize pings so an older keepalive pong cannot acknowledge input.
        async with self.ping_lock:
            self.pong.clear()
            await self.send("ping", {})
            await asyncio.wait_for(self.pong.wait(), timeout=5)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        if self.ws:
            await self.ws.close()
        if self.http:
            if "Cookie" in self.http.headers:
                with suppress(Exception):
                    await self.request(
                        "POST",
                        "/api/auth/logout",
                        timeout=aiohttp.ClientTimeout(total=3),
                    )
            await self.http.close()
        self.ws = self.http = None

    @asynccontextmanager
    async def operation(self, *, mutation=False):
        async with self.lock:
            try:
                if (
                    self.ws is None
                    or self.ws.closed
                    or any(task.done() for task in self.tasks)
                ):
                    await self.connect()
                else:
                    try:
                        await self.request("GET", "/api/auth/check")
                    except (CometError, aiohttp.ClientError, TimeoutError):
                        await self.connect()  # Before any input or power action.
                yield self
            except BaseException as error:
                with anyio.CancelScope(shield=True):
                    await self.close()
                if isinstance(error, asyncio.CancelledError):
                    raise
                detail = (
                    str(error)
                    if isinstance(error, CometError)
                    else type(error).__name__
                )
                suffix = (
                    " Action may have partially completed; observe before retrying."
                    if mutation
                    else ""
                )
                raise CometError(detail + suffix) from None

    async def screenshot(self, max_width):
        try:
            return await capture(self.http, self.endpoint.url, max_width)
        except TimeoutError:
            raise CometError(
                "No display frame arrived in time. Video may be changing modes; "
                "retry observation, then check power and HDMI signal."
            ) from None

    async def keys(self, keys, hold_ms):
        pressed = []
        try:
            for key in keys:
                pressed.append(key)  # Track before sending: failures can be ambiguous.
                await self.send("key", {"key": key, "state": True, "finish": False})
                await asyncio.sleep(0.005)
            await asyncio.sleep(hold_ms / 1000)
        finally:
            with anyio.CancelScope(shield=True):
                async with asyncio.timeout(3):
                    for key in reversed(pressed):
                        await self.send(
                            "key", {"key": key, "state": False, "finish": True}
                        )
                        await asyncio.sleep(0.005)
        await self.fence()

    async def move(self, x, y, mode):
        state = await self.request("GET", "/api/hid")
        output = "usb" if mode == "absolute" else "usb_rel"
        mouse = state.get("mouse", {})
        if mouse.get("outputs", {}).get("active") != output:
            if output not in mouse.get("outputs", {}).get("available", []):
                raise CometError("Requested mouse mode is not supported by this Comet")
            await self.request(
                "POST", "/api/hid/set_params", params={"mouse_output": output}
            )
            for _ in range(20):
                await asyncio.sleep(0.1)
                state = await self.request("GET", "/api/hid")
                if state.get("mouse", {}).get("outputs", {}).get("active") == output:
                    break
            else:
                raise CometError("Mouse mode did not become ready")
        if mode == "absolute":
            await self.send(
                "mouse_move",
                {
                    "to": {
                        "x": round(x * 65535 - 32768),
                        "y": round(y * 65535 - 32768),
                    }
                },
            )
        else:
            await self.send(
                "mouse_relative", {"delta": {"x": int(x), "y": int(y)}, "squash": False}
            )
        await self.fence()

    async def click(self, button, count):
        for _ in range(count):
            try:
                await self.send("mouse_button", {"button": button, "state": True})
                await asyncio.sleep(0.04)
            finally:
                with anyio.CancelScope(shield=True):
                    async with asyncio.timeout(3):
                        await self.send(
                            "mouse_button", {"button": button, "state": False}
                        )
            await asyncio.sleep(0.05)
        await self.fence()
