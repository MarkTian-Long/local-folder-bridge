"""Supervises the official OpenAI tunnel-client as a foreground child process."""
from __future__ import annotations
from collections import deque
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import urllib.request
from urllib.parse import urlsplit
from .security import BridgeError
from .windows import protect_secret, unprotect_secret

class Tunnel:
    def __init__(self, store, mcp_url: str, mcp_token: str):
        self.store=store; self.mcp_url=mcp_url; self.mcp_token=mcp_token
        self.process=None; self.logs=deque(maxlen=80); self.key=''; self.doctor_text=''
        self.lock=threading.RLock()
        self.health_file=store.directory/'tunnel-health.url'
        self.profile=store.directory/'tunnel-profile.yaml'
        self.secret_file=store.directory/'runtime-key.dpapi'

    def save(self, binary: str, tunnel_id: str, key: str='', remember: bool=False):
        with self.lock:
            if self.process and self.process.poll() is None: raise BridgeError('TUNNEL_RUNNING','请先停止隧道再修改配置。')
            p=Path(binary).expanduser().absolute()
            if p.name.lower() not in ('tunnel-client.exe','tunnel-client') or not p.is_file():
                raise BridgeError('BINARY_INVALID','请选择官方 tunnel-client.exe 文件，而非文件夹、压缩包或其他程序。')
            if not re.fullmatch(r'tunnel_[0-9a-f]{32}',tunnel_id.strip()):
                raise BridgeError('TUNNEL_ID_INVALID','Tunnel ID 应为 tunnel_ 加 32 位小写十六进制字符；不是 App ID 或 Version ID。')
            if key.strip(): self.key=key.strip()
            if self.key and (len(self.key)>4096 or '\n' in self.key): raise BridgeError('KEY_INVALID','密钥格式不正确。')
            if remember:
                if not self.key: raise BridgeError('KEY_REQUIRED','请先输入运行时密钥。')
                self.secret_file.write_bytes(protect_secret(self.key))
            elif self.secret_file.exists(): self.secret_file.unlink()
            self.store.set('tunnel',{'binary':str(p),'tunnel_id':tunnel_id.strip(),'remember':remember})
            self.store.log('local','save_tunnel')
            return {'saved':True,'key_present':bool(self.key),'remembered':self.secret_file.exists()}

    def _prepare(self):
        config=self.store.get('tunnel',{})
        if not config: raise BridgeError('TUNNEL_NOT_CONFIGURED','尚未配置隧道，请先选择客户端并填写 Tunnel ID。')
        if not self.key and self.secret_file.exists(): self.key=unprotect_secret(self.secret_file.read_bytes())
        if not self.key: raise BridgeError('KEY_REQUIRED','本次运行缺少隧道运行时密钥；请在本机输入，不要发到聊天中。')
        binary=Path(config['binary'])
        if not binary.is_file(): raise BridgeError('BINARY_MISSING','隧道客户端文件不在配置路径，请重新选择。')
        # JSON is valid YAML; this avoids manual interpolation or a YAML dependency.
        profile={'config_version':1,
                 'control_plane':{'base_url':'https://api.openai.com','tunnel_id':config['tunnel_id'],'api_key':'env:CONTROL_PLANE_API_KEY'},
                 'mcp':{'server_urls':[{'channel':'main','url':self.mcp_url}],
                        'extra_headers':{'Authorization':'env:LOCALFOLDER_MCP_AUTH'},
                        'discovery_extra_headers':{'Authorization':'env:LOCALFOLDER_MCP_AUTH'},
                        'max_concurrent_requests':4, 'startup_wait_timeout':'10s'},
                 'health':{'listen_addr':'127.0.0.1:0','url_file':str(self.health_file)},
                 'admin_ui':{'open_browser':False},'log':{'level':'info','format':'json'}}
        self.profile.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
        env=os.environ.copy()
        # Do not accidentally inherit a stale or privileged tunnel setup.
        for k in list(env):
            if k.startswith(('CONTROL_PLANE_','MCP_','TUNNEL_CLIENT_','OPENAI_','HEALTH_','HARPOON_','CLOUDFLARED_')):
                del env[k]
        # Never send a loopback MCP call through a corporate/outbound HTTP proxy.
        no_proxy=env.get('NO_PROXY',env.get('no_proxy',''))
        env['NO_PROXY']=','.join(filter(None,[no_proxy,'127.0.0.1','localhost']))
        env['no_proxy']=env['NO_PROXY']
        env['CONTROL_PLANE_API_KEY']=self.key
        env['LOCALFOLDER_MCP_AUTH']='Bearer '+self.mcp_token
        return str(binary),env

    def _redact(self,text):
        for secret in (self.key,self.mcp_token):
            if secret: text=text.replace(secret,'[REDACTED]')
        text=re.sub(r'sk-[A-Za-z0-9_\-]{8,}','[REDACTED]',text)
        text=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._\-]+',r'\1[REDACTED]',text)
        return text

    def doctor(self):
        with self.lock:
            binary,env=self._prepare()
            try:
                p=subprocess.run([binary,'doctor','--profile-file',str(self.profile),'--explain'],
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=45,
                                 creationflags=0x08000000 if os.name=='nt' else 0)
            except subprocess.TimeoutExpired as exc: raise BridgeError('DOCTOR_TIMEOUT','官方诊断超过 45 秒；请检查网络、代理和权限。') from exc
            except OSError as exc: raise BridgeError('TUNNEL_EXEC_FAILED','无法启动官方客户端；检查文件架构和系统安全提示。') from exc
            self.doctor_text=self._redact(p.stdout.decode('utf-8',errors='replace'))[-12000:]
            return {'passed':p.returncode==0,'exit_code':p.returncode,'output':self.doctor_text,
                    'note':'doctor 通过不等于 ChatGPT 端到端读取成功。'}

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None: return {'started':False,'already_running':True}
            binary,env=self._prepare()
            if self.health_file.exists(): self.health_file.unlink()
            self.logs.clear()
            try:
                self.process=subprocess.Popen([binary,'run','--profile-file',str(self.profile)],env=env,
                                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                              stdin=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
            except OSError as exc: raise BridgeError('TUNNEL_EXEC_FAILED','无法启动官方隧道客户端。') from exc
            proc=self.process
            def collect():
                for raw in iter(proc.stdout.readline,b''):
                    self.logs.append(self._redact(raw.decode('utf-8',errors='replace').strip())[:2000])
                proc.stdout.close()
            threading.Thread(target=collect,daemon=True).start()
            self.store.log('local','start_tunnel')
            return {'started':True,'note':'进程已启动；等待官方 /healthz 和 /readyz 检查，不表示已连接。'}

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=8)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=3)
            self.store.log('local','stop_tunnel')
            return {'stopped':True}

    def forget_key(self):
        self.stop(); self.key=''
        if self.secret_file.exists(): self.secret_file.unlink()
        self.store.log('local','forget_key')
        return {'forgotten':True}

    def status(self):
        running=bool(self.process and self.process.poll() is None)
        health_url=''; healthy=False; ready=False
        if running and self.health_file.exists():
            try:
                raw=self.health_file.read_text(encoding='utf-8').strip()
                u=urlsplit(raw)
                if u.scheme=='http' and u.hostname=='127.0.0.1' and u.port and u.path in ('','/') and not u.query:
                    health_url=raw.rstrip('/')
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    for endpoint in ('healthz','readyz'):
                        try:
                            with opener.open(health_url+'/'+endpoint,timeout=0.4) as r: success=r.status==200
                        except Exception: success=False
                        if endpoint=='healthz': healthy=success
                        else: ready=success
            except Exception: pass
        return {'process_running':running,'healthy':healthy,'ready':ready,'health_url':health_url,
                'exit_code':self.process.poll() if self.process else None,'logs':list(self.logs),
                'configuration':self.store.get('tunnel',{}),'key_present':bool(self.key),
                'remembered':self.secret_file.exists(),'doctor_output':self.doctor_text}
