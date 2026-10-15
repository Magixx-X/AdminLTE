import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.config import configuration
from app.services.backup import backup

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',default='backups')
    args=parser.parse_args()
    print(backup(configuration()['DATA_DIR'],args.destination))
