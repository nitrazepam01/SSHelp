#!/usr/bin/env python3
"""Discard one exact local checkout transaction."""

from __future__ import annotations

import argparse

from _remote_files_common import add_checkout_root_argument, load_manifest, remove_checkout
from _ssh_common import JsonArgumentParser, invoke


def parse_args() -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    add_checkout_root_argument(parser)
    return parser.parse_args()


def run() -> dict[str, object]:
    args = parse_args()
    load_manifest(args.checkout_root, args.checkout, require_ready=False)
    remove_checkout(args.checkout_root, args.checkout)
    return {"checkout_id": args.checkout, "local_checkout_removed": True}


if __name__ == "__main__":
    invoke(run)
