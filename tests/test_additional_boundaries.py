import secrets
import time
from sqlalchemy import select,delete
from app.models import QueryTask,ExportRecord,TemplatePermission,UserDataScope,User
from conftest import submit,complete,Client


def test_scope_is_server_owned_and_revoked_exports_are_denied(app,client):
    group=submit(client,{'month_end':'2024-02'})
    complete(app,group)
    eid=client.post('/api/exports',{'group_id':group['group_id']}).json['data']['id']
    worker=app.extensions['test_worker']
    worker.claim(ExportRecord)
    worker.execute_export(eid)
    secret=secrets.token_urlsafe(18)
    uid=client.post('/api/admin/users',{'username':'outsider','password':secret,'role_ids':[3],'scopes':['D001']}).json['data']['id']
    other=Client(app,'outsider',secret)
    assert other.get('/api/exports/'+eid+'/download').status_code==403
    assert other.request('DELETE','/api/exports/'+eid).status_code==403
    assert client.post('/api/queries',{'template_id':1,'params':{'month_start':'2024-01','month_end':'2024-01','scope_department':'D999'}}).status_code==400
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(TemplatePermission).where(TemplatePermission.template_id==1))
    assert client.get('/api/exports/'+eid+'/download').status_code==403


def test_worker_rechecks_disabled_user(app,client):
    group=submit(client,{'month_end':'2024-02'})
    worker=app.extensions['test_worker']
    worker.claim(QueryTask)
    with app.extensions['repo'].transaction() as db:
        db.get(User,1).enabled=False
    worker.execute_query(group['task_id'])
    with app.extensions['repo'].transaction() as db:
        task=db.get(QueryTask,group['task_id'])
        assert task.status=='FAILED' and task.error_code=='PERMISSION_REVOKED'


def test_empty_results_and_export(app,client):
    group=submit(client,{'month_end':'2024-02','keyword':'不存在的合成词'})
    complete(app,group)
    assert client.get('/api/queries/'+group['task_id']+'/results').json['data']['rows']==[]
    record=client.post('/api/exports',{'group_id':group['group_id']}).json['data']
    worker=app.extensions['test_worker']
    worker.claim(ExportRecord)
    worker.execute_export(record['id'])
    assert client.get('/api/exports/'+record['id']).json['data']['status']=='SUCCEEDED'


def test_invalid_ids_are_400(client):
    assert client.post('/api/queries',{'template_id':[],'params':{}}).status_code==400
    assert client.get('/api/queries/history?user_id=bad').status_code==400
    assert client.post('/api/admin/grants',{'template_id':1,'user_id':[]}).status_code==400


def test_restore_uses_backup_api(app,tmp_path):
    import sqlite3,subprocess,sys,os
    from pathlib import Path
    from app.services.backup import backup
    from app.config import ROOT
    saved=backup(app.config['DATA_DIR'],tmp_path/'saved')
    with app.extensions['repo'].transaction() as db:
        db.get(User,1).enabled=False
    app.extensions['repo'].engine.dispose()
    env=dict(os.environ,DATA_DIR=app.config['DATA_DIR'],EXPORT_DIR=app.config['EXPORT_DIR'],LOG_DIR=app.config['LOG_DIR'],APP_SECRET=app.config['SECRET_KEY'],APP_ENV='development',DATA_SOURCE='mock')
    result=subprocess.run([sys.executable,str(ROOT/'scripts/restore_sqlite.py'),str(saved),'--services-stopped'],cwd=ROOT,env=env,capture_output=True)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    with sqlite3.connect(Path(app.config['DATA_DIR'])/'metadata.db') as db:
        assert db.execute('SELECT enabled FROM users WHERE id=1').fetchone()[0]==1


def test_export_size_quota_and_interruption_temp_cleanup(app,client):
    from pathlib import Path
    group=submit(client,{'month_end':'2024-02'})
    complete(app,group)
    app.config['MAX_EXPORT_BYTES']=1024
    eid=client.post('/api/exports',{'group_id':group['group_id']}).json['data']['id']
    worker=app.extensions['test_worker']
    worker.claim(ExportRecord)
    worker.execute_export(eid)
    record=client.get('/api/exports/'+eid).json['data']
    assert record['status']=='FAILED' and '大小配额' in record['error']
    temp=Path(app.config['EXPORT_DIR'])/'temp'/'openpyxl.interrupted'
    temp.write_text('SYNTHETIC_ONLY',encoding='ascii')
    partial=Path(app.config['EXPORT_DIR'])/'fake.part'
    partial.write_text('SYNTHETIC_ONLY',encoding='ascii')
    worker.recover()
    assert not temp.exists() and not partial.exists()
