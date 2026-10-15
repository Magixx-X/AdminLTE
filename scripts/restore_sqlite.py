import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.config import configuration
from app.services.backup import backup

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='停服后恢复元数据库（必须另行恢复原 APP_SECRET）')
    parser.add_argument('backup_file')
    parser.add_argument('--services-stopped',action='store_true',required=True)
    args=parser.parse_args()
    config=configuration()
    target=Path(config['DATA_DIR'])/'metadata.db'
    source=Path(args.backup_file).resolve()
    if source==target.resolve() or not source.is_file():
        raise SystemExit('备份路径无效')
    with sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise SystemExit('备份完整性校验失败')
        if target.exists():
            print('恢复前备份：',backup(config['DATA_DIR'],Path(config['DATA_DIR'])/'backups'))
        with sqlite3.connect(target) as dest:
            db.backup(dest)
    print('恢复完成；启动 Worker 会标记遗留 RUNNING 为 INTERRUPTED。')
