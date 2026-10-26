import base64,hashlib,json,subprocess
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import pytest
spec=spec_from_file_location('updater',Path(__file__).resolve().parents[1]/'tools/ci/update-manifest.py');updater=module_from_spec(spec);spec.loader.exec_module(updater)

def test_disposable_key_signs_the_installed_client_payload(tmp_path,monkeypatch):
    private=subprocess.run(['openssl','genpkey','-algorithm','ed25519'],capture_output=True,check=True).stdout
    key=tmp_path/'private.pem';key.write_bytes(private)
    public=subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-outform','DER'],capture_output=True,check=True).stdout[-32:]
    trust={'key_id':hashlib.sha256(public).hexdigest(),'public_key_base64':base64.b64encode(public).decode()}
    monkeypatch.setenv('UPDATE_SIGNING_KEY',private.decode())
    for name in ['silicium-node-windows-dev.exe','silicium-node-linux-dev.AppImage']:(tmp_path/name).write_bytes(b'fixture only')
    identity={'channel':'dev','version':'0.3.0-dev.1','source_sha':'a'*40}
    result=updater.build(tmp_path,identity,'https://10.77.0.1:8443/downloads/snapshots/test',trust)
    assert len(result['releases'])==2
    assert result['releases'][0]['signing_key_id']==trust['key_id']
    assert updater.payload(result['releases'][0]).endswith(b'\n')
    assert 'fixture only'not in json.dumps(result)
    with pytest.raises(RuntimeError,match='trust anchor mismatch'):updater.build(tmp_path,identity,'https://example.invalid',{'key_id':'0'*64,'public_key_base64':trust['public_key_base64']})

def test_missing_updater_key_cannot_generate_a_replacement(tmp_path,monkeypatch):
    monkeypatch.delenv('UPDATE_SIGNING_KEY',raising=False)
    with pytest.raises(RuntimeError,match='existing'):updater.build(tmp_path,{},'',{})
