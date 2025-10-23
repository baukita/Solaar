# Solaar Daemon

This directory contains the headless daemon version of Solaar, which allows you to run Solaar as a background service without any GUI dependencies.

## Features

- **Headless Operation**: No GTK or GUI dependencies required
- **Same Device Support**: All receiver and device functionality from the GUI version
- **Configuration Preservation**: Uses the same configuration files as the GUI version
- **Service Integration**: Proper daemon with PID files, logging, and signal handling
- **CLI Compatibility**: All `solaar` CLI commands continue to work

## Installation

### Manual Installation

1. Copy the daemon binary:
   ```bash
   sudo cp bin/solaar-daemon /usr/bin/
   sudo chmod +x /usr/bin/solaar-daemon
   ```

2. Ensure udev rules are installed:
   ```bash
   sudo cp rules.d/42-logitech-unify-permissions.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   ```

### Systemd Service

1. Install the service file:
   ```bash
   sudo cp share/systemd/solaar.service /etc/systemd/system/
   ```

2. Create the solaar user:
   ```bash
   sudo useradd -r -s /bin/false -g plugdev solaar
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable solaar
   sudo systemctl start solaar
   ```

4. Check status:
   ```bash
   sudo systemctl status solaar
   sudo journalctl -u solaar -f
   ```

### Traditional Init System

1. Install the init script:
   ```bash
   sudo cp share/init.d/solaar /etc/init.d/
   sudo chmod +x /etc/init.d/solaar
   ```

2. Create the solaar user:
   ```bash
   sudo useradd -r -s /bin/false -g plugdev solaar
   ```

3. Enable and start:
   ```bash
   sudo update-rc.d solaar defaults
   sudo service solaar start
   ```

## Usage

### Command Line Options

```bash
solaar-daemon --help
```

**Key Options:**
- `--no-fork`: Run in foreground (useful for testing)
- `--pid-file PATH`: Write PID to specified file
- `--debug`: Enable debug logging (can be repeated for more verbosity)
- `--hidraw PATH`: Use specific receiver device
- `--restart-on-wake-up`: Restart on system suspend/resume

### Testing

Run in foreground with debug output:
```bash
./bin/solaar-daemon --no-fork --debug
```

### Using with GUI

The daemon and GUI versions can coexist but should not run simultaneously. The daemon provides the same functionality as the GUI version but without the graphical interface.

### CLI Commands

All existing CLI commands work with the daemon:
```bash
solaar show                    # Show device information
solaar config <device> <setting> <value>  # Configure devices
solaar pair                    # Pair new devices
solaar unpair <device>         # Unpair devices
```

## Logging

The daemon logs to:
- **Systemd**: `journalctl -u solaar`
- **Syslog**: `/var/log/syslog` or `/var/log/messages`
- **Debug mode**: Console output when using `--no-fork --debug`

## Troubleshooting

1. **Permission Issues**: Ensure the solaar user is in the `plugdev` group and udev rules are installed
2. **Device Not Found**: Check `lsusb` for Logitech receivers and verify `/dev/hidraw*` permissions
3. **Service Won't Start**: Check `journalctl -u solaar` for error messages
4. **Multiple Instances**: Ensure GUI version is not running simultaneously

## Security

The systemd service includes security hardening:
- Runs as non-root user
- Restricted file system access
- Device access limited to USB/HID devices only
- No new privileges allowed