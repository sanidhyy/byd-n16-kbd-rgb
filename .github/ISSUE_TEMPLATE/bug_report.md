---
name: Bug report
about: Report a problem with byd-n16-rgb
title: ''
labels: bug
assignees: ''

---

**Describe the bug**
A clear description of what went wrong.

**To reproduce**
Steps and exact command(s):

```bash
# example
byd-n16-rgb always_on 255 0 0 100 -s 2
```

1.
2.
3.

**Expected behavior**
What you expected the keyboard RGB (or CLI) to do.

**Actual behavior**
What happened instead — include full terminal output if there was an error.

```
paste output here
```

**Environment**

- Laptop model: [e.g. Infinix GT Book]
- OS / distro: [e.g. CachyOS, Arch, Ubuntu]
- Install method: [pipx / AUR / manual `python byd_n16_rgb.py`]
- `byd-n16-rgb` version: [e.g. 0.1.0]
- USB device present: [run `lsusb | grep 340e:8002` — paste result]

**Diagnostics**

Please run these and paste the output:

```bash
lsusb -v -d 340e:8002 2>/dev/null | head -80
ls -la /dev/hidraw*
byd-n16-rgb always_on 255 0 0 100
byd-n16-rgb --help
```

If the issue is effect- or zone-specific, include the exact command, section (`-s`), and whether any keys lit up at all.

**Additional context**
Anything else that might help — udev rules, pipx vs system Python, Hyprland keybinds, idle/suspend hooks, etc.
