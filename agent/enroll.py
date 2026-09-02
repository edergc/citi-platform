"""One-time enrollment: exchanges a CITI Core enrollment token for a persistent agent credential.

Usage: python enroll.py --core-url http://127.0.0.1:8010 --server-id <uuid> --token <token>
"""

import argparse
import json
from pathlib import Path

import httpx

CONFIG_PATH = Path(__file__).parent / "agent_config.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-url", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    response = httpx.post(
        f"{args.core_url}/api/v1/agents/enroll",
        json={"server_id": args.server_id, "token": args.token},
        trust_env=False,
    )
    response.raise_for_status()
    data = response.json()

    CONFIG_PATH.write_text(
        json.dumps(
            {"core_url": args.core_url, "agent_id": data["agent_id"], "agent_token": data["agent_token"]},
            indent=2,
        )
    )
    print(f"Enrolado correctamente. Config guardada en {CONFIG_PATH}")


if __name__ == "__main__":
    main()
