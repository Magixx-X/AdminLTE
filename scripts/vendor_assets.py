"""Update only dependency bugfixes, retaining official AdminLTE 3.2 unchanged."""
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent.parent
PACKAGES={
    'jquery':('3.7.1',{'dist/jquery.min.js':'jquery/jquery.min.js'},'LICENSE.txt'),
    'bootstrap':('4.6.2',{'dist/js/bootstrap.bundle.min.js':'bootstrap/js/bootstrap.bundle.min.js'},'LICENSE'),
    'datatables.net':('1.13.11',{'js/jquery.dataTables.min.js':'datatables/jquery.dataTables.min.js'},'License.txt'),
    'datatables.net-bs4':('1.13.11',{'js/dataTables.bootstrap4.min.js':'datatables-bs4/js/dataTables.bootstrap4.min.js','css/dataTables.bootstrap4.min.css':'datatables-bs4/css/dataTables.bootstrap4.min.css'},'License.txt'),
    'codemirror':('5.65.20',{'lib/codemirror.js':'codemirror/codemirror.js','lib/codemirror.css':'codemirror/codemirror.css','mode/sql/sql.js':'codemirror/mode/sql/sql.js'},'LICENSE'),
}


if __name__=='__main__':
    records=[]
    for name,(version,mapping,license_file) in PACKAGES.items():
        url=f'https://registry.npmjs.org/{name}/-/{name}-{version}.tgz'
        with urlopen(url,timeout=60) as response:
            raw=response.read()
        record={'name':name,'version':version,'source':url,'archive_sha256':hashlib.sha256(raw).hexdigest(),'files':[]}
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            for origin,destination in mapping.items():
                data=archive.extractfile('package/'+origin).read()
                path=ROOT/'app/static/vendor'/destination
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
                record['files'].append({'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(data).hexdigest()})
            (ROOT/'docs/licenses'/f'{name}-{version}.txt').write_bytes(archive.extractfile('package/'+license_file).read())
        records.append(record)
    records.append({'name':'admin-lte','version':'3.2.0','source':'https://github.com/ColorlibHQ/AdminLTE/tree/v3.2.0'})
    (ROOT/'docs/frontend-assets.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Local assets pinned:',', '.join(f'{name}@{item[0]}' for name,item in PACKAGES.items()))
