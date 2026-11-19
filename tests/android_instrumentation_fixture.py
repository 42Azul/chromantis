"""Run an index-only HTTPS fixture and prepare test-APK assets, never app assets."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from android_fixture import open_fixture


def interrupt(*_):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = Path(args.config)
    config.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        with open_fixture(args.cert, args.key, index_only=True) as (server, _, _, invite):
            config.write_text(json.dumps({
                'origin': 'https://10.0.2.2:8443',
                'code': invite,
                'certificate': Path(args.cert).read_text(),
            }))
            print('Synthetic index-only HTTPS fixture ready.', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        config.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
