import time
import secrets
from sqlalchemy import select, delete
from app.models import *
from app.security import password
from conftest import Client, submit, complete


def test_auth_csrf_logout_and_revocation(app,client):
    assert app.test_client().get('/api/auth/me').status_code == 401
    assert client.raw.post('/api/queries',json={}).status_code == 403
    assert client.get('/api/auth/me').json['data']['username'] == 'admin'
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    fresh=Client(app)
    with app.extensions['repo'].transaction() as db:
        db.get(User,1).enabled=False
    assert fresh.get('/api/auth/me').status_code == 401


def test_expired_session_and_password_reset(app,client):
    with app.extensions['repo'].transaction() as db:
        for session in db.scalars(select(AuthSession)):
            session.expires=time.time()-1
    assert client.get('/api/auth/me').status_code == 401
    fresh=Client(app)
    with app.extensions['repo'].transaction() as db:
        db.get(User,1).auth_epoch += 1
    assert fresh.get('/api/auth/me').status_code == 401


def test_login_rate_limit(app):
    raw=app.test_client()
    token=raw.get('/api/auth/csrf').json['data']['csrf_token']
    for _ in range(5):
        r=raw.post('/api/auth/login',json={'username':'no-user','password':'incorrect'},headers={'X-CSRF-Token':token})
        assert r.status_code == 401
    assert raw.post('/api/auth/login',json={'username':'no-user','password':'incorrect'},headers={'X-CSRF-Token':token}).status_code == 429
    with app.extensions['repo'].transaction() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.result=='FAILED')).all()) == 5


def test_lifecycle_immutable_history_and_copy(app,client):
    body={'name':'安全月报','sql':'SELECT record_id FROM approved_v WHERE d>=:start_date AND d<:end_date ORDER BY record_id',
          'schema':[{'name':'start_date','type':'date','required':True},{'name':'end_date','type':'date','required':True,'end_after':'start_date'}],
          'sort_fields':['record_id'],'summary':'v1'}
    response=client.post('/api/templates',body)
    assert response.status_code==201,response.json
    item=response.json['data'];tid=item['id']
    assert item['status']=='PUBLISHED' and item['published_version']==1
    assert 'scope_policy' not in item and 'validation' not in item
    assert any(t['id']==tid for t in client.get('/api/templates').json['data'])
    assert client.post(f'/api/templates/{tid}/publish',{}).status_code==404
    assert client.post(f'/api/templates/{tid}/submit',{}).status_code==404
    body.update(expected_version=1,summary='v2')
    assert client.request('PUT',f'/api/templates/{tid}',body).status_code==200
    assert client.request('PUT',f'/api/templates/{tid}',body).status_code==409
    history=client.get(f'/api/templates/{tid}/versions').json['data']
    assert len(history)==2 and history[1]['summary']=='v1'
    assert 'validation' not in history[0] and 'scope_policy' not in history[0]
    assert client.post('/api/templates',{'name':'copy','copy_from':tid}).status_code==201
    assert client.post(f'/api/templates/{tid}/disable').status_code==200
    assert client.request('DELETE',f'/api/templates/{tid}').status_code==200
    assert client.get(f'/api/templates/{tid}/versions').status_code==404
    from sqlalchemy.exc import IntegrityError
    import pytest
    with pytest.raises(IntegrityError):
        with app.extensions['repo'].transaction() as db:
            db.get(TemplateVersion,1).sql='changed'
    with pytest.raises(IntegrityError):
        with app.extensions['repo'].transaction() as db:
            db.execute(delete(AuditLog))


def test_query_pagination_sort_idor_and_template_revocation(app,client):
    group=submit(client)
    complete(app,group)
    tid=group['task_id']
    assert client.get('/api/queries/'+tid).json['data']['status']=='SUCCEEDED'
    page=client.get('/api/queries/'+tid+'/results?start=10&length=5&sort=record_id&direction=desc').json['data']
    assert len(page['rows'])==5 and page['rows'][0][0]==15
    assert set(r[1] for r in page['rows']) <= {'D001','D002'}
    assert client.get('/api/queries/'+tid+'/results?sort=record_id;DROP').status_code==400
    assert client.get('/api/queries/'+tid+'/results?length=999').status_code==400
    secret=secrets.token_urlsafe(18)
    r=client.post('/api/admin/users',{'username':'other','password':secret,'role_ids':[3],'scopes':['D001']})
    assert r.status_code==201
    other=Client(app,'other',secret)
    assert other.get('/api/queries/'+tid).status_code==403
    assert other.get('/api/queries/'+tid+'/results').status_code==403
    assert other.post('/api/exports',{'group_id':group['group_id']}).status_code==403
    assert other.get('/api/admin/users').status_code==403
    assert other.get('/pages/users').status_code==403
    assert other.post('/api/queries',{'template_id':1,'params':{}}).status_code==403
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(UserDataScope).where(UserDataScope.user_id==1))
    assert client.get('/api/queries/'+tid+'/results').status_code==200
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(TemplatePermission).where(TemplatePermission.template_id==1))
    assert client.get('/api/queries/'+tid+'/results').status_code==403


def test_department_is_not_a_query_filter_but_template_grants_remain_required(app,client):
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(UserDataScope).where(UserDataScope.user_id==1))
    request={'template_id':1,'params':{'start_date':'2024-01-01','end_date':'2024-02-01'}}
    assert client.post('/api/queries',request).status_code==202
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(TemplatePermission).where(TemplatePermission.template_id==1))
    assert client.post('/api/queries',request).status_code==403


def test_global_permissions_change_effective_immediately(app,client):
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(RolePermission).where(RolePermission.role_id==1,RolePermission.permission=='user:manage'))
    assert client.get('/api/admin/users').status_code==403


def test_users_roles_grants_settings_health_audit(app,client):
    r=client.post('/api/admin/roles',{'name':'CUSTOM'})
    assert r.status_code==200
    rid=r.json['data']['id']
    assert client.request('PUT',f'/api/admin/roles/{rid}/menus',{'menu_ids':['query']}).status_code==200
    assert client.post('/api/admin/scopes',{'code':'D003','name':'合成科室'}).status_code==201
    secret=secrets.token_urlsafe(18)
    uid=client.post('/api/admin/users',{'username':'queryuser','password':secret,'role_ids':[rid],'scopes':['D003']}).json['data']['id']
    assert client.post('/api/admin/grants',{'template_id':1,'role_id':rid,'execute':True,'view':True}).status_code==200
    other=Client(app,'queryuser',secret)
    assert len(other.get('/api/templates').json['data'])==1
    assert client.request('PUT',f'/api/admin/users/{uid}',{'enabled':False}).status_code==200
    assert other.get('/api/auth/me').status_code==401
    assert client.request('PUT','/api/admin/query-settings',{'MAX_MONTHS':48}).status_code==200
    assert client.get('/api/admin/query-settings').json['data']['MAX_MONTHS']==48
    assert client.request('PUT','/api/admin/settings',{'APP_SECRET':'unsafe'}).status_code==400
    assert client.get('/api/admin/health').json['data']['provider']['synthetic'] is True
    assert client.get('/api/admin/audits?action=user.update').json['data']['total']>0
    assert 'password_hash' not in str(client.get('/api/admin/users').json)
    assert client.get('/api/admin/grants').status_code==200


def test_retry_payload_is_private(app,client):
    group=submit(client,{'keyword':'合成样例'})
    complete(app,group)
    response=client.get('/api/queries/'+group['task_id'])
    assert '合成样例' not in str(response.json) and 'payload' not in response.json['data']
    assert client.post('/api/queries/'+group['task_id']+'/retry').status_code==202
    with app.extensions['repo'].transaction() as db:
        assert '合成样例' not in db.get(QueryTask,group['task_id']).payload


def test_pages_local_static_and_api_errors(app,client):
    import re
    for name in ['dashboard','query','templates','history','exports','users','roles','settings','audits']:
        r=client.get('/pages/'+name)
        assert r.status_code==200
        html=r.get_data(as_text=True)
        assert not re.search(r'(?:src|href)=["\']https?://',html)
        for path in re.findall(r'(?:src|href)=["\'](/static/[^"\']+)',html):
            assert client.get(path).status_code==200,path
    assert client.get('/').status_code==200
    assert client.get('/api/not-exist').json['success'] is False
    assert client.post('/api/queries').status_code==400
    assert client.get('/static/../data/metadata.db').status_code==404


def test_ten_users_login_and_isolation(app,client):
    for i in range(10):
        secret=secrets.token_urlsafe(18)
        response=client.post('/api/admin/users',{'username':'loaduser'+str(i),'password':secret,'role_ids':[3],'scopes':['D001']})
        uid=response.json['data']['id']
        assert client.post('/api/admin/grants',{'template_id':1,'user_id':uid,'execute':True,'view':True,'export':True}).status_code==200
        user=Client(app,'loaduser'+str(i),secret)
        assert user.get('/api/auth/me').json['data']['id']==uid
        assert user.get('/api/queries/history').json['data']['total']==0
