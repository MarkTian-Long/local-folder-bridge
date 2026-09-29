"""Explicit, local-user-initiated component installation from pinned/official sources."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import tempfile
import urllib.request
from urllib.parse import urlsplit
import zipfile
from .security import BridgeError

PDF_VERSION='6.18.1'
PDF_URL='https://files.pythonhosted.org/packages/58/13/645df3995075112cb3cce15e8797c205f0f88fb50acc11012b84b071bc22/pypdf-6.18.1-py3-none-any.whl'
PDF_SHA256='ee93a2665670ecf57ee81d197a4ca548f3dc15f9cefc56e59b8140866aaa3de5'
ALLOWED_HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com',
               'github-releases.githubusercontent.com','files.pythonhosted.org','www.python.org'}

def check_url(url: str):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise BridgeError('DOWNLOAD_ORIGIN','组件下载地址不在允许的官方域名内。')

class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        check_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url: str, limit=100*1024*1024) -> bytes:
    check_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'LocalFolderBridge/1.1','Accept':'application/json,application/octet-stream,*/*'})
    try:
        with urllib.request.build_opener(CheckedRedirect()).open(req,timeout=45) as r:
            parts=[]; size=0
            while True:
                b=r.read(256*1024)
                if not b: break
                size+=len(b)
                if size>limit: raise BridgeError('DOWNLOAD_LIMIT','组件下载超过大小限制。')
                parts.append(b)
        return b''.join(parts)
    except BridgeError: raise
    except Exception as exc:
        raise BridgeError('DOWNLOAD_FAILED','官方组件下载失败。请检查本机网络/代理，或按手册离线安装；不会切换到未知镜像。') from exc

def unpack(blob: bytes, dest: Path):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if len(z.infolist())>5000 or sum(i.file_size for i in z.infolist())>400*1024*1024:
            raise BridgeError('ARCHIVE_LIMIT','组件压缩包超出安全限制。')
        seen=set()
        for i in z.infolist():
            if i.filename.casefold() in seen: raise BridgeError('ARCHIVE_UNSAFE','组件包包含重复或大小写冲突的路径。')
            seen.add(i.filename.casefold())
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or (i.external_attr>>16)&0o170000 not in (0,0o040000,0o100000):
                raise BridgeError('ARCHIVE_UNSAFE','组件压缩包包含不安全路径或链接。')
        z.extractall(dest)

def install_pdf(app_dir: Path):
    blob=fetch(PDF_URL,5*1024*1024)
    if hashlib.sha256(blob).hexdigest()!=PDF_SHA256:
        raise BridgeError('HASH_MISMATCH','PDF 组件哈希与发布值不一致，已拒绝安装。')
    vendor=app_dir/'third_party'; vendor.mkdir(exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='pdf-stage-',dir=vendor))
    try:
        unpack(blob,staging)
        if not (staging/'pypdf'/'__init__.py').exists(): raise BridgeError('PACKAGE_INVALID','PDF 组件目录不完整。')
        target=vendor/'pypdf'
        if target.exists(): shutil.rmtree(target)
        shutil.move(str(staging/'pypdf'),str(target))
        for d in staging.glob('*.dist-info'):
            t=vendor/d.name
            if t.exists(): shutil.rmtree(t)
            shutil.move(str(d),str(t))
    finally: shutil.rmtree(staging,ignore_errors=True)
    return {'installed':True,'component':'pypdf','version':PDF_VERSION,'sha256':PDF_SHA256}

def install_tunnel(state_dir: Path):
    if os.name!='nt': raise BridgeError('WINDOWS_ONLY','自动下载功能针对 Windows。其他系统请手动选择官方 tunnel-client。')
    machine=(os.environ.get('PROCESSOR_ARCHITEW6432') or platform.machine()).lower()
    arch='arm64' if 'arm' in machine else 'amd64'
    meta=json.loads(fetch('https://api.github.com/repos/openai/tunnel-client/releases/latest',2*1024*1024))
    assets=meta.get('assets',[])
    options=[a for a in assets if re.fullmatch(r'tunnel-client-v[0-9]+\.[0-9]+\.[0-9]+-windows-'+arch+r'\.zip', a.get('name',''))]
    # Current releases include full-client, runtime-only and runtime-cloudflared flavors.
    # Only the full client implements doctor/init; do not count all three as ambiguous.
    if len(options)!=1: raise BridgeError('RELEASE_AMBIGUOUS','未找到唯一匹配的官方 Windows 压缩包，请从官方隧道页面下载后手动选择。')
    a=options[0]; checksum=''
    if re.fullmatch(r'sha256:[0-9a-fA-F]{64}',a.get('digest') or ''): checksum=a['digest'][7:].lower()
    if not checksum:
        sums=[x for x in assets if x.get('name','').lower() in ('sha256sums','sha256sums.txt','checksums.txt') or x.get('name','').lower().endswith('_checksums.txt')]
        if len(sums)==1:
            text=fetch(sums[0]['browser_download_url'],2*1024*1024).decode('utf-8')
            for line in text.splitlines():
                parts=line.split()
                if len(parts)==2 and parts[1].lstrip('*')==a['name'] and re.fullmatch('[0-9a-fA-F]{64}',parts[0]): checksum=parts[0].lower()
    if not checksum: raise BridgeError('NO_PUBLISHED_DIGEST','官方响应未提供可核验的 SHA-256，未自动安装。请手动核验官方分发包。')
    blob=fetch(a['browser_download_url'],200*1024*1024)
    if hashlib.sha256(blob).hexdigest()!=checksum: raise BridgeError('HASH_MISMATCH','隧道组件 SHA-256 不匹配，已拒绝安装。')
    parent=state_dir/'components'; parent.mkdir(exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='tunnel-',dir=parent))
    try:
        unpack(blob,staging)
        candidates=list(staging.rglob('tunnel-client.exe'))
        if len(candidates)!=1: raise BridgeError('PACKAGE_INVALID','官方包内未找到唯一 tunnel-client.exe。')
        binary=candidates[0]
        (staging/'SOURCE.json').write_text(json.dumps({'release':meta.get('tag_name'),'url':a['browser_download_url'],'sha256':checksum},indent=2),encoding='utf-8')
        return {'installed':True,'binary':str(binary),'release':meta.get('tag_name'),'sha256':checksum}
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise
