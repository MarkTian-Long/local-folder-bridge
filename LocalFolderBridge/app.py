#!/usr/bin/env python3
"""Double-click START.cmd on Windows, or run `python app.py` on a supported Python."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time
import webbrowser

APP_DIR=Path(__file__).resolve().parent
# Explicitly control imports even with the isolated Windows embeddable runtime.
sys.path.insert(0,str(APP_DIR))
sys.path.insert(0,str(APP_DIR/'third_party'))
from bridge import __version__


def state_directory() -> Path:
    if os.name=='nt':
        return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'LocalFolderBridge'
    return Path.home()/'.local-folder-bridge'

def main():
    parser=argparse.ArgumentParser(description='Local Folder Bridge — bounded local files over MCP')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--parse-worker')
    parser.add_argument('--stdio',action='store_true')
    parser.add_argument('--state-dir',type=Path)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--admin-port',type=int,default=18765)
    parser.add_argument('--mcp-port',type=int,default=18766)
    parser.add_argument('--install-pdf',action='store_true')
    parser.add_argument('--self-test',action='store_true',help='Run isolated local tests; never use authorized user files')
    args=parser.parse_args()
    if args.self_test:
        import runpy
        sys.argv=[str(APP_DIR/'tools'/'run_tests.py')]
        runpy.run_path(str(APP_DIR/'tools'/'run_tests.py'),run_name='__main__')
        return
    if args.parse_worker:
        from bridge.extractors import worker
        if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
        worker(args.parse_worker); return
    if args.install_pdf:
        from bridge.downloads import install_pdf
        try: print(json.dumps(install_pdf(APP_DIR),ensure_ascii=False))
        except Exception as exc: print(str(exc),file=sys.stderr); sys.exit(1)
        return
    from bridge.engine import Engine
    from bridge.protocol import Protocol
    state=(args.state_dir or state_directory()).resolve()
    state.mkdir(parents=True,exist_ok=True)
    if args.stdio:
        # Standalone stdio mode is for other local MCP hosts. Same authorization database, no GUI actions.
        e=Engine(state,APP_DIR); p=Protocol(e)
        if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
        while True:
            line=sys.stdin.buffer.readline(512*1024+1)
            if not line: break
            if len(line)>512*1024: break
            try: result=p.dispatch(json.loads(line))
            except Exception: result=Protocol.error(None,-32700,'Parse error')
            if result is not None: print(json.dumps(result,ensure_ascii=False),flush=True)
        return
    # Keep one manager per state directory; a second launch only reopens its UI.
    lock=open(state/'instance.lock','a+b')
    try:
        if os.name=='nt':
            import msvcrt
            if lock.tell()==0: lock.write(b'0'); lock.flush()
            lock.seek(0); msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        lock.close()
        try:
            existing=json.loads((state/'runtime.json').read_text(encoding='utf-8'))
            from urllib.parse import urlsplit
            u=urlsplit(existing['url'])
            if u.scheme=='http' and u.hostname=='127.0.0.1' and u.port:
                if not args.no_browser:
                    webbrowser.open(existing['url']+'/#auth='+existing['admin_token'])
                print('Local Folder Bridge is already running.' + (' Reopened the manager.' if not args.no_browser else ''))
                return
        except Exception: pass
        print('Another Local Folder Bridge instance is starting or running.',file=sys.stderr); return
    e=Engine(state,APP_DIR)
    e.store.recover_interrupted()
    e.store.cancel_pending(); e.store.set('writes_enabled',False); e.store.set('paused',False)
    from bridge.http_server import Application
    try: app=Application(e,args.admin_port,args.mcp_port)
    except OSError:
        lock.close()
        print(f'Cannot bind loopback ports {args.admin_port}/{args.mcp_port}. Close the conflicting program or use --admin-port/--mcp-port.',file=sys.stderr)
        return 1
    runtime=state/'runtime.json'
    runtime.write_text(json.dumps({'url':app.admin_url,'admin_token':app.admin_token,'pid':os.getpid()},indent=2),encoding='utf-8')
    if os.name!='nt': runtime.chmod(0o600)
    app.start()
    print('Local Folder Bridge '+__version__,flush=True)
    print('Local manager: '+app.admin_url)
    print('MCP endpoint: '+app.mcp_url+' (authenticated, loopback only)')
    print('Keep this window running. Closing it stops this session; no background service is installed.')
    if not args.no_browser: webbrowser.open(app.admin_url+'/#auth='+app.admin_token)
    def stop(*_): app.shutdown_event.set()
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    try:
        while not app.shutdown_event.wait(0.5): pass
    finally:
        app.close()
        runtime.unlink(missing_ok=True)
        lock.close()
    return 0

if __name__=='__main__':
    raise SystemExit(main())
