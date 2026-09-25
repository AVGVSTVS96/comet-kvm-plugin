# comet-kvm

Give coding agents eyes and hands on a physical computer. **comet-kvm** exposes a
[GL.iNet Comet](https://docs.gl-inet.com/kvm/en/) KVM's HDMI capture, USB
keyboard and mouse, and ATX power buttons as MCP tools, packaged as one plugin for
Claude Code and Codex.

SSH and computer-use need a working OS. A KVM doesn't: it sees the display and
types as a USB keyboard through BIOS/UEFI, boot menus, installers, disk unlock
screens, and crashed systems. comet-kvm keeps the integration thin. The model does
the perceiving and planning, while the server exposes only hardware primitives and
hides the Comet's session, streamer, and HID mechanics.

## Features

- 🖥️ **Display** -- fresh JPEG screenshots at any width, even when firmware mislabels H.264 as JPEG
- ⌨️ **Keyboard** -- US-layout typing plus key chords, always released, even on cancellation
- 🖱️ **Mouse** -- absolute or relative movement, clicks, and scrolling, switching USB mouse mode automatically
- 🔌 **Power** -- ATX power, long-power, and reset buttons with raw power and LED state
- 🎯 **Explicit targets** -- every call names its Comet, with no mutable "active device"
- 🛑 **No replays** -- uncertain input and power actions are reported, never retried
- 🔐 **Credentials stay local** -- passwords come from config or a helper like Keychain, never from tool output

## Requirements

- A GL.iNet Comet reachable over HTTP(S). ATX tools need the wired ATX accessory.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). It provisions Python 3.11+ and the locked dependencies on first launch.

## Install

**Claude Code**

```bash
claude plugin marketplace add AVGVSTVS96/comet-kvm
claude plugin install comet-kvm@comet-kvm
```

**Codex**

```bash
codex plugin marketplace add AVGVSTVS96/comet-kvm
codex plugin add comet-kvm@comet-kvm
```

**Any other MCP client** can run the stdio server from a clone:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/absolute/path/to/comet-kvm", "--locked", "comet-kvm"]
}
```

## Configure

Copy [`config.example.json`](config.example.json) to `~/.config/comet-kvm/config.json`
and name each Comet:

```json
{
  "comets": {
    "server": {
      "url": "https://glkvm.local",
      "password_command": ["security", "find-generic-password", "-s", "comet-kvm", "-a", "admin", "-w"],
      "ca_file": "~/.config/comet-kvm/comet-ca.crt"
    }
  }
}
```

| field | |
| --- | --- |
| `url` | HTTP(S) origin of the Comet |
| `username` | defaults to `admin` |
| `password` | the device password, **or** |
| `password_command` | argv for a credential helper, run without a shell; stdout is the password |
| `ca_file` | extra CA for the Comet's certificate; HTTPS is always verified |

`COMET_KVM_CONFIG` or `--config` selects another file. Restrict its permissions if it
holds a password. Changes apply when the MCP server restarts.

## Tools

| tool | |
| --- | --- |
| `list_comets` | configured names, no network access |
| `screenshot` | fresh display image, optionally resized |
| `type_text` | US-layout ASCII text, tab, and newline |
| `press_keys` | one key or modifier chord, with bounded hold |
| `move_mouse` | normalized absolute position or relative USB deltas |
| `click_mouse` | left, middle, or right click, or double-click |
| `scroll` | horizontal and vertical wheel steps |
| `power_state` | raw ATX availability, busy state, power, and LEDs |
| `press_atx` | short power, long power, or reset |

The bundled skill teaches agents the operating habits: observe, act in small steps,
observe again, and treat the screen as the only evidence of an input's effect.

## How it works

Each Comet gets one lazily authenticated, serialized session, so different Comets
operate concurrently. Before every operation the session is checked and, if needed,
re-established, so a dropped connection never swallows the next input.

Screenshots use the snapshot endpoint when it returns real JPEG bytes. Some firmware
returns H.264 under a JPEG content type, and then the server decodes a fresh frame
from the direct video stream with PyAV. No ffmpeg install is needed.

Input and power are never replayed. A failed request may already have reached the
computer, so the error says so and the agent observes before deciding. Held keys and
buttons are released on every exit path. After a lost network connection, release
waits until the Comet's firmware detects the disconnect.

## Development

```bash
git clone https://github.com/AVGVSTVS96/comet-kvm && cd comet-kvm
uv sync --group dev
uv run --group dev pytest   # tools against a loopback fake Comet
uv run --group dev ruff check
claude --plugin-dir .       # or link the repo into ~/.claude/skills/comet-kvm
```

[AGENTS.md](AGENTS.md) records the project's boundaries, and
[verification.md](verification.md) records the live hardware evidence and known limits.

Protocol research drew on
[MooseGooseConsulting's integration](https://github.com/MooseGooseConsulting/comet-kvm-codex-plugin/tree/ac8e4dd99c74c678bb99e2330d7f4ab2e37541d9),
[GL.iNet's firmware source](https://github.com/gl-inet/glkvm/tree/3e8dd23c4bd638a4650433664cc3b0f3b4d29395),
and the [PiKVM API reference](https://docs.pikvm.org/api/). This is an independent,
smaller implementation, not a fork.

## License

[MIT](LICENSE)
