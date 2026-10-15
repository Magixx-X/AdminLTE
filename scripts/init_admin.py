import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        app.cli.main(args=['init-admin'] + sys.argv[1:])
