"""Run an index-only HTTPS fixture and prepare test-APK assets, never app assets."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from threading import Thread

from android_fixture import open_fixture
from chromantis.app import ApplicationService
from chromantis.db.repository import Repository


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
            with open_fixture(args.cert, args.key, port=8444, beach_photos=59) as (ui_server, ui_db, _, ui_invite):
                _, launcher_invite = ApplicationService(Repository(ui_db)).family_access.invite(
                    "Android launcher fixture"
                )
                worker = Thread(target=ui_server.serve_forever, daemon=True)
                worker.start()
                config.write_text(json.dumps({
                    'origin': 'https://10.0.2.2:8443',
                    'code': invite,
                    'ui_origin': 'https://10.0.2.2:8444',
                    'ui_code': ui_invite,
                    'launcher_code': launcher_invite,
                    'certificate': Path(args.cert).read_text(),
                }))
                print('Synthetic index-only and visual HTTPS fixtures ready.', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    ui_server.shutdown()
                    worker.join(timeout=5)
    finally:
        config.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
