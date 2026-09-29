#!/usr/bin/env python3
"""Independent JSON Schema and real app-process lifecycle checks. Fixtures only.
Optional dependency: jsonschema. Runs without credentials or external networking.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, tempfile, time, traceback, urllib.request
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from tools.fixtures import isolated_directory
from bridge.engine import Engine
from bridge.protocol import Protocol,READ_TOOLS,WRITE_TOOLS
from bridge import __version__


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=Path,default=APP/'reports'/'current')
    args=parser.parse_args()
    args.report_dir.mkdir(parents=True,exist_ok=True)
    cases=[];failure=None;started=time.time()
    def record(name,condition=True):
        cases.append({'name':name,'status':'passed' if condition else 'failed'})
        if not condition:raise AssertionError(name)
    try:
        from jsonschema import Draft202012Validator
        for t in READ_TOOLS+WRITE_TOOLS:
            for schema in ('inputSchema','outputSchema'):
                Draft202012Validator.check_schema(t[schema]);record(t['name']+' '+schema+' schema valid')
        with isolated_directory(prefix='lfb-delivery-') as td:
            base=Path(td);folder=base/'files';folder.mkdir();(folder/'fixture.md').write_text('isolated delivery nonce',encoding='utf-8')
            e=Engine(base/'unit-state',APP);rid=e.add_root(str(folder),'资料')['root_id'];p=Protocol(e)
            def call(name,args):
                out=p.call(name,args)
                definition=next(t for t in READ_TOOLS+WRITE_TOOLS if t['name']==name)
                Draft202012Validator(definition['outputSchema']).validate(out['structuredContent'])
                record(name+' actual output conforms');return out['structuredContent']['data']
            call('get_status',{});call('list_files',{'root_id':rid});call('read_file',{'root_id':rid,'path':'fixture.md'});call('search_files',{'root_id':rid,'query':'nonce'})
            e.set_mode(writes=True);e.root_writable(rid,True)
            op=call('propose_write_file',{'root_id':rid,'path':'new.md','content':'new','reason':'explicit isolated test'})
            call('get_operation',{'operation_id':op['operation_id']})
            call('propose_move_file',{'root_id':rid,'path':'fixture.md','destination':'moved.md','reason':'explicit isolated test'})
            call('propose_create_directory',{'root_id':rid,'path':'sub','reason':'explicit isolated test'})
            call('propose_trash_file',{'root_id':rid,'path':'fixture.md','reason':'explicit isolated test'})
            invalid=p.call('read_file',{'root_id':rid,'path':'../outside.md'})
            Draft202012Validator(READ_TOOLS[3]['outputSchema']).validate(invalid['structuredContent']);record('Error output conforms to declared schema',invalid['isError'])
            state=base/'process-state'
            cmd=[sys.executable,str(APP/'app.py'),'--no-browser','--state-dir',str(state),'--admin-port','0','--mcp-port','0']
            proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def wait_runtime():
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    if proc.poll() is not None:raise RuntimeError('App exited before readiness: '+proc.stderr.read())
                    try:
                        details=json.loads((state/'runtime.json').read_text(encoding='utf-8'))
                        req=urllib.request.Request(details['url']+'/api/state',headers={'Authorization':'Bearer '+details['admin_token']})
                        with opener.open(req,timeout=1) as r:s=json.load(r)
                        return details,s['data']
                    except (OSError,ValueError):time.sleep(.1)
                raise TimeoutError('Standalone app not ready')
            def act(details,action,args=None):
                payload=json.dumps({'action':action,'args':args or {}}).encode()
                req=urllib.request.Request(details['url']+'/api/action',data=payload,headers={'Authorization':'Bearer '+details['admin_token'],'Content-Type':'application/json','Origin':details['url']})
                with opener.open(req,timeout=10) as r:return json.load(r)['data']
            try:
                details,ui=wait_runtime();record('Standalone app starts actual HTTP listeners',ui['status']['version']==__version__)
                record('Startup is read-only',not ui['status']['writes_enabled'])
                r=act(details,'add_root',{'path':str(folder),'alias':'独立进程测试'});rid=r['root_id']
                data=act(details,'tool',{'name':'read_file','arguments':{'root_id':rid,'path':'fixture.md'}})
                record('Standalone app reads authorized fixture',data['data']['sha256']==hashlib.sha256((folder/'fixture.md').read_bytes()).hexdigest())
                record('Standalone app performs real local MCP self-test',act(details,'self_test')['passed'])
                act(details,'mode',{'writes':True});act(details,'root_writable',{'root_id':rid,'enabled':True})
                act(details,'shutdown');proc.wait(timeout=8);record('Shutdown API terminates process cleanly',proc.returncode==0)
                record('Runtime credential file removed at shutdown',not (state/'runtime.json').exists())
                out,err=proc.communicate();record('Clean shutdown has no traceback','Traceback' not in err)
                proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
                d2,s2=wait_runtime();record('Restart retains explicit folder grants',len(s2['roots'])==1)
                record('Restart disables global write permissions',not s2['status']['writes_enabled'])
                record('Restart rotates manager credential',d2['admin_token']!=details['admin_token'])
                act(d2,'shutdown');proc.wait(timeout=8);record('Second clean shutdown',proc.returncode==0)
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=8)
                proc.communicate()
    except Exception:failure=traceback.format_exc();print(failure,file=sys.stderr)
    out={'suite':'Schema + standalone app process','platform':platform.platform(),'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'duration_seconds':round(time.time()-started,3),'success':failure is None,'passed':sum(c['status']=='passed' for c in cases),'total':len(cases),'failure':failure,'cases':cases,'limits':['No external network or actual user account','Not a Windows bootstrap, native browser or official tunnel-client executable test']}
    out['version']=__version__
    (args.report_dir/'delivery-checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k not in ('cases','failure')},ensure_ascii=False,indent=2));return 0 if failure is None else 1
if __name__=='__main__':raise SystemExit(main())
