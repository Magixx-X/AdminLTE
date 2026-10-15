import pytest


@pytest.mark.parametrize('item', ['thick_19c_oracle_11204_nls_lob_functions', 'real_business_sql_baselines',
    'oracle_timeout_cancel_readonly_grants', 'two_queries_ten_users_large_export_reconnect',
    'win7_minimum_chrome_iframe_datatables_codemirror', 'iis_tls_acl_service_backup_restore'])
def test_hospital_acceptance(item):
    pytest.skip('PENDING_HOSPITAL_VALIDATION: ' + item)
