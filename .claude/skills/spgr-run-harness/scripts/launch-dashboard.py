#!/usr/bin/env python3
"""Open the live run dashboard in a separate terminal window, best effort.

Called by the run-harness skill when a run starts or resumes. The dashboard
is opt-in: nothing launches unless the developer sets SPGR_DASHBOARD=1.
Exits 0 in every case so a launch failure can never block a run. A no-op
when a dashboard process is already watching the run, or when the platform
has no known way to open a terminal window, in which case it prints the
manual command instead.

Usage: python3 launch-dashboard.py <run-dir>
"""

import os
import subprocess
import sys


def already_watching(run_dir):
    run_id = os.path.basename(os.path.abspath(run_dir).rstrip("/"))
    try:
        out = subprocess.run(
            ["pgrep", "-fl", "run-dashboard.py"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(run_id in line or run_dir in line for line in out.splitlines())


def main():
    if len(sys.argv) != 2:
        print("usage: launch-dashboard.py <run-dir>")
        return
    run_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(run_dir):
        print(f"launch-dashboard: no such run directory {run_dir}, skipping")
        return
    if os.environ.get("SPGR_DASHBOARD", "").lower() not in ("1", "true", "yes"):
        print("launch-dashboard: dashboard is opt-in, set SPGR_DASHBOARD=1 to enable")
        return
    if already_watching(run_dir):
        print(f"launch-dashboard: a dashboard is already watching {run_dir}")
        return

    dashboard = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-dashboard.py")
    command = f'python3 "{dashboard}" "{run_dir}"'

    if sys.platform == "darwin":
        escaped = command.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "Terminal"\n'
            f'  do script "{escaped}"\n'
            "  activate\n"
            "end tell"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, timeout=15
            )
            if result.returncode == 0:
                print(f"launch-dashboard: opened dashboard for {run_dir}")
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole"):
            try:
                subprocess.Popen(
                    [terminal, "-e", f"python3 {dashboard} {run_dir}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print(f"launch-dashboard: opened dashboard for {run_dir}")
                return
            except OSError:
                continue

    print(f"launch-dashboard: could not open a terminal window. Run manually: {command}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"launch-dashboard: skipped ({exc})")
    sys.exit(0)
