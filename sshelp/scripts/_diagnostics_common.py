#!/usr/bin/env python3
"""Shared read-only remote process and resource diagnostics."""

from __future__ import annotations

import base64
import json
import subprocess
from typing import Any

from _ssh_common import SSHOptions, SkillError, build_ssh_command, shell_quote, ssh_failure


REMOTE_DIAGNOSTICS_HELPER = r'''
import json
import os
import re
import subprocess
import sys
import time

JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

def command(argv, timeout=15):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except FileNotFoundError:
        return {"available": False, "argv0": argv[0], "returncode": None, "stdout": "", "stderr": "not installed"}
    except subprocess.TimeoutExpired:
        return {"available": True, "argv0": argv[0], "returncode": None, "stdout": "", "stderr": "timed out"}
    return {"available": True, "argv0": argv[0], "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

def ps_rows():
    result = command(["ps", "-eo", "uid=,pid=,ppid=,stat=,pcpu=,rss=,etimes=,comm=,args="], 20)
    if not result["available"] or result["returncode"] != 0:
        return []
    rows = []
    for line in result["stdout"].splitlines():
        fields = line.strip().split(None, 8)
        if len(fields) < 8:
            continue
        if len(fields) == 8:
            fields.append(fields[7])
        uid, pid, ppid, state, cpu, rss, elapsed, comm, args = fields
        try:
            row = {
                "uid": int(uid),
                "pid": int(pid),
                "ppid": int(ppid),
                "state": state,
                "cpu_percent": float(cpu),
                "rss_bytes": int(rss) * 1024,
                "elapsed_seconds": int(elapsed),
                "command": comm,
                "args": args[:2000],
            }
        except ValueError:
            continue
        rows.append(row)
    return rows

def proc_detail(row):
    pid = row["pid"]
    try:
        row["wchan"] = open(f"/proc/{pid}/wchan", "r", encoding="utf-8", errors="replace").read().strip() or None
    except OSError:
        row["wchan"] = None
    try:
        io_values = {}
        with open(f"/proc/{pid}/io", "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                key, separator, value = line.partition(":")
                if separator and value.strip().isdigit():
                    io_values[key] = int(value.strip())
        row["io"] = {
            "read_bytes": io_values.get("read_bytes"),
            "write_bytes": io_values.get("write_bytes"),
            "syscr": io_values.get("syscr"),
            "syscw": io_values.get("syscw"),
        }
    except OSError:
        row["io"] = None
    return row

def process_tree(root_pid, detailed=True):
    rows = ps_rows()
    by_parent = {}
    by_pid = {}
    for row in rows:
        by_pid[row["pid"]] = row
        by_parent.setdefault(row["ppid"], []).append(row)
    selected = []
    queue = [root_pid]
    seen = set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        row = by_pid.get(pid)
        if row is not None:
            selected.append(proc_detail(row) if detailed else row)
        queue.extend(child["pid"] for child in by_parent.get(pid, []))
    return selected

def job_info(job_id):
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError("invalid job id")
    session = None
    for candidate in ("sshelp-" + job_id, "srd-" + job_id):
        if command(["tmux", "has-session", "-t", candidate])["returncode"] == 0:
            session = candidate
            break
    if session is None:
        return {"job_id": job_id, "session": session, "state": "missing", "pid": None}
    status = command([
        "tmux", "display-message", "-p", "-t", session + ":0.0",
        "#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}|#{pane_pid}|#{pane_current_command}|#{pane_tty}"
    ])
    if status["returncode"] != 0:
        raise ValueError("could not inspect tmux pane")
    fields = status["stdout"].strip().split("|", 5)
    if len(fields) != 6:
        raise ValueError("unexpected tmux pane response")
    dead, exit_code, signal, pid, current, tty = fields
    return {
        "job_id": job_id,
        "session": session,
        "state": "exited" if dead == "1" else "running",
        "pid": int(pid) if pid.isdigit() else None,
        "exit_code": int(exit_code) if exit_code.lstrip("-").isdigit() else None,
        "signal": int(signal) if signal.isdigit() else (signal or None),
        "command": current or None,
        "tty": tty or None,
    }

def memory_snapshot():
    values = {}
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            for line in handle:
                key, _, raw = line.partition(":")
                amount = raw.strip().split()[0]
                if amount.isdigit():
                    values[key] = int(amount) * 1024
    except OSError:
        pass
    return {
        "total_bytes": values.get("MemTotal"),
        "available_bytes": values.get("MemAvailable"),
        "free_bytes": values.get("MemFree"),
        "swap_total_bytes": values.get("SwapTotal"),
        "swap_free_bytes": values.get("SwapFree"),
    }

def disk_snapshot(path):
    if not path.startswith("/") or "\x00" in path:
        raise ValueError("disk path must be absolute")
    resolved = os.path.realpath(path)
    info = os.statvfs(resolved)
    return {
        "path": resolved,
        "total_bytes": info.f_blocks * info.f_frsize,
        "available_bytes": info.f_bavail * info.f_frsize,
        "free_bytes": info.f_bfree * info.f_frsize,
    }

def gpu_data():
    gpu_result = command([
        "nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits"
    ], 20)
    if not gpu_result["available"]:
        return {"available": False, "gpus": [], "processes": []}
    if gpu_result["returncode"] != 0:
        return {"available": True, "healthy": False, "error": gpu_result["stderr"][-1000:], "gpus": [], "processes": []}
    gpus = []
    for line in gpu_result["stdout"].splitlines():
        fields = [value.strip() for value in line.split(",")]
        if len(fields) != 6:
            continue
        index, name, utilization, used, total, temperature = fields
        gpus.append({
            "index": int(index), "name": name,
            "utilization_percent": float(utilization),
            "memory_used_mib": float(used), "memory_total_mib": float(total),
            "temperature_c": float(temperature),
        })
    proc_result = command(["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"], 20)
    processes = []
    if proc_result["returncode"] == 0:
        for line in proc_result["stdout"].splitlines():
            fields = [value.strip() for value in line.split(",", 2)]
            if len(fields) == 3 and fields[0].isdigit():
                used = None if fields[2] in ("[N/A]", "N/A") else float(fields[2])
                processes.append({"pid": int(fields[0]), "process_name": fields[1], "memory_used_mib": used})
    return {"available": True, "healthy": True, "gpus": gpus, "processes": processes}

def process_list(payload):
    pattern = payload.get("pattern")
    maximum = payload["max_results"]
    values = [
        row for row in ps_rows()
        if row["uid"] == os.getuid()
        and row["pid"] != os.getpid()
        and "base64;exec(base64.b64decode" not in row["args"]
    ]
    if pattern:
        lowered = pattern.lower()
        values = [row for row in values if lowered in row["args"].lower()]
    values.sort(key=lambda row: (-row["cpu_percent"], -row["rss_bytes"], row["pid"]))
    return {"processes": values[:maximum], "truncated": len(values) > maximum}

def process_inspect(payload):
    job = job_info(payload["job_id"])
    tree = process_tree(job["pid"]) if job["pid"] is not None and job["state"] == "running" else []
    return {"job": job, "process_tree": tree}

def resource_snapshot(payload):
    result = {
        "load_average": list(os.getloadavg()),
        "memory": memory_snapshot(),
        "disk": disk_snapshot(payload.get("path") or "/"),
    }
    job_id = payload.get("job_id")
    if job_id:
        job = job_info(job_id)
        tree = process_tree(job["pid"], detailed=False) if job["pid"] is not None and job["state"] == "running" else []
        result["job"] = job
        result["job_resources"] = {
            "cpu_percent": sum(row["cpu_percent"] for row in tree),
            "rss_bytes": sum(row["rss_bytes"] for row in tree),
            "process_count": len(tree),
        }
    return result

def port_owner(payload):
    port = int(payload["port"])
    result = command(["ss", "-H", "-ltnup"], 20)
    if not result["available"]:
        return {"available": False, "port": port, "listeners": []}
    listeners = []
    for line in result["stdout"].splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        local = fields[4]
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        listeners.append({
            "protocol": fields[0],
            "state": fields[1],
            "local_address": local,
            "peer_address": fields[5] if len(fields) > 5 else None,
            "pids": [int(value) for value in re.findall(r"pid=(\d+)", line)],
            "raw": line[:2000],
        })
    return {"available": True, "port": port, "listeners": listeners, "stderr": result["stderr"][-1000:]}

def diagnose(payload):
    job = job_info(payload["job_id"])
    output_path = os.path.expanduser("~/.sshelp/jobs/" + payload["job_id"] + "/output.ansi")
    if not os.path.isfile(output_path):
        output_path = os.path.expanduser("~/.ssh-research-debug/jobs/" + payload["job_id"] + "/output.ansi")
    output = {"path": output_path, "exists": False, "size": None, "mtime_ns": None, "idle_seconds": None}
    try:
        info = os.stat(output_path)
        output.update({"exists": True, "size": info.st_size, "mtime_ns": info.st_mtime_ns, "idle_seconds": max(0.0, time.time() - info.st_mtime)})
    except OSError:
        pass
    tree = process_tree(job["pid"]) if job["pid"] is not None and job["state"] == "running" else []
    total_cpu = sum(row["cpu_percent"] for row in tree)
    total_rss = sum(row["rss_bytes"] for row in tree)
    states = [row["state"] for row in tree]
    wchans = [row.get("wchan") for row in tree if row.get("wchan")]
    gpu = gpu_data()
    pids = {row["pid"] for row in tree}
    gpu_processes = [row for row in gpu.get("processes", []) if row["pid"] in pids]
    idle = output["idle_seconds"]
    waiting_for_input = any(value in ("n_tty_read", "tty_read") for value in wchans)
    idle_sleep = any(value == "hrtimer_nanosleep" for value in wchans)
    io_blocked = any(value.startswith("D") for value in states)
    network_wait = any("sock" in value or "unix" in value or "inet" in value for value in wchans)
    possible_waiting = waiting_for_input
    recommendations = []
    if job["state"] == "missing":
        recommendations.append("verify_host_and_job_id")
    elif job["state"] == "exited":
        recommendations.append("drain_remaining_output_and_report_exit")
    elif io_blocked:
        recommendations.append("inspect_disk_or_network_io")
    elif possible_waiting:
        recommendations.append("inspect_recent_terminal_output_for_prompt")
    elif idle_sleep:
        recommendations.append("continue_waiting_for_timer")
    elif total_cpu >= 1.0 or gpu_processes:
        recommendations.append("continue_waiting")
    else:
        recommendations.append("recheck_after_a_longer_interval")
    return {
        "job": job,
        "output": output,
        "process_tree": tree,
        "cpu_percent": total_cpu,
        "rss_bytes": total_rss,
        "cpu_active": total_cpu >= 1.0,
        "gpu_active": bool(gpu_processes),
        "gpu_host_active": any(item.get("utilization_percent", 0) >= 1.0 for item in gpu.get("gpus", [])),
        "gpu_processes": gpu_processes,
        "possible_waiting_for_input": possible_waiting,
        "possible_idle_sleep": idle_sleep,
        "possible_io_blocked": io_blocked,
        "possible_network_wait": network_wait,
        "wait_channels": sorted(set(wchans)),
        "recommendations": recommendations,
    }

def main():
    try:
        payload = json.load(sys.stdin)
        operation = payload.pop("operation")
        handlers = {
            "process_list": process_list,
            "process_inspect": process_inspect,
            "resource_snapshot": resource_snapshot,
            "port_owner": port_owner,
            "gpu_snapshot": lambda payload: gpu_data(),
            "job_diagnose": diagnose,
        }
        result = handlers[operation](payload)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": {"code": "DIAGNOSTIC_FAILED", "message": str(exc), "details": {}}}, ensure_ascii=False))
        sys.exit(1)

main()
'''


def run_remote_diagnostics(
    options: SSHOptions,
    host: str,
    operation: str,
    payload: dict[str, Any],
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    encoded = base64.b64encode(REMOTE_DIAGNOSTICS_HELPER.encode("utf-8")).decode("ascii")
    launcher = f"import base64;exec(base64.b64decode({encoded!r}))"
    command = build_ssh_command(options, host, f"python3 -c {shell_quote(launcher)}")
    body = json.dumps({"operation": operation, **payload}, ensure_ascii=False).encode("utf-8")
    try:
        result = subprocess.run(
            command,
            input=body,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("SSH_NOT_FOUND", f"SSH executable not found: {options.ssh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError("DIAGNOSTIC_TIMEOUT", "remote diagnostic operation timed out") from exc
    try:
        response = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        if result.returncode != 0:
            raise ssh_failure(result, "DIAGNOSTIC_FAILED", "remote diagnostic operation failed")
        raise SkillError("INVALID_DIAGNOSTIC_RESPONSE", "remote diagnostic helper returned invalid JSON")
    if not response.get("ok"):
        error = response.get("error", {})
        raise SkillError(
            error.get("code", "DIAGNOSTIC_FAILED"),
            error.get("message", "remote diagnostic operation failed"),
            error.get("details") or {},
        )
    if result.returncode != 0:
        raise ssh_failure(result, "DIAGNOSTIC_FAILED", "remote diagnostic operation failed")
    return response
