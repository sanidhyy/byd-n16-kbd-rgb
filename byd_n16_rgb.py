#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import hid

# Supported USB HID devices: (vendor_id, product_id, name)
SUPPORTED_DEVICES = (
    (0x340E, 0x8002, "BYD N16"),
)

RGB_INTERFACE = 1


class DeviceError(Exception):
    """The RGB device was not found or could not be opened."""

CONFIG_DIR = Path.home() / ".config" / "byd-n16-rgb"
STATE_FILE = CONFIG_DIR / "state.json"

DEFAULT_R, DEFAULT_G, DEFAULT_B = 255, 255, 255
DEFAULT_BRIGHTNESS = 100

# global effect names
GLOBAL_EFFECTS = {
    'off': 0x10,
    'always_on': 0x11,
    'breath': 0x12,
    'clock': 0x13,
    'rainbow': 0x14,
    'flow': 0x15,
    'wave': 0x16,
}

SECTION_EFFECTS = {
    'always_on': 0x00,
    'breath': 0x01,
    'clock': 0x02,
    'rainbow': 0x03,
}

CYCLE_ORDER_GLOBAL = ['always_on', 'breath', 'clock', 'rainbow', 'flow', 'wave']
CYCLE_ORDER_SECTION = ['always_on', 'breath', 'clock', 'rainbow']

# cli effect aliases
EFFECT_ALIASES = {
    'static': 'always_on',
    'alwayson': 'always_on',
    'always-on': 'always_on',
    'always on': 'always_on',
}

EFFECT_LABELS = {
    'off': 'Off',
    'always_on': 'Always On',
    'breath': 'Breath',
    'clock': 'Clock',
    'rainbow': 'Rainbow',
    'flow': 'Flow',
    'wave': 'Wave',
}

SECTION_LABELS = {
    0: 'Global (all keys)',
    1: 'Section 1 — left third (main keyboard)',
    2: 'Section 2 — center third (main keyboard)',
    3: 'Section 3 — right third (main keyboard)',
    4: 'Section 4 — numpad area',
}

COLOR_EFFECTS = {'always_on', 'breath', 'wave'}
BRIGHTNESS_EFFECTS = {'always_on', 'breath', 'clock', 'rainbow', 'flow', 'wave'}
GLOBAL_ONLY_EFFECTS = {'off', 'flow', 'wave'}
SECTION_ZONES = (1, 2, 3, 4)

def default_last_active(section=0):
    return {
        'effect': 'always_on',
        'r': DEFAULT_R,
        'g': DEFAULT_G,
        'b': DEFAULT_B,
        'brightness_pct': DEFAULT_BRIGHTNESS,
        'section': section,
    }


def default_state():
    return {
        'power_on': False,
        'last_active': default_last_active(0),
        'effects': {},
        'cycle_index': {str(i): 0 for i in range(5)},
        'suspended_from_on': False,
    }


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_state():
    ensure_config_dir()
    if not STATE_FILE.exists():
        return default_state()
    try:
        with STATE_FILE.open(encoding='utf-8') as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default_state()

    base = default_state()
    base.update({k: v for k, v in data.items() if k in base})
    if not isinstance(base.get('effects'), dict):
        base['effects'] = {}
    if not isinstance(base.get('cycle_index'), dict):
        base['cycle_index'] = {str(i): 0 for i in range(5)}
    if not isinstance(base.get('last_active'), dict):
        base['last_active'] = default_last_active(0)
    return base


def save_state(state):
    ensure_config_dir()
    with STATE_FILE.open('w', encoding='utf-8') as fh:
        json.dump(state, fh, indent=2)
        fh.write('\n')


def effect_storage_key(section, effect):
    return f"{section}:{effect}"


def get_saved_effect_settings(state, section, effect):
    entry = state.get('effects', {}).get(effect_storage_key(section, effect))
    if not entry:
        return DEFAULT_R, DEFAULT_G, DEFAULT_B, DEFAULT_BRIGHTNESS
    return (
        int(entry.get('r', DEFAULT_R)),
        int(entry.get('g', DEFAULT_G)),
        int(entry.get('b', DEFAULT_B)),
        int(entry.get('brightness_pct', DEFAULT_BRIGHTNESS)),
    )


def save_effect_settings(state, section, effect, r, g, b, brightness_pct):
    state.setdefault('effects', {})[effect_storage_key(section, effect)] = {
        'r': r,
        'g': g,
        'b': b,
        'brightness_pct': brightness_pct,
    }


def cycle_order_for(section):
    return CYCLE_ORDER_SECTION if section in SECTION_ZONES else CYCLE_ORDER_GLOBAL


def normalize_effect(name):
    if not name:
        return None
    key = name.strip().lower().replace('_', ' ')
    key = EFFECT_ALIASES.get(key, key.replace(' ', '_'))
    if key in GLOBAL_EFFECTS:
        return key
    return None


def normalize_section(section):
    try:
        value = int(section)
    except (TypeError, ValueError):
        return None
    if 0 <= value <= 4:
        return value
    return None


def validate_rgb(r, g, b):
    for label, value in (('R', r), ('G', g), ('B', b)):
        if not isinstance(value, int) or not (0 <= value <= 255):
            raise ValueError(f"{label} must be an integer from 0 to 255 (got {value!r})")


def validate_brightness(brightness_pct):
    if not isinstance(brightness_pct, int) or not (0 <= brightness_pct <= 100):
        raise ValueError(
            f"Brightness must be an integer from 0 to 100 (got {brightness_pct!r})"
        )


def allowed_effects(section):
    if section in SECTION_ZONES:
        return SECTION_EFFECTS
    return GLOBAL_EFFECTS


def validate_effect_for_target(effect, section):
    if effect not in allowed_effects(section):
        zone = f"section {section}" if section in SECTION_ZONES else "global"
        permitted = ', '.join(allowed_effects(section))
        raise ValueError(
            f"Effect '{effect}' is not valid for {zone}. Allowed: {permitted}"
        )
    if section in SECTION_ZONES and effect in GLOBAL_ONLY_EFFECTS:
        raise ValueError(
            f"Effect '{effect}' is global-only. "
            f"Use section 0 or pick: {', '.join(SECTION_EFFECTS)}"
        )


def section_command_byte(section, effect):
    mode_offset = SECTION_EFFECTS[effect]
    if section <= 2:
        return 0x60 + (section - 1) * 4 + mode_offset
    return 0x70 + (section - 3) * 4 + mode_offset


def effect_command_byte(effect, section):
    if section in SECTION_ZONES:
        return section_command_byte(section, effect)
    return GLOBAL_EFFECTS[effect]


def brightness_to_byte(brightness_pct):
    validate_brightness(brightness_pct)
    bright_hex = int(brightness_pct * 2.55)
    return min(bright_hex, 254)


def format_usb_id(vendor_id, product_id):
    return f"{vendor_id:04x}:{product_id:04x}"


def supported_devices_label():
    return ', '.join(
        f"{name} ({format_usb_id(vid, pid)})"
        for vid, pid, name in SUPPORTED_DEVICES
    )


def find_rgb_device():
    """Locate a connected supported device with the RGB HID interface."""
    detected_without_rgb = []

    for vendor_id, product_id, name in SUPPORTED_DEVICES:
        interfaces = list(hid.enumerate(vendor_id, product_id))
        if not interfaces:
            continue

        for info in interfaces:
            if info.get('interface_number') == RGB_INTERFACE:
                return {
                    'path': info['path'],
                    'vendor_id': vendor_id,
                    'product_id': product_id,
                    'name': name,
                    'product_string': info.get('product_string') or name,
                }

        detected_without_rgb.append(
            f"{name} ({format_usb_id(vendor_id, product_id)})"
        )

    if detected_without_rgb:
        devices = ', '.join(detected_without_rgb)
        raise DeviceError(
            f"Supported device detected ({devices}) but RGB interface "
            f"{RGB_INTERFACE} was not found. The keyboard module may be "
            f"connected on a different interface."
        )

    raise DeviceError(
        f"No supported keyboard RGB device found. Expected one of: "
        f"{supported_devices_label()}. "
        f"Verify with: lsusb"
    )


def open_rgb_device():
    match = find_rgb_device()
    device = hid.device()
    label = (
        f"{match['name']} ({format_usb_id(match['vendor_id'], match['product_id'])})"
    )
    try:
        device.open_path(match['path'])
    except OSError as e:
        raise DeviceError(
            f"Found {label} but could not open it: {e}. "
            f"Check USB permissions (see README udev rules)."
        ) from e
    return device


def ensure_rgb_device():
    """Verify a supported RGB device is connected and can be opened."""
    device = open_rgb_device()
    device.close()


def resolve_settings(state, section, effect, r=None, g=None, b=None, brightness_pct=None):
    """Use explicit values when provided, else saved per-effect settings, else white."""
    if r is not None and g is not None and b is not None and brightness_pct is not None:
        validate_rgb(r, g, b)
        validate_brightness(brightness_pct)
        return r, g, b, brightness_pct

    saved_r, saved_g, saved_b, saved_brightness = get_saved_effect_settings(
        state, section, effect
    )
    return (
        saved_r if r is None else r,
        saved_g if g is None else g,
        saved_b if b is None else b,
        saved_brightness if brightness_pct is None else brightness_pct,
    )


def persist_successful_apply(state, section, effect, r, g, b, brightness_pct):
    if effect != 'off':
        save_effect_settings(state, section, effect, r, g, b, brightness_pct)
        state['last_active'] = {
            'effect': effect,
            'r': r,
            'g': g,
            'b': b,
            'brightness_pct': brightness_pct,
            'section': section,
        }
        state['power_on'] = True
    else:
        state['power_on'] = False
    save_state(state)


def set_keyboard(
    effect='always_on',
    r=DEFAULT_R,
    g=DEFAULT_G,
    b=DEFAULT_B,
    brightness_pct=DEFAULT_BRIGHTNESS,
    section=0,
    *,
    update_config=True,
):
    try:
        section = normalize_section(section)
        if section is None:
            raise ValueError("Section must be 0 (global) or 1-4 (zone)")

        effect = normalize_effect(effect)
        if effect is None:
            raise ValueError("Unknown effect. See --help for valid names.")

        validate_effect_for_target(effect, section)
        validate_rgb(r, g, b)
        validate_brightness(brightness_pct)

        bright_hex = brightness_to_byte(brightness_pct)
        effect_hex = effect_command_byte(effect, section)

        device = open_rgb_device()
        try:
            payload = [0x00] * 64
            payload[0] = 0x06
            payload[1] = effect_hex
            payload[2] = 0x04
            payload[7] = r
            payload[8] = g
            payload[9] = b
            payload[10] = bright_hex
            payload[63] = sum(payload[1:63]) & 0xFF
            device.write(payload)
        finally:
            device.close()

        if update_config:
            state = load_state()
            persist_successful_apply(state, section, effect, r, g, b, brightness_pct)

        target_str = SECTION_LABELS[section]
        effect_label = EFFECT_LABELS.get(effect, effect)
        print(
            f"Hardware ({target_str}) → {effect_label} | "
            f"R:{r} G:{g} B:{b} | Brightness: {brightness_pct}% | "
            f"Cmd: {effect_hex:#04x} | Checksum: {payload[63]:#04x}"
        )
        return True

    except ValueError as e:
        print(f"Invalid input: {e}")
        return False
    except DeviceError as e:
        print(f"Device error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def cmd_toggle(section=0):
    section = normalize_section(section)
    if section is None:
        raise ValueError("Section must be 0 (global) or 1-4 (zone)")

    state = load_state()
    if state.get('power_on', False):
        last = state.get('last_active', default_last_active(section))
        print(
            f"Toggling off (restoring later: {EFFECT_LABELS.get(last['effect'], last['effect'])}, "
            f"R:{last['r']} G:{last['g']} B:{last['b']}, {last['brightness_pct']}%)"
        )
        return set_keyboard(
            effect='off',
            r=0,
            g=0,
            b=0,
            brightness_pct=0,
            section=section,
            update_config=True,
        )

    last = state.get('last_active', default_last_active(section))
    restore_section = normalize_section(last.get('section', section))
    if restore_section is None:
        restore_section = section

    effect = normalize_effect(last.get('effect', 'always_on')) or 'always_on'
    validate_effect_for_target(effect, restore_section)

    r, g, b, brightness_pct = resolve_settings(
        state,
        restore_section,
        effect,
        last.get('r'),
        last.get('g'),
        last.get('b'),
        last.get('brightness_pct'),
    )

    effect_name = EFFECT_LABELS.get(effect, effect)
    print(f"Toggling on → {effect_name} | R:{r} G:{g} B:{b} | {brightness_pct}%")
    return set_keyboard(
        effect=effect,
        r=r,
        g=g,
        b=b,
        brightness_pct=brightness_pct,
        section=restore_section,
        update_config=True,
    )

def cmd_suspend():
    """Turn off the keyboard for idle/lock, but remember if it was on."""
    state = load_state()
    currently_on = state.get('power_on', False)
    
    # Save the current state to a special suspend flag
    state['suspended_from_on'] = currently_on
    save_state(state)
    
    if currently_on:
        print("Suspending: Turning hardware off.")
        # Turn it off, which sets power_on to False, but our suspend flag is saved
        return set_keyboard('off', r=0, g=0, b=0, brightness_pct=0, update_config=True)
        
    print("Suspending: Hardware was already off.")
    return True

def cmd_resume():
    """Restore the keyboard only if it was suspended while on."""
    state = load_state()
    
    # Check the flag, default to False if missing, and remove it from state
    should_resume = state.pop('suspended_from_on', False)
    save_state(state)
    
    if should_resume:
        print("Resuming: Restoring previous state.")
        # Because power_on is currently False, cmd_toggle will turn it back ON
        return cmd_toggle(section=0)
        
    print("Resuming: Hardware was manually turned off prior to suspend. Leaving off.")
    return True

def cmd_cycle(section=0):
    section = normalize_section(section)
    if section is None:
        raise ValueError("Section must be 0 (global) or 1-4 (zone)")

    state = load_state()
    order = cycle_order_for(section)
    section_key = str(section)
    current_index = int(state.get('cycle_index', {}).get(section_key, 0))
    next_index = (current_index + 1) % len(order)
    effect = order[next_index]

    r, g, b, brightness_pct = get_saved_effect_settings(state, section, effect)

    state.setdefault('cycle_index', {})[section_key] = next_index
    save_state(state)

    effect_name = EFFECT_LABELS.get(effect, effect)
    print(f"Cycling → {effect_name} | R:{r} G:{g} B:{b} | {brightness_pct}%")
    return set_keyboard(
        effect=effect,
        r=r,
        g=g,
        b=b,
        brightness_pct=brightness_pct,
        section=section,
        update_config=True,
    )


def prompt_int(label, min_val, max_val, default):
    hint = f" ({min_val}-{max_val})"
    while True:
        raw = input(f"{label}{hint} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if min_val <= value <= max_val:
                return value
        except ValueError:
            pass
        print(f"  Enter an integer between {min_val} and {max_val}.")


def select_effect(section):
    effects = allowed_effects(section)
    names = list(effects.keys())
    scope = "section" if section in SECTION_ZONES else "global"
    print(f"\nKeyboard RGB effects ({scope}):")
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {EFFECT_LABELS.get(name, name)}")

    while True:
        raw = input("\nSelect effect (number or name): ").strip()
        if not raw:
            continue
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(names):
                return names[idx]
            print(f"  Pick a number from 1 to {len(names)}.")
            continue
        canonical = normalize_effect(raw)
        if canonical in effects:
            return canonical
        print(
            f"  Unknown effect. Choose from: "
            f"{', '.join(EFFECT_LABELS.get(n, n) for n in names)}"
        )


def prompt_settings(effect, section):
    state = load_state()
    defaults = get_saved_effect_settings(state, section, effect)

    r, g, b, brightness_pct = defaults
    needs_color = effect in COLOR_EFFECTS
    needs_brightness = effect in BRIGHTNESS_EFFECTS

    if needs_color or needs_brightness:
        print()

    if needs_color:
        print(f"Color for '{EFFECT_LABELS.get(effect, effect)}' (0-255 per channel):")
        r = prompt_int("  Red", 0, 255, defaults[0])
        g = prompt_int("  Green", 0, 255, defaults[1])
        b = prompt_int("  Blue", 0, 255, defaults[2])
    elif effect == 'rainbow':
        print("Rainbow cycles colors automatically — RGB is not used.")
    elif effect == 'flow':
        print("Flow cycles colors automatically — RGB is not used.")
    elif effect == 'clock':
        print("Clock effect uses a fixed palette — RGB is not used.")
    elif effect == 'off':
        print("Off — no color or brightness settings needed.")

    if needs_brightness:
        brightness_pct = prompt_int("Brightness (%)", 0, 100, defaults[3])

    return r, g, b, brightness_pct


def run_interactive():
    print("BYD N16 keyboard RGB controller")
    print(f"Config: {STATE_FILE}")

    try:
        ensure_rgb_device()
    except DeviceError as e:
        print(f"Device error: {e}")
        sys.exit(1)

    print("\nZones:")
    for num, label in SECTION_LABELS.items():
        print(f"  {num}: {label}")

    section = prompt_int("\nTarget zone", 0, 4, 0)
    effect = select_effect(section)
    r, g, b, brightness_pct = prompt_settings(effect, section)
    ok = set_keyboard(
        effect=effect, r=r, g=g, b=b, brightness_pct=brightness_pct, section=section
    )
    sys.exit(0 if ok else 1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='byd-n16-rgb',
        description=(
            'Control BYD N16 keyboard RGB on Linux. '
            f'Supported devices: {supported_devices_label()}.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s -t\n"
            "      Toggle keyboard RGB off/on (restores last state when turning on).\n"
            "  %(prog)s -t -s 2\n"
            "      Toggle for section 2 only.\n"
            "  %(prog)s -c\n"
            "      Cycle global effects (uses saved RGB/brightness per effect).\n"
            "  %(prog)s -c -s 2\n"
            "      Cycle effects for section 2.\n"
            "  %(prog)s wave\n"
            "      Apply wave with saved settings, or white @ 100%% if none saved.\n"
            "  %(prog)s wave 5 60 128 75\n"
            "      Apply wave with custom RGB and brightness (saved for next time).\n"
            "  %(prog)s always_on 255 0 0 100 -s 2\n"
            "      Red always-on on section 2 (center third of main keyboard).\n"
            "  %(prog)s --suspend\n"
            "      Turn off RGB before sleep/lock; remember if it was on.\n"
            "  %(prog)s --resume\n"
            "      Restore RGB after wake only if it was on before suspend.\n"
            f"\nConfig file: {STATE_FILE}"
        ),
    )
    parser.add_argument('-t', '--toggle', action='store_true', help='Toggle keyboard RGB off/on')
    parser.add_argument(
        '-c', '--cycle', action='store_true',
        help='Cycle through effects (saved RGB/brightness per effect when omitted)',
    )
    parser.add_argument('--suspend', action='store_true', help='Suspend RGB state (for system idle)')
    parser.add_argument('--resume', action='store_true', help='Resume RGB state (for system wake)')
    parser.add_argument(
        '-s', '--section', type=int, default=0, metavar='N',
        help='Target zone for -t/-c or quick apply (0=global, 1-4=zone)',
    )
    parser.add_argument('effect', nargs='?', help='Effect name (global quick apply)')
    parser.add_argument('r', nargs='?', type=int, help='Red (0-255)')
    parser.add_argument('g', nargs='?', type=int, help='Green (0-255)')
    parser.add_argument('b', nargs='?', type=int, help='Blue (0-255)')
    parser.add_argument('brightness_pct', nargs='?', type=int, help='Brightness (0-100)')
    return parser


def run_quick_apply(args):
    section = normalize_section(args.section)
    if section is None:
        raise ValueError("Section must be 0 (global) or 1-4 (zone)")

    effect = normalize_effect(args.effect)
    if effect is None:
        raise ValueError(f"Unknown effect: {args.effect!r}")

    validate_effect_for_target(effect, section)
    state = load_state()

    if args.r is None and args.g is None and args.b is None and args.brightness_pct is None:
        r, g, b, brightness_pct = get_saved_effect_settings(state, section, effect)
    else:
        if args.r is None or args.g is None or args.b is None:
            raise ValueError("Quick apply requires R G B together, or omit all for saved values")
        brightness_pct = (
            args.brightness_pct if args.brightness_pct is not None else DEFAULT_BRIGHTNESS
        )
        r, g, b, brightness_pct = resolve_settings(
            state, section, effect, args.r, args.g, args.b, brightness_pct
        )

    return set_keyboard(
        effect=effect,
        r=r,
        g=g,
        b=b,
        brightness_pct=brightness_pct,
        section=section,
    )


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.toggle:
            ok = cmd_toggle(section=args.section)
        elif args.cycle:
            ok = cmd_cycle(section=args.section)
        elif args.suspend:
            ok = cmd_suspend()
        elif args.resume:
            ok = cmd_resume()
        elif args.effect is None:
            run_interactive()
            return
        else:
            ok = run_quick_apply(args)

        sys.exit(0 if ok else 1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
