"""One agent at a time on a Comet's keyboard, mouse, and power buttons."""

import asyncio
import fcntl
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from time import time
from urllib.parse import urlsplit

from . import CometError

# Longer than an agent takes to observe the screen and decide its next input.
QUIET = 60


def agent():
    return (
        os.environ.get("COMET_KVM_AGENT")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or f"process session {os.getsid(0)}"
    )


def record(url):
    state = Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()
    (state / "comet-kvm").mkdir(parents=True, exist_ok=True)
    return state / "comet-kvm" / urlsplit(url).netloc.replace(":", "_")


@asynccontextmanager
async def turn(url):
    with await asyncio.to_thread(open, record(url), "a+") as file:
        # Held for the whole input, so another process's keys can't land between these.
        await asyncio.to_thread(fcntl.flock, file, fcntl.LOCK_EX)
        file.seek(0)
        last = json.loads(file.read() or "{}")
        me = agent()
        ago = round(time() - last.get("at", 0))
        if last.get("agent", me) != me and ago < QUIET:
            raise CometError(
                f"Another agent ({last['agent']}) used this Comet's keyboard, mouse, or "
                f"power {ago}s ago, and input from two agents mixes on the attached "
                f"computer. No input sent: observe the screen, and act once it has been "
                f"quiet for {QUIET}s or you have agreed who drives."
            )
        try:
            yield
        finally:
            file.seek(0)
            file.truncate()
            json.dump({"agent": me, "at": time()}, file)
