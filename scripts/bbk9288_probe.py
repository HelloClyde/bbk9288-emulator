#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run a short BBK 9288 firmware probe and print the final CPU state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_build" / "python-deps"))
sys.path.insert(0, str(ROOT / "python"))

from qemu.machine import QEMUMachine  # noqa: E402


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path, nargs="?")
    parser.add_argument("--nand", type=Path)
    parser.add_argument(
        "--qemu",
        type=Path,
        default=ROOT / "_build" / "qemu-system-s1c33.exe",
    )
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument(
        "--key",
        action="append",
        help="QEMU sendkey name to inject one third of the way through the run",
    )
    parser.add_argument(
        "--hmp",
        action="append",
        default=[],
        help="human-monitor command to run and print at the end",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "_build" / "bbk9288-probe",
    )
    parser.add_argument("--trace-io", action="store_true")
    parser.add_argument("--trace-key-scan", action="store_true")
    args = parser.parse_args()

    qemu = args.qemu.resolve()
    if args.kernel is None and args.nand is None:
        parser.error("provide a kernel path, --nand, or both")
    kernel = args.kernel.resolve() if args.kernel is not None else None
    nand = args.nand.resolve() if args.nand is not None else None
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_log = output_dir / "probe.log"
    lcd_dump = output_dir / "probe.pgm"
    for path in (trace_log, lcd_dump):
        path.unlink(missing_ok=True)

    machine = (
        "bbk9288,"
        f"debug-lcd-dump-ms={max(1, int(args.seconds * 800))},"
        f"debug-lcd-dump-path={lcd_dump}"
    )
    if nand is not None:
        machine += f",nand-image={nand.as_posix()}"
    if args.trace_io:
        machine += ",trace-io=on"
    if args.trace_key_scan:
        machine += ",trace-key-scan=on"

    # The local UCRT64 build needs its runtime DLL directories on PATH.
    os.environ["PATH"] = (
        r"C:\msys64\ucrt64\bin;C:\msys64\usr\bin;"
        + os.environ.get("PATH", "")
    )

    qemu_args = [
        "-M",
        machine,
        "-cpu",
        "c33l05,exit-on-halt=off",
        "-serial",
        "none",
        "-d",
        "guest_errors,int",
        "-D",
        str(trace_log),
    ]
    if kernel is not None:
        qemu_args.extend(["-kernel", str(kernel)])

    vm = QEMUMachine(
        str(qemu),
        args=qemu_args,
        monitor_address=("127.0.0.1", free_local_port()),
        log_dir=str(output_dir),
        qmp_timer=10,
    )

    try:
        vm.launch()
        if args.key:
            interval = args.seconds / (len(args.key) + 2)
            time.sleep(interval)
            for command in args.key:
                vm.qmp(
                    "human-monitor-command",
                    {"command-line": f"sendkey {command}"},
                )
                time.sleep(interval)
            time.sleep(interval)
        else:
            time.sleep(args.seconds)
        if vm.is_running():
            for command in args.hmp:
                response = vm.qmp(
                    "human-monitor-command",
                    {"command-line": command},
                )
                print(json.dumps(response, ensure_ascii=False, indent=2))
            registers = vm.qmp(
                "human-monitor-command",
                {"command-line": "info registers"},
            )
            status = vm.qmp("query-status")
            print(json.dumps(registers, ensure_ascii=False, indent=2))
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print(f"QEMU exited early with status {vm.exitcode()}")
    finally:
        if vm.is_running():
            vm.shutdown()
        else:
            vm.wait()

    if trace_log.exists():
        print(f"trace: {trace_log} ({trace_log.stat().st_size} bytes)")
    if lcd_dump.exists():
        print(f"lcd:   {lcd_dump} ({lcd_dump.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
