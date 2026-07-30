#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end regression test for the BBK 9288 V1.5 machine."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_build" / "python-deps"))
sys.path.insert(0, str(ROOT / "python"))

from qemu.machine import QEMUMachine  # noqa: E402


logging.getLogger("qemu.machine.machine").setLevel(logging.ERROR)

NAND_SIZE = 276_824_064
FATAL_LOG_MARKERS = (
    "unimplemented opcode",
    "guest shutdown",
    "does not contain a readable",
    "NAND image",
)


class BBKQEMUMachine(QEMUMachine):
    """QEMUMachine with deterministic decoding for QEMU's UTF-8 log."""

    def _load_io_log(self) -> None:
        if self._qemu_log_path is not None:
            self._iolog = Path(self._qemu_log_path).read_text(
                encoding="utf-8",
                errors="replace",
            )


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def read_pnm(path: Path) -> tuple[int, int, int, bytes]:
    data = path.read_bytes()
    parts = data.split(maxsplit=4)
    if len(parts) != 5 or parts[0] not in (b"P5", b"P6"):
        raise AssertionError(f"{path} is not a binary PGM/PPM")
    width = int(parts[1])
    height = int(parts[2])
    maximum = int(parts[3])
    pixels = parts[4]
    channels = 1 if parts[0] == b"P5" else 3
    if maximum != 255 or len(pixels) != width * height * channels:
        raise AssertionError(f"{path} has an invalid PNM payload")
    return width, height, channels, pixels


def assert_lcd(path: Path) -> bytes:
    width, height, channels, pixels = read_pnm(path)
    if (width, height) != (320, 240):
        raise AssertionError(f"unexpected LCD size {width}x{height}")
    colors = {
        pixels[index:index + channels]
        for index in range(0, len(pixels), channels)
    }
    if len(colors) < 2:
        raise AssertionError("LCD framebuffer is blank")
    return pixels


def all_logs(directory: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in directory.glob("*.log")
    )


def assert_no_fatal_log(text: str) -> None:
    for marker in FATAL_LOG_MARKERS:
        if marker == "NAND image":
            if "has " in text and "bytes; expected" in text:
                raise AssertionError("NAND image size validation failed")
            continue
        if marker in text:
            raise AssertionError(f"fatal emulator log marker: {marker}")


def make_vm(
    qemu: Path,
    nand: Path,
    run_dir: Path,
    audio_player: Path | None,
) -> QEMUMachine:
    trace_log = run_dir / "trace.log"
    machine = f"bbk9288,nand-image={nand.as_posix()}"
    if audio_player is not None:
        machine += f",audio-player={audio_player.as_posix()}"
    args = [
        "-M", machine,
        "-cpu", "c33l05,exit-on-halt=off",
        "-display", "none",
        "-serial", "none",
        "-d", "guest_errors,int",
        "-D", str(trace_log),
    ]
    return BBKQEMUMachine(
        str(qemu),
        args=args,
        monitor_address=("127.0.0.1", free_local_port()),
        log_dir=str(run_dir),
        qmp_timer=15,
    )


def make_cpu_test_kernel(path: Path) -> None:
    base = 0x0200_0000
    entry_offset = 0x100
    int_handler_offset = 0x200
    debug_handler_offset = 0x220
    lhs_offset = 0x300
    rhs_offset = 0x310
    body = bytearray(0x400)

    struct.pack_into("<I", body, 0x00, base + entry_offset)
    struct.pack_into("<I", body, 0x30, base + int_handler_offset)
    struct.pack_into("<hh", body, lhs_offset, 2, 3)
    struct.pack_into("<hh", body, rhs_offset, 4, 5)

    def emit(offset: int, word: int) -> int:
        struct.pack_into("<H", body, offset, word)
        return offset + 2

    def load_imm(offset: int, reg: int, value: int) -> int:
        value &= 0xffff_ffff
        offset = emit(offset, 0xc000 | ((value >> 19) & 0x1fff))
        offset = emit(offset, 0xc000 | ((value >> 6) & 0x1fff))
        return emit(offset, 0x6c00 | ((value & 0x3f) << 4) | reg)

    pc = entry_offset
    pc = load_imm(pc, 10, base + debug_handler_offset)
    pc = load_imm(pc, 11, 0)
    pc = emit(pc, 0x3c00 | (11 << 4) | 10)  # ld.w [r11], r10

    pc = load_imm(pc, 1, 0x8844_2211)
    pc = emit(pc, 0x9600 | (1 << 4) | 4)  # mirror r4, r1

    pc = load_imm(pc, 0, 2)
    pc = load_imm(pc, 1, base + lhs_offset)
    pc = load_imm(pc, 2, base + rhs_offset)
    pc = load_imm(pc, 3, 0)
    pc = emit(pc, 0xa000 | (3 << 4) | 2)  # ld.w alr, r3
    pc = emit(pc, 0xa000 | (3 << 4) | 3)  # ld.w ahr, r3
    pc = emit(pc, 0xb200)                  # mac r0
    pc = emit(pc, 0xa400 | (2 << 4) | 5)  # ld.w r5, alr

    pc = emit(pc, 0x0480)                  # int 0
    pc = load_imm(pc, 7, 0x77)
    pc = emit(pc, 0x0400)                  # brk
    pc = load_imm(pc, 9, 0x99)
    emit(pc, 0x0080)                       # halt

    pc = int_handler_offset
    pc = load_imm(pc, 6, 0x66)
    emit(pc, 0x04c0)                       # reti

    pc = debug_handler_offset
    pc = load_imm(pc, 8, 0x55)
    emit(pc, 0x0440)                       # retd

    header = bytearray(0x40)
    header[0:4] = b"KNL "
    header[4:20] = b"CPU-REGRESSION\0\0"
    struct.pack_into("<I", header, 0x14, len(body))
    path.write_bytes(header + body)


def run_cpu_opcode_test(qemu: Path, run_dir: Path) -> None:
    kernel = run_dir / "cpu-opcodes.knl"
    make_cpu_test_kernel(kernel)
    vm = BBKQEMUMachine(
        str(qemu),
        args=[
            "-M", "bbk9288",
            "-cpu", "c33l05,exit-on-halt=off",
            "-kernel", str(kernel),
            "-display", "none",
            "-serial", "none",
            "-d", "guest_errors,int",
            "-D", str(run_dir / "trace.log"),
        ],
        monitor_address=("127.0.0.1", free_local_port()),
        log_dir=str(run_dir),
        qmp_timer=10,
    )
    try:
        vm.launch()
        time.sleep(1)
        response = vm.cmd(
            "human-monitor-command",
            command_line="info registers",
        )
        registers = {
            name: int(value, 16)
            for name, value in re.findall(
                r"\b(r(?:1[0-5]|[0-9]))\s*=0x([0-9a-fA-F]+)",
                response,
            )
        }
        special = {
            name: int(value, 16)
            for name, value in re.findall(
                r"\b(alr|ahr)\s*=0x([0-9a-fA-F]+)",
                response,
            )
        }
        expected = {
            "r0": 0,
            "r1": 0x0200_0304,
            "r2": 0x0200_0314,
            "r4": 0x1122_4488,
            "r5": 23,
            "r6": 0x66,
            "r7": 0x77,
            "r8": 0x55,
            "r9": 0x99,
        }
        for name, value in expected.items():
            if registers.get(name) != value:
                raise AssertionError(
                    f"CPU opcode test {name}: "
                    f"got {registers.get(name)!r}, expected 0x{value:08x}"
                )
        if special.get("alr") != 23 or special.get("ahr") != 0:
            raise AssertionError(f"MAC accumulator mismatch: {special}")
    finally:
        if vm.is_running():
            vm.shutdown()
        elif vm.exitcode() is not None:
            vm.wait()
    assert_no_fatal_log(all_logs(run_dir))


def run_first_pass(
    qemu: Path,
    nand: Path,
    run_dir: Path,
    seconds: float,
    audio_player: Path | None,
) -> None:
    vm = make_vm(qemu, nand, run_dir, audio_player)
    screenshots: list[bytes] = []
    start = time.monotonic()
    try:
        vm.launch()
        time.sleep(min(4.5, seconds * 0.6))
        status = vm.cmd("query-status")
        if not status.get("running"):
            raise AssertionError(f"QEMU did not reach running state: {status}")

        before = run_dir / "before.pgm"
        vm.cmd("screendump", filename=str(before))
        screenshots.append(assert_lcd(before))

        for index, key in enumerate(("ret", "down", "ret", "f11"), start=1):
            vm.cmd(
                "human-monitor-command",
                command_line=f"sendkey {key} 180",
            )
            time.sleep(0.8)
            shot = run_dir / f"key-{index}-{key}.pgm"
            vm.cmd("screendump", filename=str(shot))
            screenshots.append(assert_lcd(shot))

        remaining = seconds - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(remaining)
        if not vm.is_running():
            raise AssertionError(f"QEMU exited early with {vm.exitcode()}")
    finally:
        if vm.is_running():
            # Deliberately bypass the exit notifier. Periodic NAND syncing
            # must leave an image that the second pass can boot.
            vm.kill()
        elif vm.exitcode() is not None:
            vm.wait()

def run_reboot_pass(
    qemu: Path,
    nand: Path,
    run_dir: Path,
    seconds: float,
) -> None:
    vm = make_vm(qemu, nand, run_dir, None)
    try:
        vm.launch()
        time.sleep(seconds)
        status = vm.cmd("query-status")
        if not status.get("running"):
            raise AssertionError(
                f"reboot did not reach running state: {status}"
            )
        shot = run_dir / "reboot.pgm"
        vm.cmd("screendump", filename=str(shot))
        assert_lcd(shot)
    finally:
        if vm.is_running():
            vm.shutdown()
        elif vm.exitcode() is not None:
            vm.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nand", type=Path, required=True)
    parser.add_argument(
        "--qemu",
        type=Path,
        default=ROOT / "_build" / "qemu-system-s1c33.exe",
    )
    parser.add_argument("--audio-player", type=Path)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "_build" / "bbk9288-regression",
    )
    parser.add_argument("--keep-test-nand", action="store_true")
    args = parser.parse_args()

    qemu = args.qemu.resolve()
    source_nand = args.nand.resolve()
    output_dir = args.output_dir.resolve()
    audio_player = (
        args.audio_player.resolve() if args.audio_player is not None else None
    )
    if not qemu.is_file():
        parser.error(f"QEMU executable not found: {qemu}")
    if not source_nand.is_file() or source_nand.stat().st_size != NAND_SIZE:
        parser.error(f"expected a {NAND_SIZE}-byte raw NAND image")
    if audio_player is not None and not audio_player.is_file():
        parser.error(f"audio player not found: {audio_player}")
    if args.seconds < 5:
        parser.error("--seconds must be at least 5")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    first_dir = output_dir / "first-pass"
    reboot_dir = output_dir / "reboot-pass"
    cpu_dir = output_dir / "cpu-opcodes"
    first_dir.mkdir(parents=True)
    reboot_dir.mkdir(parents=True)
    cpu_dir.mkdir(parents=True)
    test_nand = output_dir / "nand-test.raw"
    shutil.copyfile(source_nand, test_nand)
    original_mtime = test_nand.stat().st_mtime_ns

    if os.name == "nt":
        msys_paths = [
            Path(r"C:\msys64\ucrt64\bin"),
            Path(r"C:\msys64\usr\bin"),
        ]
        available = [str(path) for path in msys_paths if path.is_dir()]
        if available:
            os.environ["PATH"] = os.pathsep.join(
                available + [os.environ.get("PATH", "")]
            )

    run_cpu_opcode_test(qemu, cpu_dir)
    run_first_pass(
        qemu, test_nand, first_dir, args.seconds, audio_player
    )
    if test_nand.stat().st_size != NAND_SIZE:
        raise AssertionError("hard termination changed the NAND image size")
    if test_nand.stat().st_mtime_ns == original_mtime:
        raise AssertionError(
            "guest NAND writes were not persisted periodically"
        )
    first_logs = all_logs(first_dir)
    assert_no_fatal_log(first_logs)
    if "bbk9288s-nand: program=" not in first_logs:
        raise AssertionError("firmware did not exercise NAND page programming")
    if first_logs.count("wake line low by keyboard") < 4:
        raise AssertionError("keyboard events did not reach the board matrix")
    if audio_player is not None and "audio player:" not in first_logs:
        raise AssertionError("host audio player process was not started")

    run_reboot_pass(
        qemu, test_nand, reboot_dir, max(4.0, args.seconds / 2)
    )
    assert_no_fatal_log(all_logs(reboot_dir))

    if not args.keep_test_nand:
        test_nand.unlink()
    print("PASS: INT, RETD, MIRROR, and MAC CPU opcode checks")
    print("PASS: V1.5 boot, LCD, keyboard, NAND hard-exit recovery, reboot")
    if audio_player is not None:
        print("PASS: host audio player process was configured")
    print(f"artifacts: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
