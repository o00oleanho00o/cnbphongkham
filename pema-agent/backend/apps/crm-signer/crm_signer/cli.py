"""``crm-signer keygen`` makes the key once; ``crm-signer serve`` runs the service
(docs/PLAN-crm-plugin.md 3.9)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn

from crm_signer import keys
from crm_signer.app import create_app

DEFAULT_KEY_FILE = "/keys/crm-signer-ed25519.pem"
DEFAULT_UPSTREAM = "http://api:8000/api/v1/agent-gateway"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crm-signer")
    parser.add_argument("--key-file", default=os.environ.get("CRM_SIGNER_KEY_FILE", DEFAULT_KEY_FILE))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("keygen", help="make the private key (once) and print the public key for the CRM")
    serve = sub.add_parser("serve", help="run the service")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104  # inside the stack's internal network
    serve.add_argument("--port", type=int, default=int(os.environ.get("CRM_SIGNER_PORT", "8090")))
    serve.add_argument("--upstream", default=os.environ.get("CRM_SIGNER_UPSTREAM", DEFAULT_UPSTREAM))
    args = parser.parse_args(argv)
    path = Path(args.key_file)

    if args.command == "keygen":
        try:
            made = keys.generate(path)
        except FileExistsError:
            sys.stderr.write(f"{path} already exists; a key in use is never replaced.\n")
            return 1
        sys.stdout.write(f"PEMA_AGENT_GATEWAY_PUBLIC_KEYS={made.x}\n")
        return 0

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        key = keys.load(path)
    except (OSError, ValueError) as err:
        sys.stderr.write(f"no usable key at {path} ({type(err).__name__}); run `crm-signer keygen` first.\n")
        return 1
    uvicorn.run(create_app(key, args.upstream), host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
