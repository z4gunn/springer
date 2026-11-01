"""The springer command: the TUI, and for now the daemon. Onboarding lands later."""

import argparse
import sys
import time
from pathlib import Path


def serve(home, port):
    """Run the daemon on the loopback interface. The mock provider is the only one
    until step 6, so this serves a canned run and spends no tokens."""
    import uvicorn

    from .api.app import create_app
    from .daemon import Daemon
    from .providers.mock import MockProvider, MockSourceHost
    from .providers.mock_scenario import demo_planner_factory, demo_script
    from .providers.secrets import KeyringSecrets

    daemon = Daemon(home, MockProvider(demo_script()), MockSourceHost(), demo_planner_factory(), KeyringSecrets(), time.time)
    app = create_app(daemon)
    daemon.home.write_port(port)
    daemon.start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def open_tui(home):
    """Open the TUI on a running daemon. Onboarding will start the daemon as a service."""
    from .tui.app import SpringerApp
    from .tui.client import ApiClient

    try:
        client = ApiClient.from_home(home)
    except (OSError, KeyError, ValueError):
        sys.stderr.write(f"springer: no daemon found under {home}. Start one with `springer daemon`.\n")
        return 1
    SpringerApp(client).run()
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["daemon"]:
        parser = argparse.ArgumentParser(prog="springer daemon")
        parser.add_argument("--home", default=str(Path.home() / ".springer"))
        parser.add_argument("--port", type=int, default=7337)
        args = parser.parse_args(argv[1:])
        return serve(args.home, args.port)
    return open_tui(Path.home() / ".springer" if not argv else Path(argv[0]))


if __name__ == "__main__":
    sys.exit(main())
