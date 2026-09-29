"""Separate loopback listeners for local management and MCP. No public listener."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from .protocol import Protocol, PROTOCOL_VERSIONS
from .security import BridgeError, normalize_root, resolve_scoped
from . import windows
from .tunnel import Tunnel
from .downloads import install_pdf, install_tunnel

MAX_REQUEST=512*1024
CSP="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"

class LimitedServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,*a,**kw):
        self.slots=threading.BoundedSemaphore(24)
        super().__init__(*a,**kw)
    def process_request(self,request,client_address):
        if not self.slots.acquire(False):
            request.close(); return
        try: super().process_request(request,client_address)
        except Exception:
            self.slots.release(); raise
    def process_request_thread(self,request,client_address):
        try: super().process_request_thread(request,client_address)
        finally: self.slots.release()

class Application:
    def __init__(self,engine,admin_port=18765,mcp_port=18766,admin_token=None,mcp_token=None):
        self.engine=engine; self.protocol=Protocol(engine)
        self.admin_token=admin_token or secrets.token_urlsafe(32)
        self.mcp_token=mcp_token or secrets.token_urlsafe(32)
        self.shutdown_event=threading.Event()
        self.admin_server=LimitedServer(('127.0.0.1',admin_port),self._handler(False))
        try: self.mcp_server=LimitedServer(('127.0.0.1',mcp_port),self._handler(True))
        except Exception:
            self.admin_server.server_close(); raise
        self.admin_port=self.admin_server.server_address[1]; self.mcp_port=self.mcp_server.server_address[1]
        self.admin_url=f'http://127.0.0.1:{self.admin_port}'
        self.mcp_url=f'http://127.0.0.1:{self.mcp_port}/mcp'
        self.tunnel=Tunnel(engine.store,self.mcp_url,self.mcp_token)
        self.started=time.time()
        self.install_lock=threading.Lock()

    def start(self):
        for s in (self.admin_server,self.mcp_server):
            threading.Thread(target=s.serve_forever,kwargs={'poll_interval':0.2},daemon=True).start()

    def close(self):
        self.engine.set_mode(paused=True,writes=False)
        self.tunnel.stop()
        for s in (self.admin_server,self.mcp_server): s.shutdown(); s.server_close()

    def state(self):
        e=self.engine
        pdfpath=e.app_dir/'third_party'/'pypdf'/'__init__.py'
        return {'status':e.status(),'roots':e.store.roots(),'operations':e.store.operations(),
                'audit':e.store.audit(),'tunnel':self.tunnel.status(),'last_mcp_call':e.last_mcp_call,
                'admin_url':self.admin_url,'mcp_url':self.mcp_url,'uptime':int(time.time()-self.started),
                'state_directory':str(e.store.directory),'app_directory':str(e.app_dir),
                'pdf_component_installed':pdfpath.is_file(),'windows':os.name=='nt'}

    def self_test(self):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        checks=[]
        for n,(method,params) in enumerate((('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'local-self-test','version':'1.0'}}),('tools/list',{}),('tools/call',{'name':'get_status','arguments':{}})),1):
            msg={'jsonrpc':'2.0','id':n,'method':method,'params':params}
            req=urllib.request.Request(self.mcp_url,data=json.dumps(msg).encode(),
                headers={'Authorization':'Bearer '+self.mcp_token,'Content-Type':'application/json',
                         'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25',
                         'X-Local-Self-Test':'true'})
            with opener.open(req,timeout=8) as r: result=json.load(r)
            checks.append({'name':method,'passed':'result' in result and not result['result'].get('isError',False)})
        return {'passed':all(c['passed'] for c in checks),'checks':checks,
                'note':'这里只验证本机 MCP 握手、工具发现和状态调用；没有验证 OpenAI 隧道或 ChatGPT 端到端读取。'}

    def action(self,data):
        if not isinstance(data,dict): raise BridgeError('INVALID_ARGUMENTS','请求必须是 JSON 对象。')
        name=data.get('action'); args=data.get('args',{})
        if not isinstance(args,dict): raise BridgeError('INVALID_ARGUMENTS','args 必须是 JSON 对象。')
        e=self.engine
        if name=='add_root': return e.add_root(args.get('path',''),args.get('alias',''))
        if name=='remove_root': return e.remove_root(args.get('root_id',''))
        if name=='root_writable':
            if type(args.get('enabled')) is not bool: raise BridgeError('INVALID_ARGUMENTS','enabled 必须是布尔值。')
            return e.root_writable(args.get('root_id',''),args['enabled'])
        if name=='mode':
            for key in ('paused','writes'):
                if key in args and type(args[key]) is not bool: raise BridgeError('INVALID_ARGUMENTS','模式参数必须是布尔值。')
            return e.set_mode(paused=args.get('paused'),writes=args.get('writes'))
        if name=='tool': return self.protocol.call(args.get('name',''),args.get('arguments',{}),origin='local-preview')['structuredContent']
        if name=='decide':
            if type(args.get('approve')) is not bool: raise BridgeError('INVALID_ARGUMENTS','审批参数必须是布尔值。')
            return e.decide(args.get('operation_id',''),args['approve'],args.get('confirmation',''))
        if name=='restore_backup': return e.restore_backup(args.get('operation_id',''), args.get('destination',''), args.get('confirmation',''))
        if name=='pick_folder': return {'path':windows.pick('folder')}
        if name=='pick_tunnel': return {'path':windows.pick('tunnel')}
        if name=='save_tunnel': return self.tunnel.save(args.get('binary',''),args.get('tunnel_id',''),args.get('key',''),bool(args.get('remember',False)))
        if name=='doctor': return self.tunnel.doctor()
        if name=='start_tunnel': return self.tunnel.start()
        if name=='stop_tunnel': return self.tunnel.stop()
        if name=='forget_key': return self.tunnel.forget_key()
        if name in ('install_pdf','install_tunnel'):
            if not self.install_lock.acquire(False): raise BridgeError('INSTALL_BUSY','另一个组件正在安装。')
            try:
                result=install_pdf(e.app_dir) if name=='install_pdf' else install_tunnel(e.store.directory)
                e._cache.clear()
                return result
            finally: self.install_lock.release()
        if name=='self_test': return self.self_test()
        if name=='create_demo':
            base=Path.home()/'LocalFolderBridge-Demo'
            base.mkdir(exist_ok=True)
            filename='connection-check-'+secrets.token_hex(3)+'.txt'
            nonce='LFB-'+secrets.token_hex(8)
            normalize_root(str(base), e.store.directory, e.app_dir)
            found=next((r for r in e.store.roots() if Path(r['path'])==base.resolve()),None)
            root={'root_id':found['id'],'alias':found['alias']} if found else e.add_root(str(base),'本机连接测试')
            target=resolve_scoped(e.root(root['root_id']),filename,missing_leaf=True)
            with target.open('x',encoding='utf-8') as f:
                f.write('这是本机连接测试文件。\n验证字符串：'+nonce+'\n此内容只用于确认 ChatGPT 是否实际读取了这台电脑。\n')
            return {**root,'path':filename,'verification':nonce}
        if name=='open_backups':
            p=e.store.directory/'backups'; p.mkdir(exist_ok=True)
            if os.name=='nt': os.startfile(p)
            else: raise BridgeError('WINDOWS_ONLY','请手动打开状态目录中的 backups 文件夹。')
            return {'opened':True}
        if name=='shutdown': self.shutdown_event.set(); return {'stopping':True}
        raise BridgeError('UNKNOWN_ACTION','不支持的本机管理操作。')

    def _handler(self,is_mcp):
        app=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def setup(self):
                super().setup(); self.connection.settimeout(12)
            def log_message(self,*args): pass
            def send(self,status,data=None,content_type='application/json; charset=utf-8',extra=None):
                body=b'' if data is None else (data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode('utf-8'))
                self.send_response(status)
                self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Content-Security-Policy',CSP)
                self.send_header('Connection','close')
                for k,v in (extra or {}).items(): self.send_header(k,v)
                self.end_headers()
                try:
                    if body: self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError): pass
                self.close_connection=True
            def trusted(self):
                port=self.server.server_address[1]
                if any(len(self.headers.get_all(k,[])) > 1 for k in ('Host','Origin','Authorization','Content-Length')):
                    self.send(400,{'error':'Duplicate security headers'}); return False
                if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                    self.send(403,{'error':'Invalid Host'}); return False
                origin=self.headers.get('Origin')
                if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                    self.send(403,{'error':'Invalid Origin'}); return False
                return True
            def authorized(self):
                expected='Bearer '+(app.mcp_token if is_mcp else app.admin_token)
                if not secrets.compare_digest(self.headers.get('Authorization','').encode('utf-8'),expected.encode('utf-8')):
                    self.send(401,{'error':'Unauthorized'},extra={'WWW-Authenticate':'Bearer realm="LocalFolderBridge"'}); return False
                return True
            def body(self):
                if self.headers.get('Transfer-Encoding'):
                    self.send(400,{'error':'Chunked request bodies are not supported'}); return None
                try: length=int(self.headers.get('Content-Length','-1'))
                except ValueError: length=-1
                if length<0 or length>MAX_REQUEST:
                    self.send(413,{'error':'Request body must be at most 512 KiB'}); return None
                if self.headers.get_content_type()!='application/json':
                    self.send(415,{'error':'Content-Type must be application/json'}); return None
                try:
                    raw=self.rfile.read(length)
                    if len(raw)!=length:
                        self.send(400,{'error':'Incomplete request body'}); return None
                    value=json.loads(raw)
                    if value is None:
                        self.send(400,Protocol.error(None,-32600,'Invalid Request')); return None
                    return value
                except (TimeoutError, OSError):
                    self.send(408,{'error':'Request body timed out'}); return None
                except (ValueError,UnicodeDecodeError):
                    self.send(400,Protocol.error(None,-32700,'Parse error') if is_mcp else {'error':'Invalid JSON'}); return None
            def do_GET(self):
                if not self.trusted(): return
                path=urlsplit(self.path).path
                if is_mcp:
                    if path!='/mcp': self.send(404,{'error':'Not found'}); return
                    if not self.authorized(): return
                    self.send(405,{'error':'Use Streamable HTTP POST; unsolicited SSE is not offered.'},extra={'Allow':'POST'}); return
                static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
                if path in static:
                    file,ctype=static[path]
                    self.send(200,(app.engine.app_dir/'web'/file).read_bytes(),ctype); return
                if path=='/healthz': self.send(200,{'app':'LocalFolderBridge','status':'local-listener-running'}); return
                if path=='/api/state':
                    if self.authorized(): self.send(200,{'ok':True,'data':app.state()})
                    return
                self.send(404,{'error':'Not found'})
            def do_POST(self):
                if not self.trusted(): return
                path=urlsplit(self.path).path
                if path!=('/mcp' if is_mcp else '/api/action'):
                    self.send(404,{'error':'Not found'}); return
                if not self.authorized(): return
                if is_mcp:
                    accept=self.headers.get('Accept','')
                    if 'application/json' not in accept or 'text/event-stream' not in accept:
                        self.send(406,{'error':'Accept must contain application/json and text/event-stream'}); return
                    version=self.headers.get('MCP-Protocol-Version')
                    if version and version not in PROTOCOL_VERSIONS:
                        self.send(400,{'error':'Unsupported MCP-Protocol-Version'}); return
                body=self.body()
                if body is None: return
                try:
                    if is_mcp:
                        origin='local-self-test' if self.headers.get('X-Local-Self-Test')=='true' else 'mcp'
                        result=app.protocol.dispatch(body,origin)
                        self.send(202 if result is None else 200,result)
                    else: self.send(200,{'ok':True,'data':app.action(body)})
                except BridgeError as exc:
                    self.send(400,{'ok':False,'error':{'code':exc.code,'message':exc.message}})
                except Exception:
                    self.send(500,{'ok':False,'error':{'code':'INTERNAL_ERROR','message':'程序内部错误，请检查配置或运行诊断。'}})
            def do_DELETE(self):
                if self.trusted() and self.authorized(): self.send(405,{'error':'Stateless transport; no session to delete'},extra={'Allow':'POST'})
            def do_OPTIONS(self):
                if self.trusted(): self.send(405,{'error':'Cross-origin requests are not supported'})
        return Handler
