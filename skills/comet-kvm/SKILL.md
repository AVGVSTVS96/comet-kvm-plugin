---
name: comet-kvm
description: Operate another computer through a configured GL.iNet Comet KVM. Use for remote setup, repair, BIOS/UEFI, boot menus, installers, and desktop work requiring display, keyboard, mouse, or physical power controls.
---

# Operating through Comet

You have physical peripherals attached to another computer. The screen is your
evidence; a successful input call only confirms delivery to the KVM.

## Observe and act

- Discover configured Comets and name the intended endpoint on every operation.
- Observe before typing, clicking, or deciding which boot state you are in.
- Use short action sequences with a fresh screenshot at meaningful transitions.
- Allow rendering/boot time; a frame immediately after input can lag its effect.
- Prefer keyboard navigation for menus, dialogs, terminals, and firmware setup.
- Establish input focus before typing. Newlines submit; tabs change focus.
- Text entry simulates a US keyboard. Check the remote layout and Caps Lock,
  especially for passwords or punctuation. Unicode is not clipboard paste.
- After an uncertain action, inspect the result before deciding what to repeat.

## Mouse

- Absolute coordinates cover the captured display, independent of image size.
- Prefer absolute positioning for desktops. Use short relative movements when
  firmware ignores absolute input; observe the pointer before clicking.
- Relative motion is affected by remote acceleration and does not map to pixels.
- Mode switching is handled by movement calls; wait for the pointer to respond.
- Remote natural-scrolling settings can reverse the visible effect of a wheel.

## Boot and power

- During POST, use short repeated setup/boot-menu key presses with observation;
  do not assume a vendor's setup key or blindly navigate an unseen BIOS.
- A blank HDMI image can mean a boot transition, sleep, the wrong video output,
  or no signal. It does not establish power state or a crashed OS.
- Read ATX state before a button action. Short power presses follow the target's
  own behavior; long presses and reset can interrupt writes and lose data.
- Prefer an orderly OS shutdown when it is responsive. After a power action,
  observe the state and display; acknowledgement does not mean boot completed.
- ATX reports may disagree: compare the reported power field, LEDs, and video
  rather than treating an individual LED as definitive.

## Recovery

- Check a harmless, reversible input before declaring HID broken. Some Comets
  report keyboard offline even while input works.
- Connection recovery and key/button release belong to the server. Do not replay
  a command or power press just because its response was lost.
- Persistent missing video or BIOS-only input failure: load
  [troubleshooting.md](troubleshooting.md) for verified causes and source links.
