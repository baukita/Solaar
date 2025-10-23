#!/usr/bin/env python3

## Copyright (C) 2012-2013  Daniel Pavel
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License along
## with this program; if not, write to the Free Software Foundation, Inc.,
## 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import argparse
import atexit
import faulthandler
import locale
import logging
import os
import os.path
import platform
import signal
import sys
import tempfile
import time

from traceback import format_exc

from solaar import NAME
from solaar import __version__
from solaar import cli
from solaar import configuration
from solaar import dbus
from solaar import listener
from solaar.custom_logger import CustomLogger

logging.setLoggerClass(CustomLogger)
logger = logging.getLogger(__name__)

temp = tempfile.NamedTemporaryFile(prefix="Solaar_daemon_", mode="w", delete=True)
_running = True


def create_parser():
    arg_parser = argparse.ArgumentParser(
        prog=NAME.lower() + "-daemon", 
        epilog="For more information see https://pwr-solaar.github.io/Solaar"
    )
    arg_parser.add_argument(
        "-d",
        "--debug",
        action="count",
        default=0,
        help="print logging messages, for debugging purposes (may be repeated for extra verbosity)",
    )
    arg_parser.add_argument(
        "-D",
        "--hidraw",
        action="store",
        dest="hidraw_path",
        metavar="PATH",
        help="unifying receiver to use; the first detected receiver if unspecified. Example: /dev/hidraw2",
    )
    arg_parser.add_argument(
        "--restart-on-wake-up",
        action="store_true",
        help="restart Solaar on sleep wake-up (experimental)",
    )
    arg_parser.add_argument(
        "--pid-file",
        metavar="PATH",
        help="write daemon PID to this file",
    )
    arg_parser.add_argument(
        "--no-fork",
        action="store_true",
        help="run in foreground (don't fork into background)",
    )
    arg_parser.add_argument("-V", "--version", action="version", version="%(prog)s " + __version__)
    arg_parser.add_argument("--help-actions", action="store_true", help="describe the command-line actions")
    arg_parser.add_argument(
        "action",
        nargs=argparse.REMAINDER,
        choices=cli.actions,
        help="command-line action to perform (optional); append ' --help' to show args",
    )
    return arg_parser


def _parse_arguments():
    arg_parser = create_parser()
    args = arg_parser.parse_args()

    if args.help_actions:
        cli.print_help()
        return

    log_format = "%(asctime)s,%(msecs)03d %(levelname)8s [%(threadName)s] %(name)s: %(message)s"
    log_level = logging.ERROR - 10 * args.debug
    logging.getLogger("").setLevel(min(log_level, logging.WARNING))
    file_handler = logging.StreamHandler(temp)
    file_handler.setLevel(max(min(log_level, logging.WARNING), logging.INFO))
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger("").addHandler(file_handler)
    if args.debug > 0 or args.no_fork:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(log_format))
        stream_handler.setLevel(log_level)
        logging.getLogger("").addHandler(stream_handler)

    if not args.action:
        language, encoding = locale.getlocale()
        logger.info("daemon version %s, language %s (%s)", __version__, language, encoding)

    return args


def daemon_status_changed(device, alert=None, reason=None):
    """Headless replacement for ui.status_changed"""
    assert device is not None
    if logger.isEnabledFor(logging.INFO):
        try:
            if device.kind is None:
                logger.info(
                    "daemon status_changed %r: %s (%X) %s",
                    device,
                    "present" if bool(device) else "removed",
                    alert if alert is not None else 0,
                    reason or "",
                )
            else:
                device.ping()
                logger.info(
                    "daemon status_changed %r: %s %s (%X) %s",
                    device,
                    "paired" if bool(device) else "unpaired",
                    "online" if device.online else "offline",
                    alert if alert is not None else 0,
                    reason or "",
                )
        except Exception as e:
            logger.info("daemon status_changed for unknown device: %s", e)


def daemon_setting_changed(device, setting_class, vals):
    """Headless replacement for ui.setting_changed"""
    logger.info("daemon setting_changed %s: %s = %s", device, setting_class, vals)


def daemon_error_handler(reason, device_path):
    """Headless replacement for ui.common.error_dialog"""
    logger.error("daemon error: %s for device %s", reason, device_path)


def _handlesig(signl, stack):
    global _running
    if signl == int(signal.SIGINT):
        if logger.isEnabledFor(logging.INFO):
            faulthandler.dump_traceback()
        logger.info(f"{NAME.lower()}-daemon: exit due to keyboard interrupt")
    elif signl == int(signal.SIGTERM):
        logger.info(f"{NAME.lower()}-daemon: exit due to SIGTERM")
    else:
        logger.info(f"{NAME.lower()}-daemon: exit due to signal %d", signl)
    
    _running = False


def _daemon_run_loop(startup_hook, shutdown_hook):
    """Headless replacement for ui.run_loop"""
    global _running
    
    # Handle signals for clean shutdown
    signal.signal(signal.SIGTERM, _handlesig)
    signal.signal(signal.SIGINT, _handlesig)
    
    startup_hook()
    
    try:
        # Keep daemon alive
        while _running:
            time.sleep(1)
    except Exception as e:
        logger.error("daemon loop error: %s", e)
    finally:
        shutdown_hook()


def _write_pid_file(pid_file):
    """Write PID to file and set up cleanup"""
    if pid_file:
        try:
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
            atexit.register(lambda: os.path.exists(pid_file) and os.unlink(pid_file))
            logger.info("PID %d written to %s", os.getpid(), pid_file)
        except Exception as e:
            logger.error("Failed to write PID file %s: %s", pid_file, e)


def _daemonize():
    """Fork into background"""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Parent exits
    except OSError as e:
        logger.error("fork #1 failed: %s", e)
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        # Second fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Second parent exits
    except OSError as e:
        logger.error("fork #2 failed: %s", e)
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def main():
    if platform.system() not in ("Darwin", "Windows"):
        try:
            import pyudev
        except ImportError:
            sys.exit(f"{NAME.lower()}-daemon: missing required system package python3-pyudev")

    args = _parse_arguments()
    if not args:
        temp.close()
        return
    
    if args.action:
        # if any argument, run commandline and exit
        result = cli.run(args.action, args.hidraw_path)
        temp.close()
        return result

    # Fork into background unless --no-fork specified
    if not args.no_fork:
        _daemonize()

    # Write PID file
    _write_pid_file(args.pid_file)

    udev_file = "42-logitech-unify-permissions.rules"
    if (
        platform.system() == "Linux"
        and logger.isEnabledFor(logging.WARNING)
        and not os.path.isfile("/etc/udev/rules.d/" + udev_file)
        and not os.path.isfile("/usr/lib/udev/rules.d/" + udev_file)
        and not os.path.isfile("/usr/local/lib/udev/rules.d/" + udev_file)
    ):
        logger.warning("Solaar udev file not found in expected location")
        logger.warning("See https://pwr-solaar.github.io/Solaar/installation for more information")
    
    try:
        listener.setup_scanner(daemon_status_changed, daemon_setting_changed, daemon_error_handler)

        if args.restart_on_wake_up:
            dbus.watch_suspend_resume(listener.start_all, listener.stop_all)
        else:
            dbus.watch_suspend_resume(lambda: listener.ping_all(True))

        configuration.defer_saves = True  # allow configuration saves to be deferred

        # main daemon event loop
        _daemon_run_loop(listener.start_all, listener.stop_all)
    except Exception:
        logger.error(f"{NAME.lower()}-daemon: error: {format_exc()}")
        sys.exit(1)

    temp.close()


if __name__ == "__main__":
    main()