import time
from datetime import datetime
from app.providers.base import QueryProvider, QueryCancelled, QueryTimeout


class MockProvider(QueryProvider):
    def health(self):
        return {'source': 'mock', 'status': 'OK', 'synthetic': True}

    def rows(self, version, params, month, scopes, stop, timeout):
        if (getattr(version, 'scope_policy', None) or {}).get('kind') == 'all':
            scopes = ['全院合成']
        started = time.monotonic()
        scenario = params.get('scenario', 'normal')
        if scenario == 'failure':
            raise RuntimeError('MOCK_QUERY_FAILURE')
        count = int(params.get('sample_rows') or 240)
        for index in range(count):
            if scenario in ('slow', 'timeout'):
                time.sleep(.03 if scenario == 'slow' else .1)
            if stop():
                raise QueryCancelled()
            if time.monotonic() - started > timeout:
                raise QueryTimeout()
            department = scopes[index % len(scopes)]
            equipment = ('CT', 'MRI', '超声')[index % 3]
            if params.get('equipment') and equipment not in params['equipment']:
                continue
            if params.get('keyword') and params['keyword'] not in '合成样例':
                continue
            yield ['record_id', 'department', 'patient_label', 'equipment', 'amount', 'visit_time'], (
                index + 1, department, f'合成样例-{index + 1:05d}', equipment,
                round(100 + index * .25, 2), datetime.strptime(month + '-01', '%Y-%m-%d'))
