"""springer notifications: set up Slack once, test it, print its manifest, or turn it off.

The two tokens are typed at a hidden prompt and go straight to the OS keychain. They
are never written to a file, an argument, or a log. The daemon picks the settings up on
its next poll, so no restart is needed and no running session is lost.
"""

import getpass
import json
from pathlib import Path

from ..providers.secrets import KeyringSecrets
from .notifier import DEFAULTS, SETTINGS_FILE, load_settings, save_settings
from .slack import APP_TOKEN, BOT_TOKEN, MANIFEST, SECRET_SCOPE

STEPS = """Set up Slack for Springer. This takes about five minutes, once.

1. Open https://api.slack.com/apps, choose Create New App, then From a manifest.
   Pick the workspace, and paste the manifest printed below.
2. Install the app to the workspace.
3. OAuth & Permissions: copy the Bot User OAuth Token (starts with xoxb-).
4. Basic Information, App-Level Tokens: generate a token with the
   connections:write scope (starts with xapp-).
5. Your member ID: in Slack, open your profile, then the three dots, then
   Copy member ID (starts with U).

The manifest:
"""


def _ask_secret(prompt, prefix):
    value = getpass.getpass(prompt).strip()
    if not value.startswith(prefix):
        raise ValueError(f"that does not look like a token starting with {prefix}")
    return value


def _client(token):
    from slack_sdk import WebClient
    return WebClient(token=token)


def setup(home, secrets=None, ask=input, ask_secret=_ask_secret, client=_client):
    secrets = secrets or KeyringSecrets()
    print(STEPS + json.dumps(MANIFEST, indent=2) + "\n")
    try:
        bot = ask_secret("Bot token (xoxb-, hidden): ", "xoxb-")
        app = ask_secret("App-level token (xapp-, hidden): ", "xapp-")
    except ValueError as exc:
        print(f"Not saved: {exc}.")
        return 1
    user = ask("Your member ID (U...): ").strip()
    if not user.startswith(("U", "W")):
        print("Not saved: a member ID starts with U.")
        return 1
    web = client(bot)
    try:
        team = web.auth_test().get("team", "the workspace")
        web.chat_postMessage(channel=web.conversations_open(users=user)["channel"]["id"],
                             text="Springer is connected. Gates that need you will arrive here.")
    except Exception as exc:  # noqa: BLE001, any Slack refusal means nothing is saved
        print(f"Not saved: Slack refused the token or the member ID ({exc}).")
        return 1
    secrets.set(SECRET_SCOPE, BOT_TOKEN, bot)
    secrets.set(SECRET_SCOPE, APP_TOKEN, app)
    current = load_settings(home) or dict(DEFAULTS)
    save_settings(home, {**current, "slack": {"user": user}})
    print(f"Connected to {team}. Check your Slack direct messages for a note from springer.\n"
          f"Quiet hours {current['quiet_hours'][0]}:00 to {current['quiet_hours'][1]}:00 hold the digest only. "
          f"Change them in {Path(home) / SETTINGS_FILE}.")
    return 0


def test(home, secrets=None, client=_client):
    secrets = secrets or KeyringSecrets()
    settings = load_settings(home)
    bot = secrets.get(SECRET_SCOPE, BOT_TOKEN)
    if settings is None or not bot:
        print("Slack is not set up. Run: springer notifications setup")
        return 1
    web = client(bot)
    web.chat_postMessage(channel=web.conversations_open(users=settings["slack"]["user"])["channel"]["id"],
                         text="A test from springer.")
    print("Sent. Check your Slack direct messages.")
    return 0


def off(home, secrets=None):
    secrets = secrets or KeyringSecrets()
    path = Path(home) / SETTINGS_FILE
    if path.exists():
        path.unlink()
    secrets.delete(SECRET_SCOPE, BOT_TOKEN)
    secrets.delete(SECRET_SCOPE, APP_TOKEN)
    print("Slack is off. The tokens are removed from the keychain. Delete the app in Slack if you no longer want it.")
    return 0


def notifications(home, action):
    if action == "manifest":
        print(json.dumps(MANIFEST, indent=2))
        return 0
    if action == "test":
        return test(home)
    if action == "off":
        return off(home)
    return setup(home)
