# ⌨️ byd-n16-rgb

Unofficial Linux CLI for the **BYD N16** internal keyboard RGB controller (`USB 340e:8002`).

Controls colors, brightness, and lighting effects on laptops that use this module. Tested on the Infinix GT Book; other machines with the same USB ID may work.

---

## ✨ What it does

`byd-n16-rgb` sends lighting commands directly to the keyboard's RGB HID interface. Fn+F3 still handles basic firmware backlight separately — this tool is for full RGB control.

- 🌐 Set **global effects** across the whole keyboard (off, always on, breath, clock, rainbow, flow, wave)
- 🧩 Control **4 independent zones** — left, center, and right thirds of the main keyboard, plus the numpad
- 🎨 Adjust **RGB and brightness** per effect
- 🔁 **Toggle** RGB off/on while remembering the last state (`-t`)
- 🔃 **Cycle** through effects with per-effect saved settings (`-c`)
- 💤 **Suspend / resume** around sleep or lock (`--suspend` / `--resume`)
- 📋 Run an **interactive menu** when called with no arguments

State is saved to `~/.config/byd-n16-rgb/state.json`.

---

## 💻 Supported hardware

| Property      | Value                      |
| ------------- | -------------------------- |
| USB ID        | `340e:8002`                |
| `lsusb` name  | `BYD N16 CompatibilityHID` |
| RGB interface | Interface 1                |
| Tested on     | Infinix GT Book            |

```bash
lsusb | grep -i '340e:8002'
```

---

## 📦 Installation

> ⚠️ **Disclaimer:** This is an unofficial, reverse-engineered tool. It was developed and tested on an Infinix GT Book; other laptops with the same USB ID may work but are unsupported. Use at your own risk.

Requires **Python 3.10+** and **pipx**.

```bash
git clone https://github.com/sanidhyy/byd-n16-kbd-rgb.git
cd byd-n16-kbd-rgb
pipx install .
```

Then run `byd-n16-rgb --help` to verify.

> If installation fails, install the system **hidapi C library** (pipx bundles the Python package, but still needs the underlying library at runtime):
>
> - Arch / CachyOS: `sudo pacman -S hidapi`
> - Debian / Ubuntu: `sudo apt install libhidapi-hidraw0`
> - Fedora: `sudo dnf install hidapi`

### Arch / AUR

Install from the AUR:

```bash
yay -S byd-n16-rgb
```

---

## 🔐 USB permissions

Create `/etc/udev/rules.d/99-byd-n16-rgb.rules`:

```ru
KERNEL=="hidraw*", ATTRS{idVendor}=="340e", ATTRS{idProduct}=="8002", MODE="0666"
```

Reload udev rules to apply immediately:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## 🚀 Usage

### Interactive

```bash
byd-n16-rgb
```

### Quick apply

```bash
byd-n16-rgb wave                        # saved settings, or white @ 100%
byd-n16-rgb wave 5 60 128 75            # set and save custom values
byd-n16-rgb always_on 255 0 0 100 -s 2  # red on section 2
byd-n16-rgb always_on 255 255 255 100 -s 4  # white numpad
```

Omit R G B together to use saved values. Provide R G B (brightness optional, default 100) to set new ones.

### Toggle and cycle

```bash
byd-n16-rgb -t          # off ↔ restore last state
byd-n16-rgb -c          # cycle global effects
byd-n16-rgb -c -s 3     # cycle section 3 effects
```

### Suspend / resume

```bash
byd-n16-rgb --suspend
byd-n16-rgb --resume
```

### Aliases

`always_on` also accepts: `static`, `alwayson`, `always-on`, `always on`

```bash
byd-n16-rgb --help
```

---

## 🌈 Effects and zones

### Global (section 0)

| Effect      | Command byte | Description               |
| ----------- | ------------ | ------------------------- |
| `off`       | `0x10`       | Turn RGB off              |
| `always_on` | `0x11`       | Solid color               |
| `breath`    | `0x12`       | Pulsing color             |
| `clock`     | `0x13`       | Fixed palette animation   |
| `rainbow`   | `0x14`       | Cycling rainbow           |
| `flow`      | `0x15`       | Color flow                |
| `wave`      | `0x16`       | Wave pattern (custom RGB) |

### Per-zone (sections 1–4)

`off`, `flow`, and `wave` are global only. Per-zone modes use `always_on`, `breath`, `clock`, and `rainbow`.

| Section | Area         | `always_on` | `breath` | `clock` | `rainbow` |
| ------- | ------------ | ----------- | -------- | ------- | --------- |
| 1       | Left third   | `0x60`      | `0x61`   | `0x62`  | `0x63`    |
| 2       | Center third | `0x64`      | `0x65`   | `0x66`  | `0x67`    |
| 3       | Right third  | `0x70`      | `0x71`   | `0x72`  | `0x73`    |
| 4       | Numpad       | `0x74`      | `0x75`   | `0x76`  | `0x77`    |

```
┌─────────────────────────────────────────────────────┬──────────────┐
│  Section 1          Section 2          Section 3    │  Section 4   │
│  (left third)       (center third)     (right third)│  (numpad)    │
└─────────────────────────────────────────────────────┴──────────────┘
```

| `-s` | Area                         |
| ---- | ---------------------------- |
| `0`  | All keys                     |
| `1`  | Left third (main keyboard)   |
| `2`  | Center third (main keyboard) |
| `3`  | Right third (main keyboard)  |
| `4`  | Numpad                       |

Configure each zone with a separate command. Zones keep their state independently on the controller.

---

## ⌨️ Keybind examples

**Hyprland:**

```conf
bind = SUPER, F3, exec, byd-n16-rgb -t
bind = SUPER CTRL, F3, exec, byd-n16-rgb -c
```

**Hypridle / swayidle:**

```conf
# turn off RGB after 5 min idle, restore on activity
listener {
    timeout = 300
    on-timeout = byd-n16-rgb --suspend
    on-resume  = byd-n16-rgb --resume
}
```

```bash
swayidle -w timeout 300 'byd-n16-rgb --suspend' resume 'byd-n16-rgb --resume'
```

Optional feedback: `byd-n16-rgb -c && notify-send "Keyboard RGB" "Effect cycled"`

---

## 🔧 Troubleshooting

| Symptom                         | Fix                                             |
| ------------------------------- | ----------------------------------------------- |
| Permission denied               | Add udev rule or use sudo                       |
| Device not found                | Check `lsusb` for `340e:8002`                   |
| `wave` fails on a section       | Use `-s 0` — wave is global only                |
| Colors ignored on rainbow/clock | Expected — hardware ignores RGB for those modes |

---

## ⚙️ How it works

The keyboard exposes a composite USB HID device. **Interface 0** is normal typing; **interface 1** is the RGB controller. The tool opens interface 1 and writes a 64-byte report:

```
[0]=06  [1]=effect  [2]=04  [7]=R  [8]=G  [9]=B  [10]=brightness  [63]=checksum
```

Brightness is `percent × 2.55`, capped at 254. Checksum is `sum(bytes[1:63]) & 0xFF`.

Byte 1 is the effect command — see [Effects and zones](#effects-and-zones) for the full byte tables. Global mode (`-s 0`) sends one packet for the whole keyboard; per-zone mode (`-s 1`–`4`) sends one packet per section, leaving other zones unchanged.

### 💡 Quick example

Command:

```bash
byd-n16-rgb always_on 255 0 0 100 -s 2
```

This sets **section 2** (center third) to **solid red** at **100% brightness**. The tool builds and sends:

| Byte   | Value  | Meaning                                    |
| ------ | ------ | ------------------------------------------ |
| `[0]`  | `0x06` | Report ID                                  |
| `[1]`  | `0x64` | Section 2 + always on (see per-zone table) |
| `[2]`  | `0x04` | Lock/state flag                            |
| `[7]`  | `0xFF` | Red = 255                                  |
| `[8]`  | `0x00` | Green = 0                                  |
| `[9]`  | `0x00` | Blue = 0                                   |
| `[10]` | `0xFE` | Brightness 100% → `254`                    |
| `[63]` | `0x65` | Checksum of bytes 1–62                     |

```
06 64 04 00 00 00 00  FF 00 00  FE  00 ... 00  65
│  │  │               │  │  │   │              │
│  │  │               └──┴──┴───┘              └── checksum
│  │  │              RGB (red) Brightness (100%)
│  │  └── lock byte
│  └── effect (section 2, always on)
└── report ID
```

Only the center third of the main keyboard lights up red — sections 1, 3, and 4 stay as they were.

After a successful write, settings are saved to `~/.config/byd-n16-rgb/state.json` for toggle, cycle, and quick apply.

---

## 🤝 Contributing

Reports and packaging contributions welcome. For issues, include:

```bash
lsusb -v -d 340e:8002 2>/dev/null | head -80
byd-n16-rgb always_on 255 0 0 100
```

---

## 📄 License

See [LICENSE](LICENSE).
