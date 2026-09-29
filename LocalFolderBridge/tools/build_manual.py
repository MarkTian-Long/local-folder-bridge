#!/usr/bin/env python3
"""Developer-only: render the Markdown manual to self-contained offline HTML.
Requires markdown-it-py; not used by the running application.
"""
from __future__ import annotations
import base64, html, re, sys
from pathlib import Path
from markdown_it import MarkdownIt
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from bridge import __version__


def main():
    source=(APP/'docs'/'操作手册.md').read_text(encoding='utf-8')
    md=MarkdownIt('commonmark',{'html':False}).enable('table')
    body=md.render(source)
    toc=[]
    def heading(m):
        text=m.group(1);i='section-'+str(len(toc)+1);toc.append((i,text));return '<h2 id="'+i+'">'+text+'</h2>'
    body=re.sub(r'<h2>(.*?)</h2>',heading,body)
    def photo(name,caption):
        src='data:image/png;base64,'+base64.b64encode((APP/'docs'/'images'/name).read_bytes()).decode()
        return '<figure><img src="'+src+'" alt="'+html.escape(caption)+'"><figcaption>'+html.escape(caption)+'</figcaption></figure>'
    body=body.replace('<h2 id="section-3">',photo('01-overview.png','界面总览。来自 Linux Chromium 隔离样本渲染，交互使用测试转接层；不是用户 Windows 实机截图。')+'<h2 id="section-3">')
    body=body.replace('<h2 id="section-8">',photo('03-approval.png','本机审批界面。先核对拟写入全文，再输入文件名批准；此图为隔离测试样本。')+'<h2 id="section-8">')
    nav=''.join('<a href="#'+i+'">'+t+'</a>' for i,t in toc)
    css='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;line-height:1.85;background:#f5f6fa;color:#273246}.side{position:fixed;left:0;top:0;bottom:0;width:265px;background:white;border-right:1px solid #e2e7ef;padding:30px 23px;overflow:auto}.logo{font-size:18px;color:#5446b9;font-weight:700;margin-bottom:5px}.version{font-size:12px;color:#7d8696;margin-bottom:22px}.side a{display:block;color:#57677e;text-decoration:none;font-size:12px;margin:10px 0;line-height:1.6}.side a:hover{color:#5947c8}main{margin:25px 30px 40px 290px;max-width:1040px;background:white;border:1px solid #e3e7ed;border-radius:16px;padding:38px 48px 55px}h1{font-size:30px;line-height:1.4;margin:0 0 15px;letter-spacing:-.5px}h2{font-size:22px;line-height:1.5;margin:38px 0 14px;scroll-margin-top:25px;padding-top:12px;border-top:1px solid #eceff4}h3{font-size:17px}p,li{font-size:14px}a{color:#6554c8;overflow-wrap:anywhere}code{font-family:Consolas,"Microsoft YaHei",monospace;font-size:.9em;padding:2px 4px;background:#f1f3f8;border-radius:4px;overflow-wrap:anywhere}pre{padding:16px 20px;border-radius:9px;background:#f4f5f9;border:1px solid #e4e7ee;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}pre code{background:none;padding:0}table{display:block;overflow-x:auto;border-collapse:collapse;width:100%;font-size:12px;margin:18px 0}th,td{text-align:left;border:1px solid #e0e5ed;padding:10px 12px;vertical-align:top;min-width:105px;overflow-wrap:anywhere}th{background:#f1f0fa;color:#584a8c;font-weight:600}blockquote{margin:20px 0;padding:10px 20px;border-left:4px solid #8170dd;background:#f5f3fe}figure{margin:28px 0}figure img{width:100%;height:auto;border-radius:10px;border:1px solid #e2e6ef}figcaption{font-size:11px;color:#8a91a0;margin-top:8px}.tag{font-size:11px;color:#8b7dba;letter-spacing:2px;margin-bottom:14px}.foot{font-size:11px;color:#8b93a0;margin-top:35px}@media(max-width:950px){.side{position:static;width:auto;border:0;border-bottom:1px solid #e1e6ee;padding:20px}.side nav{display:flex;flex-wrap:wrap;gap:5px 20px}.side a{margin:4px 0}.version{margin-bottom:8px}main{margin:18px;padding:25px}h1{font-size:25px}}@media print{.side{display:none}body{background:white}main{margin:0;max-width:none;border:0;padding:0}h2{break-after:avoid}figure{break-inside:avoid}a{color:inherit}}'''
    result='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>本机文件桥 '+__version__+' · 操作手册</title><style>'+css+'</style></head><body><aside class="side"><div class="logo">↔ 本机文件桥</div><div class="version">'+__version__+' · Windows 联网启动版<br>离线操作手册 · 2026-09-29</div><nav>'+nav+'</nav></aside><main><div class="tag">LOCAL FOLDER BRIDGE / USER MANUAL</div>'+body+'<div class="foot">本手册不包含凭证、外部字体或运行期脚本。完整测试范围见随包报告。</div></main></body></html>'
    (APP/'使用手册.html').write_text(result,encoding='utf-8')
    print('Rendered manual:',len(result.encode()),'bytes,',len(toc),'sections')
if __name__=='__main__':main()
