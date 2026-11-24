# CleverSwitch – mouse button fork

**Press one mouse button and the mouse and the keyboard both move to the other computer.** Offline, without a Logitech account, with Logi Options+ allowed to keep running.

This is a fork of [CleverSwitch](https://github.com/MikalaiBarysevich/CleverSwitch) for Windows and macOS. It adds:

- **Switching by mouse button:** the thumb button (or back, forward, middle, SmartShift) sends every Logitech device that supports host switching to the channel you chose.
- **A tray / menu bar icon:** turn the switch on and off, pick the target channel and the button, name the channels, open Logi Options+, start at login.
- **Nothing to set up by hand:** the config file is created on first start and kept up to date by the menu.

Tested with `MX Master 3S for Business` and `MX Keys for Business`: a Windows notebook on a Bolt receiver, and a Mac with Apple silicon on Bluetooth with Logi Options+ running.

> **The keyboard's Easy-Switch keys do not take the mouse along** on these keyboards. See [Limits: the keyboard's Easy-Switch keys](#limits-the-keyboards-easy-switch-keys).

## How it works

1. Pair the keyboard and the mouse with every computer, on the same channel numbers (e.g. channel 1 = notebook, channel 2 = Mac).
2. Run CleverSwitch on **every** computer. On each one, set the target channel to the **other** computer: on the computer on channel 1 pick channel 2, on the computer on channel 2 pick channel 1.
3. Press the thumb button. CleverSwitch tells the keyboard and the mouse to switch to the target channel, and both land on the other computer, where CleverSwitch is waiting to send them back.

## Installation

Both builds are on the [pre-release page](https://github.com/Beardowings/CleverSwitch/releases/tag/dev-feature-mouse-button-switch). Install CleverSwitch on **every** computer you switch between. No admin rights are needed.

**Windows** (`cleverswitch_windows_x64.zip`)

1. Unzip it and put `cleverswitch.exe` in a folder of your own, for example `C:\Users\<you>\Programs\CleverSwitch\cleverswitch.exe`.
2. If endpoint protection blocks unknown programs, allow-list the exe by its SHA-256 (`Get-FileHash cleverswitch.exe` in PowerShell). Every build has a new hash.
3. Double-click `cleverswitch.exe`. The icon appears in the tray (it may sit under the arrow next to the clock).
4. In the menu, pick the **target channel** and turn on **Start at login**.

**macOS** (`cleverswitch_macOS.tar.gz`, Apple silicon)

1. Unpack it and move `CleverSwitch.app` to `/Applications`.
2. Open it once with right-click → **Open** (the app is not notarized). If macOS still refuses, go to **System Settings → Privacy & Security** and click **Open Anyway**.
3. Allow **Input Monitoring** and **Bluetooth** for CleverSwitch when asked. If no prompt appears, add `/Applications/CleverSwitch.app` under **System Settings → Privacy & Security → Input Monitoring**, then quit and reopen it.
4. The icon appears in the menu bar. Pick the **target channel** and turn on **Start at login**.

To update, quit CleverSwitch from its menu, replace the exe or the app, and start it again. Settings stay in the config file.

## Tray / menu bar icon

On Windows and macOS CleverSwitch shows an icon in the tray / menu bar. The menu is in German or English, following the system language:

| Menu item | What it does |
|-----------|--------------|
| Status line | The button and the target channel, or that the switch is off |
| Switch with mouse button | Turns the mouse button switch on and off |
| Target channel | The Easy-Switch channel (1–3) the button sends both devices to |
| Name channels | Labels for the channels, e.g. "1 – Notebook", "2 – Mac" |
| Button | Thumb, back, forward, middle or SmartShift button |
| Mouse follows the keyboard's Easy-Switch keys | Optional, **off by default**; see [Mouse follows the keyboard](#mouse-follows-the-keyboard-optional-off-by-default) |
| Open Logi Options+ | Starts Options+ when it is installed |
| Start at login | A `HKCU\…\Software\Microsoft\Windows\CurrentVersion\Run` value on Windows, a LaunchAgent in `~/Library/LaunchAgents` on macOS; no admin rights |
| Advanced | Divert the button itself, open the config file, open the log folder |
| Quit CleverSwitch | Gives the button back to the mouse and exits |

Every change applies at once, without a restart, and is saved to the config file. `--no-tray` runs without the icon.

## Config file

CleverSwitch reads its config file from:

| Platform | Path |
|----------|------|
| Windows | `C:\Users\<you>\.config\cleverswitch\config.yaml` (`%USERPROFILE%\.config\cleverswitch\config.yaml`) |
| macOS | `/Users/<you>/.config/cleverswitch/config.yaml` (`~/.config/cleverswitch/config.yaml`) |
| Linux | `/home/<you>/.config/cleverswitch/config.yaml` (`~/.config/cleverswitch/config.yaml`) |

You can override this path with the `--config` CLI flag.

If the file does not exist, CleverSwitch creates it on first start (only for the default path, not with `--config`). On Windows and macOS the menu item **Advanced → Open config file** opens it. Every option is described in [`config.example.yaml`](config.example.yaml). Changes made in the menu are saved there at once; changes made by hand need a restart. The menu rewrites the file without comments.

Without a config file, CleverSwitch starts with the mouse button switch on and no target channel; pick the channel in the menu.

### Mouse button settings

The same settings as the menu, in the config file:

```yaml
mouse_button_switch:
  button: gesture   # gesture (thumb) | back | forward | middle | smartshift, or a CID such as 0x00C3
  host: 2           # 1..3, the Easy-Switch channel to switch to
  divert: true      # false: only listen while Logi Options+ diverts the button
```

- Run CleverSwitch on every computer, each pointing at the **other** one: `host: 2` on the computer on channel 1, `host: 1` on the computer on channel 2.
- With `divert: true` (default) CleverSwitch diverts the button over HID++ (0x1B04), so the button no longer does its normal action. The divert is temporary: the mouse forgets it on power-off and CleverSwitch un-diverts it on exit.
- **Next to Logi Options+:** if Options+ already assigns an action to the same button, it diverts the button too, and both programs see the press. Then set `divert: false` and give the button a harmless action in Options+ (it still runs). If Options+ leaves the button on its default, `divert: true` should work without touching Options+ (not yet tested on hardware).
- Every device that supports CHANGE_HOST (0x1814) is switched. A keyboard in deep sleep may miss the command; if it stays behind, press a key and switch again.
- Editing the file by hand needs a restart; changes from the menu do not. Channel names live in `host_names` (`1: Notebook`).

## Logs

CleverSwitch writes a size-rotated log file on every platform:

- **Linux:** `~/.local/state/cleverswitch/cleverswitch.log` (or `$XDG_STATE_HOME/cleverswitch/`). Under systemd the output also goes to the journal: `journalctl --user -u cleverswitch`.
- **macOS:** `~/Library/Logs/CleverSwitch/cleverswitch.log` (also visible in Console.app).
- **Windows:** `%LOCALAPPDATA%\CleverSwitch\Logs\cleverswitch.log`

When the file reaches its size limit it is renamed to `cleverswitch.log.1` (older ones shift to `.2`, `.3`, ...) and a fresh file is started. When run from a terminal, logs are printed there as well. If a second instance is started it logs to the console only. `-v` / `-vv` force DEBUG.

Logging is configured in the `logging:` section of the config file:

```yaml
logging:
  level: INFO          # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file:
    enabled: true      # false: console only
    path: ~/cleverswitch.log
    max_size_mb: 5     # 1..1024
    backup_count: 3    # 1..50
```

When reporting a bug, please attach this log file.

## Limits: the keyboard's Easy-Switch keys

The original CleverSwitch is built around the keyboard's Easy-Switch keys: the keyboard reports the press, and CleverSwitch sends the mouse to the same channel. That only works with keyboards that report the press, such as the `MX Keys` the original was tested with.

The `MX Keys for Business` (and, per the original project's issues [#113](https://github.com/MikalaiBarysevich/CleverSwitch/issues/113) and [#28](https://github.com/MikalaiBarysevich/CleverSwitch/issues/28), the `MX Keys S`) switch away without reporting which key was pressed. The computer only sees the keyboard disconnect, so the mouse stays behind. This happens on Bolt and on Bluetooth, with or without Logi Options+. The keys cannot be diverted either (the log says `cannot divert its Easy-Switch keys`). **Use the mouse button instead.**

On keyboards that do report the press, the relay from the original still works. If Logi Options+ takes the press away from CleverSwitch, `easy_switch: {divert: true}` in the config file makes CleverSwitch divert the keys, if the keyboard allows it.

### Mouse follows the keyboard (optional, off by default)

**Off by default**, and only worth trying when you switch between exactly two computers. For keyboards that never report the Easy-Switch press: when the keyboard leaves this computer and stays away for 1.5 s while the mouse is still connected, CleverSwitch sends the mouse to the target channel. Turn it on in the menu or with `follow_keyboard: true` under `mouse_button_switch`.

It cannot know where the keyboard went, only that it left, so the mouse always goes to the one target channel:

- With three channels in use, the mouse ends up on the wrong computer whenever the keyboard went to the other one.
- Switching the keyboard off, or the keyboard losing range or battery, sends the mouse away too.
- A switch CleverSwitch sent itself (the mouse button), a sleeping computer and an unplugged receiver are not followed.

## Inherited from the original CleverSwitch

Everything below comes from the original project and is unchanged in this fork: Linux support, switching at a screen edge, and hook scripts. For Linux, Homebrew and AUR installs see the original [installation guide](docs/Installation.md); those packages install the original CleverSwitch, without the mouse button switch and the tray icon.

## Edge Switch

Hold a modifier key (Ctrl by default) and move the cursor onto an edge of the screen to switch the keyboard and the mouse to the host you mapped to that edge — no Easy-Switch button needed. It is off until you add an `edge_switch` section to the config:

```yaml
edge_switch:
  modifier: ctrl         # ctrl | alt | shift | meta (Cmd / Win / Super), or a list: [ctrl, alt]
  cooldown_ms: 1000      # ignore repeats for this long after a switch
  edges:                 # left | right | top | bottom -> host 1..3
    left: 1
    right: 2
```

- **Host numbers are the Easy-Switch channels** marked 1, 2, 3 on the keyboard and mouse: `left: 2` switches to channel 2. To confirm which number is which, press the physical button and read `'MX Keys' switched to host N` in the log.
- Only the outer edges of all your monitors together count; the border between two monitors does not. With monitors of different heights, the shorter one's exposed side sits inside that outer box, so only the edges of the box fire.
- The cursor has to move **onto** the edge while the modifier is held. Pressing the modifier while the cursor already sits at an edge does nothing, so arriving on the other host with the key still down does not bounce you back.
- The modifiers must match exactly (Ctrl+Shift does not fire a `ctrl` edge), and a held mouse button blocks it, so Ctrl-drag and Ctrl-click near an edge are safe.
- Every device that supports CHANGE_HOST (0x1814) is switched; a device without it is left alone. With only a mouse, no SWITCH hook runs unless `hooks.fire_for_all_devices: true`, because hooks are keyboard-only by default.
- Inside a remote desktop or VM session, edge switch sees that session's cursor and fires there like anywhere else.
- The binary and source installers offer to write this section for you; the AUR package installs no config.
- Editing `edge_switch` needs a restart; the config is read once at startup.
- If edge switch cannot start (for example the permission is missing), CleverSwitch keeps running and tries again whenever a device connects.
- Run one CleverSwitch per machine. Two instances are only rejected on KDE and GNOME; anywhere else both would send their own switches.
- The switch is sent while the modifier is still down, so the host you leave may not see it released. If it seems stuck there, tap it once when you come back.

| Platform | Needs |
|----------|-------|
| Windows | Nothing extra. |
| macOS | *Input Monitoring* in System Settings → Privacy & Security, which CleverSwitch already needs. |
| Linux: X11 | Nothing extra: the X server reports the keys, buttons and cursor position. Under a systemd user service, `DISPLAY` must be in its environment (`systemctl --user import-environment DISPLAY XAUTHORITY`). |
| Linux: Hyprland | `/dev/input` read access, see [`/dev/input` access](#devinput-access). |
| Linux: KDE Plasma 6 | `/dev/input` read access, see [`/dev/input` access](#devinput-access). Nothing to install. |
| Linux: GNOME 45–51 | The CleverSwitch GNOME Shell extension, installed once. No `/dev/input` access. See [Enabling edge switch on KDE / GNOME](#enabling-edge-switch-on-kde--gnome). |
| Linux: other desktops | Not available. Other Wayland desktops (sway, niri, COSMIC...) do not tell programs where the cursor is; CleverSwitch logs a warning and keeps running without edge switch. |

### `/dev/input` access

Edge switch on Hyprland and KDE reads the keyboard and mouse through libinput, so CleverSwitch needs read access to Logitech `event*` nodes. The installer's udev rule [`rules.d/42-cleverswitch.rules`](rules.d/42-cleverswitch.rules) grants that to the logged-in user; restart CleverSwitch after installing it. Without Logitech devices, join the `input` group instead (`sudo usermod -aG input $USER`, then log in again).

The trade-off: programs you run can then read keystrokes from those Logitech devices, which Wayland otherwise prevents. This rule is how CleverSwitch already reaches HID++ over hidraw, so the capability exists either way; part 2 only widens it to `/dev/input`.

A remapper that grabs your keyboard or mouse exclusively (OpenLogi, input-remapper, keyd, kanata...) leaves the real device silent and re-sends its input through a virtual device, so CleverSwitch must be able to read that virtual device. The rule covers virtual devices that carry Logitech's vendor id, which is what OpenLogi creates; for other remappers use the `input` group.

**Turning it off.** The rule has two parts: HID++ access, which CleverSwitch always needs, and the `/dev/input` part above, which only edge switch on Hyprland and KDE uses. Comment out this line to keep only HID++ access:

```
SUBSYSTEM == "input", KERNEL == "event*", GOTO="cleverswitch_input"
```

Installed from the AUR the rule is in `/usr/lib/udev/rules.d/` and is replaced on upgrades, so edit a copy in `/etc/udev/rules.d/` (same file name), which takes precedence. Binary and source installs have it in `/etc/udev/rules.d/` already. Then reload and replug the receiver:

```
sudo udevadm control --reload-rules
sudo udevadm trigger
```

To turn it back on, delete the `/etc` copy (AUR) or undo the comment (binary/source) and reload again.

### Enabling edge switch on KDE / GNOME

Wayland keeps the cursor position away from ordinary programs, so on KDE and GNOME the desktop itself tells CleverSwitch which screen edge the cursor is on, over the session bus.

**KDE Plasma 6.** Nothing to install: while CleverSwitch runs it loads a small KWin script (`cleverswitch-edge`) and removes it when it stops. KWin scripts cannot see the keyboard, so CleverSwitch reads the held modifier from `/dev/input`, as on Hyprland — see [`/dev/input` access](#devinput-access). Plasma 5 is not supported.

**GNOME 45 to 51.** Install the CleverSwitch GNOME Shell extension once. It does nothing while CleverSwitch is not running, and GNOME then needs no `/dev/input` access.

Installed from the AUR, the extension is already in `/usr/share/gnome-shell/extensions/`, so skip to step 2. From the binary or source install, copy it:

1. Copy the extension:
   ```
   mkdir -p ~/.local/share/gnome-shell/extensions
   cp -r gnome-extension/cleverswitch@mikalaibarysevich.github.io ~/.local/share/gnome-shell/extensions/
   ```
2. Log out and back in. GNOME on Wayland only picks up new extensions at login.
3. Enable it:
   ```
   gnome-extensions enable cleverswitch@mikalaibarysevich.github.io
   ```
4. Check that `gnome-extensions info cleverswitch@mikalaibarysevich.github.io` shows the state `ACTIVE` (or `ENABLED`). If GNOME has user extensions turned off, turn them on with `gsettings set org.gnome.shell disable-user-extensions false`.

A binary or source install needs the extension copied again after upgrading CleverSwitch; the AUR package updates it. If anything is missing, CleverSwitch logs what to fix and tries again when a device connects. A modifier released and pressed again without moving the mouse is only noticed at the next mouse movement. The extension's `metadata.json` lists the GNOME versions it loads on (45 to 51 today), so a newer shell needs that list extended in a later CleverSwitch release.

### If nothing happens

`cleverswitch -v` logs the gesture at DEBUG: the modifier and button state on every change, edges ignored because they were already under the cursor when the gesture began, cooldown hits, and every switch. A healthy start names the reader, for example:

```
Edge switch reads the keys and the cursor position from GNOME Shell
Edge switch reads 5 input devices and the cursor position from Hyprland
Edge switch reads the keyboard, the buttons and the cursor position from the X server
Watching screen edges (edge-linux)
```

Anything else is one of: `Edge switch is not running: …` (with the reason, retried on the next device connection), `Edge switch cannot read any keyboard or mouse in /dev/input` (the udev rule or group, then restart), or `still unavailable` after a retry. On KDE and GNOME the message names the missing or disabled extension. To check the gesture itself without switching hosts, hold the modifier and move onto an edge while watching the log — the trace says what the detector saw.

## Hook Scripts

Hook scripts let you run custom commands or scripts in response to CleverSwitch events. Hooks are executed asynchronously and never block the switch relay.
You should use this when you need some extra logic. Like switch display input source when devices connects to current PC.

By default, hooks only fire for keyboard events. Set `hooks.fire_for_all_devices: true` in config to include mouse events as well.

### Events

| Event        | When it fires                                                 |
|--------------|---------------------------------------------------------------|
| `switch`     | The mouse button, an Easy-Switch key or an edge switch started a host change, and it was sent |
| `connect`    | A device connected (including wake from sleep)                |
| `disconnect` | A device disconnected (including sleep)                       |

### Environment variables

Each hook receives the following environment variables:

| Variable                   | Values                                | Description                                        |
|----------------------------|---------------------------------------|----------------------------------------------------|
| `CLEVERSWITCH_EVENT`       | `switch` \| `connect` \| `disconnect` | The event type                                     |
| `CLEVERSWITCH_DEVICE`      | `keyboard` \| `mouse`                 | The device that triggered the event                |
| `CLEVERSWITCH_DEVICE_NAME` | e.g. `MX Keys`                        | Human-readable device name                         |
| `CLEVERSWITCH_TARGET_HOST` | `1`, `2`, or `3`                      | Target host number (1-based; `switch` events only) |
| `CLEVERSWITCH_SWITCH_SOURCE` | `device` \| `edge` \| `button` \| `follow` | What started the switch (`switch` events only); for `edge`, `button` and `follow`, `CLEVERSWITCH_DEVICE` names a keyboard when one is known (a connected one first), otherwise any named device |

### Hook configuration

Hooks live in the [config file](#config-file). Each hook is a **named** entry with the following keys:

| Key       | Description                                                                            |
|-----------|----------------------------------------------------------------------------------------|
| `path`    | A script to run directly, without a shell. Mutually exclusive with `command`.           |
| `command` | A shell command (supports pipes, `$VAR` expansion, etc). Mutually exclusive with `path`. |
| `type`    | Which event(s) fire the hook: `CONNECT`, `SWITCH`, `DISCONNECT` — a single value or a list. |
| `timeout` | Seconds before the hook process is killed (default: `5`).                               |
| `fire_for_all_devices` | Optional per-hook override of the global `hooks.fire_for_all_devices`. Set `true` to also fire for mouse events, or `false` to stay keyboard-only; omit to inherit the global default. |

Specify exactly one of `path` or `command`; setting both (or neither) logs an error and skips that hook.

```yaml
hooks:
  # Set to true to also fire hooks for mouse events (default: false)
  # fire_for_all_devices: false

  notifyOnSwitch:
    command: "notify-send 'CleverSwitch' \"Switched to host $CLEVERSWITCH_TARGET_HOST\""
    type: SWITCH

  syncDisplayInput:
    path: "~/.config/cleverswitch/on_connect.sh"
    type: [CONNECT, DISCONNECT]
    fire_for_all_devices: true   # this hook also fires for the mouse
    timeout: 10
```

## Problems

This fork has no issue tracker of its own. Problems with the mouse button switch, the tray icon or the Windows/macOS builds belong to this fork, not to the original project; please do not report them there. Attach the [log file](#logs) when you describe a problem.

## Credits and license

CleverSwitch was written by [Mikalai Barysevich](https://github.com/MikalaiBarysevich/CleverSwitch). This fork is based on it and, like the original, is licensed under the [GNU General Public License v3.0](LICENSE.txt).
