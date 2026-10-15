import re
from datetime import date, datetime
from openpyxl.cell import WriteOnlyCell


def sheet_name(month, part=1):
    month = '查询结果' if month == 'result' else month
    suffix = '' if part == 1 else '_' + str(part)
    return re.sub(r'[\\/*?:\[\]]', '_', month)[:31 - len(suffix)] + suffix


def safe_cell(sheet, value):
    if isinstance(value, str):
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)[:32767]
        if value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
            value = "'" + value
    cell = WriteOnlyCell(sheet, value=value)
    if isinstance(value, datetime):
        if value.tzinfo:
            cell.value = value.replace(tzinfo=None)
        cell.number_format = 'yyyy-mm-dd hh:mm:ss'
    elif isinstance(value, date):
        cell.number_format = 'yyyy-mm-dd'
    return cell
