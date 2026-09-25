# When observation or input fails

**Video:** Distinguish no HDMI signal from a failed capture transport. The server
keeps a streaming session open and decodes direct video when the snapshot
endpoint returns mislabeled H.264. This was reproduced on an RM10 running
V1.7.2 release1. A decoder is only image acquisition, not a vision model.
Do not change EDID, reboot the appliance, or update firmware as the first response
to a capture error. A laptop may show firmware only on its internal display.

**Input:** Confirm the USB cable carries data and reaches the controlled host.
Firmware menus may accept relative mouse input but ignore absolute input. USB
enumeration may differ before and after the OS boots. GL.iNet documents virtual
media and USB identity as compatibility factors; changing either affects the
attached machine and should follow an observed compatibility problem. Browser
focus problems do not apply to this MCP's direct HID transport.

**Status:** On the tested RM10, keyboard.online was false despite working input.
ATX power reported on while leds.power remained false. Use actual observations
and avoid converting contradictory telemetry into confident OS-state claims.

**ATX:** It requires the accessory and correct motherboard wiring. The tested
V1.7.2 firmware rejects wait=true; the server omits it. Observe completion
separately. Busy responses and lost acknowledgements do not justify repetition.

Sources, checked September 2026:

- [GL.iNet mouse modes](https://docs.gl-inet.com/kvm/en/faq/difference_between_absolute_and_relative_mouse/)
- [GL.iNet input troubleshooting](https://docs.gl-inet.com/kvm/en/faq/cannot_control_the_mouse/)
- [GL.iNet ATX installation and troubleshooting](https://docs.gl-inet.com/kvm/en/user_guide/gl-atx-board/)
- [BIOS access user reports and GL.iNet responses](https://forum.gl-inet.com/t/bios-level-access-problem-no-hdmi-signal-mouse-and-keyboard/60748)
- [Snapshot format failure observed by another integration](https://github.com/DustinTrap/kvm-pilot/issues/107)

The last report concerns an RM1PE, not every Comet. Its high-resolution encoder
failure is not proof that another model has the same fault. Likewise, reports
of virtual-media or identity workarounds are context-specific, not defaults.
