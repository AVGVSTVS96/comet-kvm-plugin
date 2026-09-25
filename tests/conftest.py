"""A loopback Comet that records what the real client sends."""

import asyncio
import io
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from PIL import Image

from comet_kvm.config import Configuration
from comet_kvm.server import build_server


def ok(result=None):
    return web.json_response({"ok": True, "result": result or {}})


class FakeComet:
    def __init__(self):
        self.logins = 0
        self.tokens = set()
        self.events = []
        self.atx = {"enabled": True, "busy": False, "leds": {"power": False}}
        self.atx_posts = 0
        self.drop_atx = False
        self.mouse_output = "usb"
        self.frame = io.BytesIO()
        Image.new("RGB", (800, 400), "navy").save(self.frame, format="JPEG")

    def authorized(self, request):
        return request.cookies.get("auth_token") in self.tokens

    def app(self):
        app = web.Application()
        app.router.add_post("/api/auth/login", self.login)
        app.router.add_get("/api/auth/check", self.check)
        app.router.add_post("/api/auth/logout", self.check)
        app.router.add_get("/api/ws", self.ws)
        app.router.add_get("/api/streamer/snapshot", self.snapshot)
        app.router.add_get("/api/atx", self.atx_state)
        app.router.add_post("/api/atx/click", self.atx_click)
        app.router.add_get("/api/hid", self.hid)
        app.router.add_post("/api/hid/set_params", self.set_params)
        app.router.add_post("/api/hid/print", self.print)
        return app

    async def login(self, request):
        self.logins += 1
        form = await request.post()
        if form["passwd"] != "secret":
            return web.json_response({"ok": False, "result": {}}, status=403)
        token = f"token-{self.logins}"
        self.tokens.add(token)
        return ok({"token": token})

    async def check(self, request):
        return ok() if self.authorized(request) else web.Response(status=401)

    async def ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            event = json.loads(message.data)
            if event["event_type"] == "ping":
                await ws.send_json({"event_type": "pong", "event": {}})
            else:
                self.events.append((event["event_type"], event["event"]))
        return ws

    async def snapshot(self, request):
        return web.Response(body=self.frame.getvalue(), content_type="image/jpeg")

    async def atx_state(self, request):
        return ok(self.atx)

    async def atx_click(self, request):
        self.atx_posts += 1
        if self.drop_atx:
            request.transport.close()
            await asyncio.sleep(1)
        return ok()

    async def hid(self, request):
        return ok(
            {
                "mouse": {
                    "outputs": {
                        "available": ["usb", "usb_rel"],
                        "active": self.mouse_output,
                    }
                }
            }
        )

    async def set_params(self, request):
        self.mouse_output = request.query["mouse_output"]
        return ok()

    async def print(self, request):
        self.events.append(("print", await request.text()))
        return ok()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def comet():
    fake = FakeComet()
    server = TestServer(fake.app(), host="127.0.0.1")
    await server.start_server()
    config = Configuration.model_validate(
        {"comets": {"lab": {"url": str(server.make_url("/")), "password": "secret"}}}
    )
    fake.mcp = build_server(config)
    async with fake.mcp.settings.lifespan(fake.mcp):  # Closes sessions like shutdown.
        yield fake
    await server.close()
