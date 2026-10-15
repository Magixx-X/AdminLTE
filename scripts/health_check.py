import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.config import configuration
from app.repositories import Repository
from app.models import Setting

if __name__ == '__main__':
    config=configuration()
    repo=Repository(config['DATABASE_URL'])
    with repo.transaction() as db:
        heartbeat=db.get(Setting,'worker_heartbeat')
        alive=bool(heartbeat and time.time()-heartbeat.value['timestamp']<20)
    print(json.dumps({'metadata':'OK','source':config['DATA_SOURCE'],'worker_alive':alive,
        'oracle_live_check':'Use authenticated /api/admin/health; CLI does not open an extra Oracle pool',
        'hospital_validation':'PENDING_HOSPITAL_VALIDATION'},ensure_ascii=False))
    repo.engine.dispose()
    sys.exit(0 if alive else 1)
