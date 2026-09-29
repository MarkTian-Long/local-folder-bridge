#!/usr/bin/env python3
"""Actual Chromium UI checks against two real loopback listeners; no cloud credentials.
Requires optional developer dependency playwright and an installed Chromium.
"""
from __future__ import annotations
import argparse, json, os, platform, re, shutil, sys, tempfile, time, traceback, urllib.request, urllib.error
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from tools.fixtures import isolated_directory
from bridge.engine import Engine
from bridge.http_server import Application
from bridge import __version__


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=Path,default=APP/'reports'/'current')
    parser.add_argument('--native-only',action='store_true',help='Fail instead of using a DOM adapter when native navigation is blocked')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    report=args.report_dir;report.mkdir(parents=True,exist_ok=True)
    images=report/'screenshots';images.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];started=time.time();failed=None;browser_mode='native-http';navigation_block=None
    def check(name, condition=True):
        checks.append({'name':name,'status':'passed' if condition else 'failed'})
        if not condition:raise AssertionError(name)
    with isolated_directory(prefix='lfb-browser-') as tmp:
        base=Path(tmp);folder=base/'示例项目';folder.mkdir()
        (folder/'研究说明.md').write_text('# 项目资料\n本机文件桥浏览器验收。\n关键词：授权目录。\n<script>window.FILE_INJECTION=true</script>\n',encoding='utf-8')
        (folder/'长文件.md').write_text('\n'.join('第'+str(i)+'行 - 版本一致性校验' for i in range(1,241)),encoding='utf-8')
        (folder/'可回收.md').write_text('应恢复的原文。',encoding='utf-8')
        (folder/'资料').mkdir();(folder/'资料'/'子文档.txt').write_text('子目录正文。',encoding='utf-8')
        e=Engine(base/'state',APP);app=Application(e,admin_port=0,mcp_port=0);app.start()
        def rpc(name,args):
            payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}
            req=urllib.request.Request(app.mcp_url,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+app.mcp_token,'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req,timeout=15) as r:out=json.load(r)
            return out['result']['structuredContent']
        try:
            with sync_playwright() as p:
                exe=os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium') or shutil.which('google-chrome')
                browser=p.chromium.launch(headless=True,**({'executable_path':exe} if exe else {}))
                context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
                page=context.new_page();page.on('pageerror',lambda err:errors.append(str(err)))
                def load_with_adapter(pg, auth):
                    # Test-only browser adapter. No production code, browser policy or
                    # user data is changed. Python still calls the actual HTTP server.
                    def fetch_local(path, options):
                        if path not in ('/api/state','/api/action'):
                            raise ValueError('Unexpected fixture HTTP path')
                        hdr=dict(options.get('headers',{}));hdr['Origin']=app.admin_url
                        body=options.get('body')
                        req=urllib.request.Request(app.admin_url+path,
                            data=body.encode() if isinstance(body,str) else None,
                            headers=hdr,method=options.get('method','GET'))
                        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        try:
                            with opener.open(req,timeout=30) as response:
                                return {'status':response.status,'body':response.read().decode()}
                        except urllib.error.HTTPError as ex:
                            return {'status':ex.code,'body':ex.read().decode()}
                    pg.expose_function('__fixtureFetch',fetch_local)
                    html=(APP/'web'/'index.html').read_text(encoding='utf-8')
                    html=html.replace('<link rel="stylesheet" href="/style.css">','').replace('<script defer src="/app.js"></script>','')
                    pg.set_content(html)
                    pg.add_style_tag(content=(APP/'web'/'style.css').read_text(encoding='utf-8'))
                    pg.evaluate("""({auth})=>{
                        const store=new Map(auth ? [['lfb-admin',auth]] : []);
                        Object.defineProperty(window,'sessionStorage',{value:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)}});
                        window.fetch=async(path,options={})=>{
                            const out=await window.__fixtureFetch(path,options);
                            return new Response(out.body,{status:out.status,headers:{'Content-Type':'application/json'}});
                        };
                    }""",{'auth':auth})
                    pg.add_script_tag(content=(APP/'web'/'app.js').read_text(encoding='utf-8'))
                try:
                    page.goto(app.admin_url+'/#auth='+app.admin_token)
                except Exception as ex:
                    if args.native_only or 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(ex):raise
                    browser_mode='DOM with explicit HTTP and sessionStorage test adapters'
                    navigation_block='Chromium policy returned ERR_BLOCKED_BY_ADMINISTRATOR for loopback URL; policy not modified.'
                    page.close();page=context.new_page();page.on('pageerror',lambda err:errors.append(str(err)))
                    load_with_adapter(page,app.admin_token)
                expect(page.locator('#local-status')).to_have_text('正在运行');check('Authenticated manager loads')
                if browser_mode=='native-http':check('Credential fragment removed',page.evaluate('location.hash')=='')
                expect(page.locator('#mode-label')).to_have_text('默认只读');check('Default read-only UI')
                def nav(name):page.locator('.nav[data-tab="'+name+'"]').click()
                nav('roots');page.locator('#root-path').fill(str(folder));page.locator('#root-alias').fill('示例项目资料');page.locator('#add-root').click()
                expect(page.locator('#root-count')).to_have_text('1');check('Folder grant via UI')
                rid=e.store.roots()[0]['id']
                expect(page.locator('#roots-list')).to_contain_text('示例项目资料');check('Alias and root displayed')
                nav('overview');page.screenshot(path=str(images/'01-overview.png'),full_page=True)
                nav('files');page.locator('#browse-btn').click()
                expect(page.locator('#file-results')).to_contain_text('研究说明.md');check('Directory listing')
                row=lambda name:page.locator('.file-item').filter(has=page.locator('.file-name',has_text=name))
                row('研究说明.md').get_by_role('button',name='读取',exact=True).click()
                expect(page.locator('#reader-text')).to_contain_text('本机文件桥浏览器验收。');check('Chinese file body displayed')
                check('Document HTML remains inert',page.evaluate('window.FILE_INJECTION') is None)
                check('SHA shown in reader','SHA-256' in page.locator('#reader-meta').inner_text())
                row('资料').get_by_role('button',name='打开',exact=True).click()
                expect(page.locator('#file-path')).to_have_value('资料');expect(page.locator('#file-results')).to_contain_text('子文档.txt');check('Navigate into subfolder')
                page.locator('#parent-btn').click();expect(page.locator('#file-path')).to_have_value('');check('Navigate to parent')
                page.locator('#search-query').fill('授权目录');page.locator('#search-mode').select_option('content');page.locator('#search-btn').click()
                expect(page.locator('#file-results')).to_contain_text('研究说明.md');check('Body keyword search')
                expect(page.locator('#file-coverage')).to_contain_text('候选路径');check('Search coverage shown')
                page.locator('#browse-btn').click();row('长文件.md').get_by_role('button',name='读取',exact=True).click()
                expect(page.locator('#read-more')).to_be_visible();check('Read pagination offered')
                page.locator('#read-more').click();expect(page.locator('#reader-text')).to_contain_text('第240行');check('Read continuation appends remaining lines')
                expect(page.locator('#read-more')).to_be_hidden();check('Read pagination terminates')
                row('研究说明.md').get_by_role('button',name='读取',exact=True).click()
                page.screenshot(path=str(images/'02-reader.png'),full_page=True)
                accept_dialog=lambda d:d.accept()
                page.on('dialog',accept_dialog)
                nav('roots');page.locator('#writes-switch').check();expect(page.locator('#mode-label')).to_have_text('操作需本机审批');check('Enable proposal mode via confirmation')
                page.locator('#roots-list input[type=checkbox]').check();check('Enable per-folder proposal permission',bool(e.root(rid)['writable']))
                check('Writes exposed only after enabling',len(app.protocol.tools())==9)
                out=rpc('propose_write_file',{'root_id':rid,'path':'新建总结.md','content':'# 测试总结\n经本机批准后才写入。','reason':'浏览器验收中明确请求创建测试文件。'})
                check('Real MCP HTTP creates proposal',out['ok']);op=out['data']['operation_id']
                check('Proposal does not create file',(not (folder/'新建总结.md').exists()))
                nav('approvals');page.locator('#refresh-approvals').click();expect(page.locator('.approval-card.pending')).to_have_count(1)
                expect(page.locator('.approval-card.pending')).to_contain_text('经本机批准后才写入。');check('Full write proposal visible for review')
                page.screenshot(path=str(images/'03-approval.png'),full_page=True)
                page.locator('.approval-card.pending input').fill('wrong.md');page.locator('.approval-card.pending').get_by_role('button',name='批准并执行').click()
                expect(page.locator('#toast')).to_contain_text('确认');check('Wrong filename confirmation rejected',not (folder/'新建总结.md').exists())
                page.locator('.approval-card.pending input').fill('新建总结.md');page.locator('.approval-card.pending').get_by_role('button',name='批准并执行').click()
                expect(page.locator('.approval-card.pending')).to_have_count(0)
                check('Local approval commits expected bytes',(folder/'新建总结.md').read_text(encoding='utf-8')=='# 测试总结\n经本机批准后才写入。')
                check('MCP confirms completion after approval',rpc('get_operation',{'operation_id':op})['data']['result']['executed'])
                out=rpc('propose_trash_file',{'root_id':rid,'path':'可回收.md','reason':'验收程序回收与恢复。'});op=out['data']['operation_id']
                page.locator('#refresh-approvals').click();expect(page.locator('.approval-card.pending')).to_have_count(1)
                page.locator('.approval-card.pending input').fill('可回收.md');page.locator('.approval-card.pending').get_by_role('button',name='批准并执行').click()
                expect(page.locator('.approval-card.pending')).to_have_count(0)
                check('Quarantine preserves backup and removes original',not (folder/'可回收.md').exists() and (base/'state'/'backups'/op/'original.bin').read_text(encoding='utf-8')=='应恢复的原文。')
                # Switch handler for the two local restore prompts.
                page.remove_listener('dialog',accept_dialog)
                answers=iter(['恢复副本.md','恢复副本.md'])
                restore_dialog=lambda d:d.accept(next(answers))
                page.on('dialog',restore_dialog)
                page.get_by_role('button',name='从备份恢复为新文件',exact=True).click()
                expect(page.locator('#toast')).to_contain_text('已恢复到')
                check('Restore through two local UI confirmations',(folder/'恢复副本.md').read_text(encoding='utf-8')=='应恢复的原文。')
                page.remove_listener('dialog',restore_dialog);page.on('dialog',accept_dialog)
                page.locator('#pause-btn').click();expect(page.locator('#mode-label')).to_have_text('访问已暂停')
                check('Pause blocks remote reads',not rpc('read_file',{'root_id':rid,'path':'研究说明.md'})['ok'])
                page.locator('#pause-btn').click();expect(page.locator('#mode-label')).not_to_have_text('访问已暂停');check('Resume works')
                nav('connection');page.locator('#selftest-btn').click();expect(page.locator('#diagnostic-output')).to_contain_text('"passed": true');check('UI local MCP self-test passes')
                check('Unconfigured tunnel is not reported connected',page.locator('#tunnel-status').inner_text()=='尚未配置')
                page.screenshot(path=str(images/'04-connection.png'),full_page=True)
                nav('audit');expect(page.locator('#audit-body')).to_contain_text('propose_write_file');check('Audit shows actual MCP call metadata')
                nav('overview');page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(150)
                check('Mobile overview has no horizontal page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                page.screenshot(path=str(images/'05-responsive.png'),full_page=True)
                for tabname in ['roots','files','approvals','connection','audit','help']:
                    nav(tabname)
                    if not page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'):
                        print('Overflow',tabname,page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right})).slice(-15)"))
                    check('Mobile layout '+tabname,page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                check('No browser JS exceptions',not errors)
                context.close()
                # A separate browser storage context must not inherit the manager credential.
                ctx=browser.new_context();unauth=ctx.new_page()
                if browser_mode=='native-http':unauth.goto(app.admin_url)
                else:load_with_adapter(unauth,'')
                expect(unauth.locator('#auth-warning')).to_be_visible();check('Fresh browser context cannot access management')
                ctx.close();browser.close()
        except Exception as ex:
            failed=traceback.format_exc();print(failed,file=sys.stderr)
        finally:app.close()
    data={'version':__version__,'suite':'Chromium interaction + real loopback HTTP backend','browser_mode':browser_mode,'native_navigation_limit':navigation_block,'platform':platform.platform(),'python':platform.python_version(),'elapsed_seconds':round(time.time()-started,3),'checks':checks,'passed':sum(c['status']=='passed' for c in checks),'total':len(checks),'javascript_errors':errors,'success':failed is None,'failure':failed,'limits':['In adapter mode native browser HTTP, sessionStorage and CSP behavior are not verified','Native folder dialogs and DPAPI are outside this browser suite','No real OpenAI tunnel, key, account or ChatGPT UI','Fixtures only; no user folders used']}
    (report/'browser-tests.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in ['checks','failure']},ensure_ascii=False,indent=2))
    return 0 if data['success'] else 1
if __name__=='__main__':raise SystemExit(main())
