"""Decode a display image; no OCR or visual interpretation."""

import asyncio
import io
import json
from time import monotonic

import aiohttp
import av
from PIL import Image

from . import CometError


def jpeg(image, max_width):
    if image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)))
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()


async def capture(http, url, max_width):
    # Some Comet firmware returns H.264 bytes with an image/jpeg content type.
    # Inspect bytes, then use the same direct video endpoint as the web console.
    for delay in (0, 0.15, 0.3, 0.6, 1.2):
        await asyncio.sleep(delay)
        async with http.get(
            url + "/api/streamer/snapshot",
            params={
                "allow_offline": "true",
            },
            allow_redirects=False,
        ) as response:
            if response.status == 503:
                continue
            if response.status != 200:
                raise CometError(f"Screenshot returned HTTP {response.status}")
            data = await response.read()
            if data.startswith(b"\xff\xd8\xff"):
                with Image.open(io.BytesIO(data)) as image:
                    return jpeg(image, max_width)
            break

    async with asyncio.timeout(12):
        async with http.ws_connect(
            url + "/api/media/ws", max_msg_size=16 * 1024 * 1024
        ) as ws:
            decoder = None
            started = False
            first_frame_at = None
            last_ping = 0.0
            while True:
                if monotonic() - last_ping >= 1:
                    await ws.send_bytes(b"\x00")
                    last_ping = monotonic()
                message = await ws.receive(timeout=5)
                if message.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(message.data)
                    if event.get("event_type") == "media":
                        formats = event["event"]["video"]
                        fmt = next(
                            (f for f in ("h264", "h265", "jpeg") if f in formats), None
                        )
                        if fmt is None:
                            raise CometError("No supported Comet video format")
                        decoder = av.CodecContext.create(
                            {"h265": "hevc", "jpeg": "mjpeg"}.get(fmt, fmt), "r"
                        )
                        await ws.send_json(
                            {
                                "event_type": "start",
                                "event": {"type": "video", "format": fmt},
                            }
                        )
                elif message.type == aiohttp.WSMsgType.BINARY:
                    data = message.data
                    if len(data) < 3 or data[0] != 1 or decoder is None:
                        continue
                    started = started or bool(data[1])
                    if started:
                        frames = decoder.decode(av.Packet(data[2:]))
                        if frames:
                            # The first keyframe may predate this connection.
                            first_frame_at = first_frame_at or monotonic()
                            if monotonic() - first_frame_at >= 0.25:
                                return jpeg(frames[-1].to_image(), max_width)
                elif message.type in {
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.ERROR,
                }:
                    raise CometError(
                        "Comet video connection closed before a frame arrived"
                    )
