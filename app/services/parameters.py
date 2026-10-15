import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from app.security import AppError

IDENT = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,29}$')
RESERVED = {'hqs_lo', 'hqs_hi'}
TYPES = {'string', 'integer', 'decimal', 'date', 'datetime', 'month', 'select', 'multiselect', 'boolean'}


def sql_bindings(sql):
    text = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/", ' ', sql, flags=re.S)
    return set(re.findall(r'(?<!:):([A-Za-z][A-Za-z0-9_]*)', text))


def date_range(schema):
    pairs = [s for s in schema if s.get('end_after') and s.get('split_by_month') is not False]
    explicit = [s for s in pairs if s.get('split_by_month') is True]
    if len(explicit) > 1:
        raise AppError('SCHEMA', '只能指定一个按月拆分的日期范围')
    end = explicit[0] if explicit else pairs[0] if len(pairs) == 1 else None
    return (next(s for s in schema if s['name'] == end['end_after']), end) if end else None


def validate_schema(schema, sort_fields, sql):
    if not isinstance(schema, list) or len(schema) > 30:
        raise AppError('SCHEMA', '参数 schema 必须是最多 30 项的数组')
    names = set()
    for spec in schema:
        if not isinstance(spec, dict):
            raise AppError('SCHEMA', '每个参数必须为对象')
        name = spec.get('name', '')
        if not IDENT.fullmatch(name) or name in names or name in RESERVED:
            raise AppError('SCHEMA', '参数名重复、非法或使用了保留名称')
        names.add(name)
        if spec.get('type') not in TYPES or not isinstance(spec.get('required', False), bool):
            raise AppError('SCHEMA', '参数类型或 required 无效')
        if spec['type'] in ('select', 'multiselect'):
            choices = spec.get('choices', [])
            if not isinstance(choices, list) or not choices or len(choices) > 100 or any(not isinstance(x, str) for x in choices):
                raise AppError('SCHEMA', '枚举选项必须为非空字符串数组')
        if not isinstance(spec.get('max_length', 200), int) or not 1 <= spec.get('max_length', 200) <= 4000:
            raise AppError('SCHEMA', 'max_length 应为 1–4000')
        if not isinstance(spec.get('label', name), str) or len(spec.get('label', name)) > 120:
            raise AppError('SCHEMA', '参数标签无效')
        for bound in ('min', 'max'):
            if bound in spec:
                try:
                    numeric = Decimal(str(spec[bound]))
                    if not numeric.is_finite():
                        raise ValueError()
                except (InvalidOperation, ValueError):
                    raise AppError('SCHEMA', '参数数值边界无效')
        if 'default' in spec:
            parse_params([dict(spec, required=False)], {name: spec['default']})
    for spec in schema:
        if spec.get('end_after'):
            start = next((s for s in schema if s['name'] == spec['end_after']), None)
            if not start or spec['type'] not in ('date', 'datetime', 'month') or start['type'] != spec['type'] or start is spec:
                raise AppError('SCHEMA', 'end_after 必须引用另一个同类型日期参数')
        if 'split_by_month' in spec and (type(spec['split_by_month']) is not bool or not spec.get('end_after')):
            raise AppError('SCHEMA', 'split_by_month 必须是日期范围结束参数上的布尔值')
        if spec['type'] == 'multiselect' and any(re.fullmatch(re.escape(spec['name']) + r'_\d+', name) for name in names):
            raise AppError('SCHEMA', '多选绑定名与已有参数冲突')
    if not isinstance(sort_fields, list) or len(sort_fields) > 20 or any(not isinstance(x, str) or not IDENT.fullmatch(x) for x in sort_fields):
        raise AppError('SORT', '排序白名单只能包含合法的英文字段名')
    date_range(schema)
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 100000:
        raise AppError('SQL', 'SQL 不能为空或过长')
    missing = sql_bindings(sql) - names
    if missing:
        raise AppError('SQL_BIND', '请在参数定义中声明 SQL 绑定变量：' + '、'.join(sorted(missing)))
    return schema


def months(start, end, maximum):
    try:
        first = datetime.strptime(start, '%Y-%m').date()
        last = datetime.strptime(end, '%Y-%m').date()
        if first.strftime('%Y-%m') != start or last.strftime('%Y-%m') != end:
            raise ValueError()
        count = (last.year - first.year) * 12 + last.month - first.month + 1
        if count < 1 or count > maximum:
            raise ValueError()
        values = []
        for index in range(count):
            year, month0 = divmod(first.year * 12 + first.month - 1 + index, 12)
            if year >= 9999:
                raise ValueError()
            values.append(f'{year:04d}-{month0 + 1:02d}')
        return values
    except (ValueError, TypeError):
        raise AppError('MONTH_RANGE', f'月份范围无效，最多 {maximum} 个月')


def month_bounds(value):
    first = datetime.strptime(value, '%Y-%m')
    year, month0 = divmod(first.year * 12 + first.month, 12)
    return first, datetime(year, month0 + 1, 1)


def parse_params(schema, supplied):
    if not isinstance(supplied, dict):
        raise AppError('PARAMETERS', 'params 必须是对象')
    allowed = {s['name'] for s in schema} | {'month_start', 'month_end'}
    if set(supplied) - allowed:
        raise AppError('PARAMETERS', '包含未经定义的参数')
    output = {}
    for spec in schema:
        name, kind = spec['name'], spec['type']
        value = supplied.get(name, spec.get('default'))
        if value is None or value == '' or value == []:
            if spec.get('required'):
                raise AppError('PARAMETERS', f'请填写 {spec.get("label", name)}')
            output[name] = None
            continue
        try:
            if kind == 'integer':
                if isinstance(value, bool) or not re.fullmatch(r'-?\d+', str(value)):
                    raise ValueError()
                value = int(value)
                if abs(value) > 2 ** 63 - 1:
                    raise ValueError()
            elif kind == 'decimal':
                value = Decimal(str(value))
                if not value.is_finite() or abs(value) > Decimal('1e30'):
                    raise ValueError()
                value = str(value)
            elif kind in ('date', 'datetime', 'month'):
                pattern = {'date': '%Y-%m-%d', 'datetime': '%Y-%m-%dT%H:%M', 'month': '%Y-%m'}[kind]
                parsed = datetime.strptime(value, pattern)
                if parsed.strftime(pattern) != value:
                    raise ValueError()
            elif kind == 'boolean':
                if value not in (True, False, 0, 1, 'true', 'false'):
                    raise ValueError()
                value = value in (True, 1, 'true')
            elif kind == 'multiselect':
                if not isinstance(value, list) or len(value) > 100 or any(x not in spec['choices'] for x in value):
                    raise ValueError()
                value = list(dict.fromkeys(value))
            else:
                if not isinstance(value, str) or len(value) > spec.get('max_length', 200):
                    raise ValueError()
                if kind == 'select' and value not in spec['choices']:
                    raise ValueError()
            if kind in ('integer', 'decimal'):
                numeric = Decimal(str(value))
                if 'min' in spec and numeric < Decimal(str(spec['min'])) or 'max' in spec and numeric > Decimal(str(spec['max'])):
                    raise ValueError()
            output[name] = value
        except (ValueError, TypeError, InvalidOperation):
            raise AppError('PARAMETERS', f'参数 {name} 类型、长度或范围无效')
    for spec in schema:
        other = spec.get('end_after')
        if other and output.get(spec['name']) and output.get(other) and output[spec['name']] <= output[other]:
            raise AppError('DATE_RANGE', '结束时间必须晚于开始时间（排他边界）')
    return output


def query_plan(schema, supplied, maximum):
    values = dict(supplied) if isinstance(supplied, dict) else supplied
    pair = date_range(schema)
    names = {s['name'] for s in schema}
    legacy = isinstance(values, dict) and 'month_start' not in names and ('month_start' in values or 'month_end' in values)
    if legacy and pair:
        first, last = values.pop('month_start', None), values.pop('month_end', None)
        periods = months(first, last, maximum)
        fmt = {'date': '%Y-%m-%d', 'datetime': '%Y-%m-%dT%H:%M', 'month': '%Y-%m'}[pair[0]['type']]
        values.setdefault(pair[0]['name'], month_bounds(periods[0])[0].strftime(fmt))
        values.setdefault(pair[1]['name'], month_bounds(periods[-1])[1].strftime(fmt))
    parsed = parse_params(schema, values)
    if pair and parsed.get(pair[0]['name']) and parsed.get(pair[1]['name']):
        fmt = {'date': '%Y-%m-%d', 'datetime': '%Y-%m-%dT%H:%M', 'month': '%Y-%m'}[pair[0]['type']]
        cursor = datetime.strptime(parsed[pair[0]['name']], fmt)
        end = datetime.strptime(parsed[pair[1]['name']], fmt)
        plan = []
        while cursor < end:
            try:
                stop = min(month_bounds(cursor.strftime('%Y-%m'))[1], end)
            except ValueError:
                raise AppError('DATE_RANGE', '日期范围超出支持年份') from None
            chunk = dict(parsed, **{pair[0]['name']: cursor.strftime(fmt), pair[1]['name']: stop.strftime(fmt)})
            plan.append((cursor.strftime('%Y-%m'), chunk))
            if len(plan) > maximum:
                raise AppError('MONTH_RANGE', f'日期范围最多跨 {maximum} 个月')
            cursor = stop
        return plan
    if legacy:
        return [(m, dict(parsed)) for m in months(supplied.get('month_start'), supplied.get('month_end'), maximum)]
    return [('result', parsed)]


def oracle_binds(version, params, month):
    binds = {}
    sql = version.sql
    names = sql_bindings(sql)
    for spec in version.schema:
        name, value = spec['name'], params.get(spec['name'])
        if name not in names:
            continue
        if spec['type'] == 'multiselect':
            # SQL uses :name as an IN-list placeholder, e.g. IN (:equipment).
            slots = []
            for index, item in enumerate(value or [None]):
                key = f'{name}_{index}'
                slots.append(':' + key)
                binds[key] = item
            sql = re.sub(':' + re.escape(name) + r'\b', ','.join(slots), sql)
        else:
            if value is not None and spec['type'] in ('date', 'datetime', 'month'):
                value = datetime.strptime(value, {'date': '%Y-%m-%d', 'datetime': '%Y-%m-%dT%H:%M', 'month': '%Y-%m'}[spec['type']])
            if value is not None and spec['type'] == 'decimal':
                value = Decimal(value)
            if value is not None and spec['type'] == 'boolean':
                value = int(value)
            if name in names:
                binds[name] = value
    # Read old monthly task payloads without exposing the removed month controls.
    legacy = names - {s['name'] for s in version.schema}
    if legacy <= {'begin_time', 'end_time'} and legacy and re.fullmatch(r'\d{4}-\d{2}', month):
        begin, end = month_bounds(month)
        binds.update({k: v for k, v in {'begin_time': begin, 'end_time': end}.items() if k in legacy})
    elif legacy:
        raise AppError('SQL_BIND', '旧模板存在未定义参数，请编辑 SQL 和参数定义后重新保存：' + '、'.join(sorted(legacy)))
    return sql, binds
