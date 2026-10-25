#!/usr/bin/env python3
"""Sign the exact final manifest with the existing release authority."""
import os,tempfile
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('repos',Path(__file__).with_name('package-repositories.py'));m=module_from_spec(spec);spec.loader.exec_module(m)
if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('Protected GitHub signing job required')
with tempfile.TemporaryDirectory(prefix='silicium-release-sign-') as home:
    home=Path(home)/'gpg';key=m.import_key(home,'RELEASE_SIGNING')
    file=m.ROOT/'.artifacts/publish/manifest.json';m.sign(home,key,file)
    m.command(['gpg','--homedir',str(home),'--verify',str(file)+'.asc',str(file)])
