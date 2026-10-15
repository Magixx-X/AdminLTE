import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def backup(data_dir, destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    target = root / ('metadata-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.db')
    with sqlite3.connect(Path(data_dir) / 'metadata.db') as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('备份完整性校验失败')
    return target
