"""The springer command. Onboarding and the TUI land here in later steps."""

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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["daemon"]:
        parser = argparse.ArgumentParser(prog="springer daemon")
        parser.add_argument("--home", default=str(Path.home() / ".springer"))
        parser.add_argument("--port", type=int, default=7337)
        args = parser.parse_args(argv[1:])
        return serve(args.home, args.port)
    sys.stderr.write("springer: the harness is under construction. Only `springer daemon` runs.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
