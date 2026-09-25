# Project intent

Give autonomous agents hardware-level display, keyboard, mouse, and ATX access
through named GL.iNet Comet KVM endpoints. Keep this integration thin.

- The consuming model owns perception, reasoning, planning, and task execution.
- MCP exposes primitive hardware capabilities and is useful without the skill.
- The shared skill supplies concise operational expertise, not API documentation.
- Keep one implementation and one canonical skill for both plugin ecosystems.
- Never model attached machines or add OCR, agent loops, or task-specific tools.
- Every hardware operation explicitly names its Comet; no mutable active target.
- Hide connection/authentication/streamer/HID mechanics inside the server.
- Prefer the smallest abstraction that faithfully exposes the hardware.
- Never replay uncertain input or power actions. Release input on failure.
- Keep secrets and local configuration out of the repository and tool output.
