import pytest
from datetime import datetime
from app.security import AppError
from app.services.parameters import months, month_bounds, parse_params, validate_schema, oracle_binds
from app.models import TemplateVersion


def test_months_cross_year_leap_and_over_twelve():
    assert months('2023-12', '2024-02', 36) == ['2023-12','2024-01','2024-02']
    assert len(months('2023-01','2024-03',36)) == 15
    start, end = month_bounds('2024-02')
    assert (end-start).days == 29
    assert month_bounds('2025-02')[1] == datetime(2025,3,1)


@pytest.mark.parametrize('start,end', [('2024-03','2024-02'),('2024-1','2024-02'),('2024-13','2024-13'),('9999-12','9999-12'),('2020-01','2026-12'),(None,None)])
def test_invalid_months(start,end):
    with pytest.raises(AppError):
        months(start,end,36)


@pytest.mark.parametrize('params', [{},{'a':'x'},{'b':2},{'a':'x','b':2}])
def test_independent_optional(params):
    schema = [{'name':'a','type':'string'},{'name':'b','type':'integer'}]
    parsed = parse_params(schema,params)
    assert parsed['a'] == params.get('a')
    assert parsed['b'] == params.get('b')


@pytest.mark.parametrize('kind,value', [('integer','1.5'),('integer',True),('integer',2**65),('decimal','nan'),('date','2023-02-29'),('datetime','2024-01-01'),('month','2024-1'),('boolean','yes'),('string',['x']),('select','invalid'),('multiselect',['invalid'])])
def test_invalid_types(kind,value):
    with pytest.raises(AppError):
        parse_params([{'name':'p','type':kind,'choices':['ok']}],{'p':value})


def test_all_types_and_bind_safety():
    schema = [{'name':'n','type':'integer'},{'name':'money','type':'decimal'},{'name':'d','type':'date'},
              {'name':'dt','type':'datetime'},{'name':'m','type':'month'},{'name':'flag','type':'boolean'},
              {'name':'pick','type':'select','choices':['x']},{'name':'many','type':'multiselect','choices':["x' OR 1=1 --",'y']}]
    params = parse_params(schema,{'n':'4','money':'1.25','d':'2024-02-29','dt':'2024-02-29T10:30','m':'2024-02','flag':'false','pick':'x','many':["x' OR 1=1 --"]})
    version = TemplateVersion(sql='SELECT * FROM v WHERE dep=:scope_department AND dt>=:begin_time AND dt<:end_time AND id IN (:many) AND n=:n AND flag=:flag',schema=schema)
    sql,binds = oracle_binds(version,params,'2024-02','D001')
    assert "OR 1=1" not in sql and binds['many_0'] == "x' OR 1=1 --"
    assert binds['end_time'] == datetime(2024,3,1) and binds['flag'] == 0


def test_date_range_and_unknown_parameter():
    schema=[{'name':'begin','type':'date'},{'name':'end','type':'date','end_after':'begin'}]
    with pytest.raises(AppError):
        parse_params(schema,{'begin':'2024-02-29','end':'2024-02-29'})
    with pytest.raises(AppError):
        parse_params([],{'sql':'DROP TABLE patients'})


def test_schema_rejects_bad_policy_and_identifiers():
    for fields in [['id DESC; DROP X'],['a.b']]:
        with pytest.raises(AppError):
            validate_schema([],fields,{'kind':'department_bind'},':scope_department :begin_time :end_time')
    with pytest.raises(AppError):
        validate_schema([{'name':'scope_department','type':'string'}],[],{'kind':'department_bind'},'')
