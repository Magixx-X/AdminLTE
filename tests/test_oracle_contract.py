"""Driver-double tests ONLY. They do not validate Oracle 11g, SQL semantics or real cancellation."""
from types import SimpleNamespace
from datetime import datetime
import pytest
import oracledb
from app.providers.oracle import OracleProvider


class Cursor:
    def __init__(self,trace):
        self.trace=trace
        self.description=[('RECORD_ID',),('DEPARTMENT',)]
        self.fetched=False
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def execute(self,sql,binds=None):
        self.trace.append((sql,binds))
    def fetchone(self):
        return (1,)
    def fetchmany(self,count):
        if self.fetched:
            return []
        self.fetched=True
        return [(1,'D001')]


class Connection:
    version='DRIVER_DOUBLE_NOT_REAL_ORACLE'
    def __init__(self,trace):
        self.trace=trace
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def cursor(self):
        return Cursor(self.trace)
    def rollback(self):
        self.trace.append(('ROLLBACK',None))
    def cancel(self):
        self.trace.append(('CANCEL',None))


@pytest.mark.parametrize('role,max_pool', [('web',1),('worker',3)])
def test_driver_contract_thick_readonly_binding_pool(monkeypatch,role,max_pool):
    trace=[]
    monkeypatch.setattr(oracledb,'init_oracle_client',lambda **kw:trace.append(('INIT',kw)))
    monkeypatch.setattr(oracledb,'is_thin_mode',lambda:False)
    def create_pool(**kw):
        trace.append(('POOL',kw))
        return SimpleNamespace(acquire=lambda:Connection(trace))
    monkeypatch.setattr(oracledb,'create_pool',create_pool)
    config=dict(ORACLE_USER='FAKE_TEST_USER',ORACLE_PASSWORD='FAKE_TEST_SECRET',ORACLE_DSN='FAKE_NO_NETWORK',
                ORACLE_CLIENT_DIR='FAKE_NOT_INSTALLED',ORACLE_POOL_MAX=4,PROCESS_ROLE=role,MAX_CELL_CHARS=4000)
    provider=OracleProvider(config)
    version=SimpleNamespace(validation='HOSPITAL_VALIDATED',reviewed_at='FAKE_DRIVER_TEST',
        sql='WITH t AS (SELECT * FROM approved WHERE department=:scope_department AND d>=:begin_time AND d<:end_time) SELECT * FROM t WHERE name=:name',
        schema=[{'name':'name','type':'string'}])
    assert len(list(provider.rows(version,{'name':"x' OR 1=1 --"},'2024-02',['D001'],lambda:False,1)))==1
    assert any(sql=='SET TRANSACTION READ ONLY' for sql,_ in trace)
    query=[entry for entry in trace if entry[0].startswith('WITH')][0]
    assert 'OR 1=1' not in query[0]
    assert query[1]['name']=="x' OR 1=1 --" and query[1]['end_time']==datetime(2024,3,1)
    assert [args['max'] for sql,args in trace if sql=='POOL']==[max_pool]
    assert trace[-1][0]=='ROLLBACK'
    version.validation='PENDING_HOSPITAL_VALIDATION'
    with pytest.raises(RuntimeError,match='PENDING_HOSPITAL_VALIDATION'):
        list(provider.rows(version,{},'2024-02',['D001'],lambda:False,1))
