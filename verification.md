# Verification: September 17, 2026

Live device: GL.iNet Comet Pro RM10, **V1.7.2 release1**. Tests used the real
stdio MCP transport, verified HTTPS, and a password obtained from macOS Keychain.
No credentials or attached-machine identity are bundled in this repository.

## Live results

| Capability | Evidence |
| --- | --- |
| MCP discovery | Initialization, server instructions, and all nine tool schemas returned successfully |
| Authentication | Login, session reuse, logout, and reconnect worked against the real endpoint |
| Display | Captured disk-unlock and desktop screens at 1600 and 2560 pixels wide |
| Capture recovery | Snapshot returned H.264 mislabeled as JPEG; preview returned HTTP 500. Direct-video decoding produced valid JPEG images |
| Text | A harmless character appeared in the unlock field; later a mixed-case/punctuation command ran in a terminal |
| Keys | Backspace removed the test character; a modifier chord opened the terminal |
| Secret entry | A saved credential was passed privately through type_text; the target reached its desktop |
| Absolute mouse | Pointer position followed normalized coordinates |
| Relative mouse | Switched output to usb_rel; observed pointer displacement; restored absolute mode afterward |
| Click | Double-click visibly selected terminal text |
| Scroll | Wheel input moved terminal scrollback to the earlier command and output |
| ATX | Short power acknowledged, boot observed; reset acknowledged, subsequent unlock screen observed; long power acknowledged, power state changed to off |
| Boot transition | One capture timed out during reboot; subsequent observation recovered without replaying input |

The target was returned to its initial powered-off state. No firmware settings,
firmware version, attached-machine configuration, or files were changed for the
integration. Live checks ran a temporary terminal command and rebooted the host.

## Local fault checks

`uv run --group dev pytest` drives the real tools against a loopback fake Comet:

- JPEG decode and aspect-preserving resize.
- Modifier/key press and reverse release order, including finish=true.
- Cancellation during a held chord releases the main key and modifier.
- Expired authentication is re-established before the next input.
- Relative movement switches the mouse output before sending deltas.
- A dropped ATX response produces an uncertain-action error and exactly one POST.
- A busy ATX presses nothing and is not reported as a partial action.
- Unsupported text, invalid key codes/coordinates, and unknown targets are rejected
  before any connection or input.
- Configuration errors name the field without echoing its value.

Ruff lint and Python compilation passed. Codex's plugin validator, Claude Code's
native plugin validator, the skill validator, and both portable JSON schemas
passed. Codex's app server recognized the installed plugin, shared skill, and
MCP server. The production launch command was exercised from an unrelated cwd.

Claude Code was subsequently registered persistently through
`~/.claude/skills/comet-kvm`, pointing to the shared repository. Its native CLI
listed `comet-kvm@skills-dir` as enabled in user scope, discovered the shared
skill and MCP server, and reported the MCP server connected from `/tmp` without
passing `--plugin-dir`.

## Limits

- Only one physical Comet was available; multi-device isolation was checked with
  simulated endpoints, not two physical units.
- BIOS setup entry was not confirmed. Input at the pre-OS disk-unlock screen
  was confirmed; firmware-specific USB enumeration remains a hardware concern.
- No qualification on newer Comet firmware, other models, H.265 mode, non-US
  layouts, or Windows/Linux client hosts is claimed.
- Native manifests were validated for both clients. No second autonomous model
  session was launched to qualify skill selection or end-to-end agent behavior.
- Real network loss cannot guarantee immediate USB release; cleanup is attempted
  and the Comet clears input when it detects WebSocket disconnect.
