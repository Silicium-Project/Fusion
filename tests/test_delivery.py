"""Host-side validation is pure/testable; these tests never mutate Docker or host services."""
import io, json, tarfile
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import pytest
spec=spec_from_file_location('delivery',Path(__file__).resolve().parents[1]/'infra/delivery/apply.py')
delivery=module_from_spec(spec);spec.loader.exec_module(delivery)

@pytest.mark.parametrize('name',['/etc/passwd','../wallet','a/../../wallet'])
def test_archives_cannot_escape(tmp_path,name):
    file=tmp_path/'bad.tar.gz'
    with tarfile.open(file,'w:gz')as t:
        member=tarfile.TarInfo(name);member.size=1;t.addfile(member,io.BytesIO(b'x'))
    with pytest.raises(ValueError):delivery.extract(file,tmp_path/'out')

def test_archive_links_are_rejected(tmp_path):
    file=tmp_path/'bad.tar.gz'
    with tarfile.open(file,'w:gz')as t:
        member=tarfile.TarInfo('link');member.type=tarfile.SYMTYPE;member.linkname='/etc';t.addfile(member)
    with pytest.raises(ValueError):delivery.extract(file,tmp_path/'out')

def test_activation_preserves_an_existing_download_directory(tmp_path):
    link=tmp_path/'downloads';link.mkdir();(link/'user-file').write_text('keep')
    with pytest.raises(RuntimeError):delivery.switch_link(link,tmp_path/'candidate')
    assert (link/'user-file').read_text()=='keep'

def test_candidate_identity_is_not_a_mutable_tag(tmp_path,monkeypatch):
    monkeypatch.setattr(delivery,'execute',lambda args:'')
    source='a'*40
    m={'schema_version':1,'channel':'dev','source_sha':source,'version':'0.3.0-dev.1','release_id':'dev-0.3.0-dev.1-'+source[:12],
       'components':{n:{'image':'ghcr.io/silicium-project/'+n+'@sha256:'+'b'*64}for n in ['api','web','network']},'assets':[]}
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='Incomplete'):delivery.verify_manifest(tmp_path,'dev',tmp_path/'keyring')
    m['components']['api']['image']='api:latest';(tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='immutable'):delivery.verify_manifest(tmp_path,'dev',tmp_path/'keyring')


def test_private_ingress_requires_an_assigned_vpn_address():
    assert not delivery.vpn_has_address([])
    assert not delivery.vpn_has_address([{'addr_info':[{'local':'192.168.1.28'}]}])
    assert delivery.vpn_has_address([{'addr_info':[{'local':'10.77.0.1'}]}])
