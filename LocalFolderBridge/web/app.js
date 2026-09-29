'use strict';
const $ = id => document.getElementById(id);
let savedToken='';
try { savedToken=sessionStorage.getItem('lfb-admin')||''; } catch (_) {}
let token = new URLSearchParams(location.hash.slice(1)).get('auth') || savedToken;
try { if (token) sessionStorage.setItem('lfb-admin', token); } catch (_) {}
if (location.hash) history.replaceState(null, '', location.pathname);
let state=null, currentTab='overview', fileMode='browse', listOffset=null, searchCursor='', readContext=null, busyPoll=false, hydrated=false, opsSignature='';
const labels={overview:'总览',roots:'授权文件夹',files:'浏览与搜索',approvals:'待审批操作',connection:'连接与诊断',audit:'调用记录',help:'使用说明'};
const statusNames={pending:'待本机审批',completed:'已执行',rejected:'已拒绝',cancelled:'已取消',expired:'已过期',executing:'执行中',failed:'失败 · 请核对',interrupted:'中断 · 状态待核对'};
const kindNames={write:'写入文本文件',move:'移动 / 重命名单个文件',mkdir:'创建子文件夹',trash:'请求移入程序回收区'};
function el(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n;}
function show(id,yes=true){$(id).classList.toggle('hidden',!yes);}
function toast(message){$('toast').textContent=message;show('toast');clearTimeout(toast.timer);toast.timer=setTimeout(()=>show('toast',false),6500);}
function date(v){return v?new Date(v*1000).toLocaleString('zh-CN',{hour12:false}):'—';}
function bytes(v){if(v==null)return '文件夹';if(v<1024)return v+' B';if(v<1048576)return (v/1024).toFixed(1)+' KiB';return (v/1048576).toFixed(1)+' MiB';}
async function request(path, options={}){
  if(!token)throw new Error('缺少本机管理凭证，请双击 START.cmd 重新打开。');
  const response=await fetch(path,{cache:'no-store',...options,headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json',...(options.headers||{})}});
  const out=await response.json();
  if(!response.ok || out.ok===false){const err=out.error||{};throw new Error((err.code?'['+err.code+'] ':'')+(err.message||err||('HTTP '+response.status)));}
  return out.data;
}
async function action(name,args={}){return request('/api/action',{method:'POST',body:JSON.stringify({action:name,args})});}
async function tool(name,args={}){const result=await action('tool',{name,arguments:args});if(!result.ok)throw new Error('['+result.error.code+'] '+result.error.message);return result.data;}
function button(text,fn,cls='btn small'){const b=el('button',cls,text);b.addEventListener('click',()=>run(b,fn));return b;}
async function run(b,fn){b.disabled=true;try{await fn();await refresh();}catch(e){toast(e.message||String(e));}finally{b.disabled=false;}}
function bind(id,fn){$(id).addEventListener('click',()=>run($(id),fn));}
function tab(name){currentTab=name;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('hidden',x.id!=='tab-'+name));document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));$('page-title').textContent=labels[name];if(name==='approvals'&&state)renderOperations();}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function renderRoots(){
  const previous=$('file-root').value;
  $('roots-list').replaceChildren();$('file-root').replaceChildren();
  if(!state.roots.length){$('roots-list').append(el('div','card empty','尚未授权任何目录。先添加一个测试文件夹。'));$('file-root').append(new Option('暂无授权目录',''));}
  for(const r of state.roots){
    $('file-root').append(new Option(r.alias,r.id));
    const card=el('article','card root-card');card.append(el('div','root-icon','▱'));
    const content=el('div','root-content');content.append(el('h3','',r.alias),el('p','muted smalltext',r.path),el('p','muted smalltext','目录标识：'+r.id));card.append(content);
    const controls=el('div','root-actions');const label=el('label','check');const checkbox=el('input');checkbox.type='checkbox';checkbox.checked=!!r.writable;label.append(checkbox,document.createTextNode('此目录允许操作提案'));
    checkbox.addEventListener('change',async()=>{const enabled=checkbox.checked;checkbox.disabled=true;try{if(enabled&&!confirm('允许对“'+r.alias+'”提交文件操作提案？操作总开关仍需开启，每次执行仍需本机审批。')){checkbox.checked=false;return;}await action('root_writable',{root_id:r.id,enabled});await refresh();}catch(e){toast(e.message);checkbox.checked=!enabled;}finally{checkbox.disabled=false;}});
    controls.append(label,button('浏览',async()=>{$('file-root').value=r.id;$('file-path').value='';tab('files');await browse(false);}),button('移除授权',async()=>{if(confirm('移除“'+r.alias+'”的授权？其待审批提案将取消，原文件不会删除。'))await action('remove_root',{root_id:r.id});},'btn small danger-text'));card.append(controls);$('roots-list').append(card);
  }
  if(state.roots.some(r=>r.id===previous))$('file-root').value=previous;
  $('roots-summary').textContent=state.roots.length+' / 12 个目录';
}
function renderOperations(){
  const sig=JSON.stringify(state.operations);if(sig===opsSignature)return;opsSignature=sig;
  const host=$('operations-list');host.replaceChildren();
  if(!state.operations.length){host.append(el('div','card empty','当前没有操作提案。模型提出修改后，待审批内容会出现在这里。'));return;}
  for(const op of state.operations){
    const card=el('article','card approval-card '+op.status);const top=el('div','card-top');top.append(el('h2','',kindNames[op.kind]||op.kind),el('span','approval-status '+op.status,statusNames[op.status]||op.status));card.append(top);
    const meta=el('dl','approval-meta');const root=state.roots.find(r=>r.id===op.root_id);const rows=[['授权目录',root?root.alias+' · '+root.path:op.root_id+'（授权可能已移除）'],['目标文件',op.args.path],['创建时间',date(op.created)],['操作原因',op.reason||'未提供'],['操作标识',op.id]];
    if(op.args.destination)rows.splice(2,0,['移至',op.args.destination]);if(op.snapshot.sha256)rows.push(['原始 SHA-256',op.snapshot.sha256]);if(op.status==='pending')rows.push(['过期时间',date(op.expires)]);
    rows.forEach(([k,v])=>meta.append(el('dt','',k),el('dd','',v)));card.append(meta);
    if(op.args.content!==undefined){const details=el('details');details.open=op.status==='pending';details.append(el('summary','', '拟写入的完整文本（'+op.args.content.length+' 字符）'),el('pre','reader',op.args.content));card.append(details);}
    if(op.result)card.append(el('pre','console',JSON.stringify(op.result,null,2)));
    if(op.status==='pending'){
      const row=el('div','form-row');const label=el('label','grow','请输入原目标的完整文件名 / 文件夹名');const confirmInput=el('input');confirmInput.placeholder='完整名称，包含扩展名';confirmInput.autocomplete='off';label.append(confirmInput);row.append(label);
      row.append(button('批准并执行',async()=>{if(!confirmInput.value)throw new Error('请先输入完整文件名确认。');if(op.kind==='trash'&&!confirm('本程序将先校验并备份，再移除原路径的文件。原始字节保留在程序回收区（不是 Windows 回收站），不自动清理。继续？'))return;const out=await action('decide',{operation_id:op.id,approve:true,confirmation:confirmInput.value});toast(out.status==='completed'?'操作已执行。':'未完成执行，请核对操作结果及备份。');},'btn primary'));
      row.append(button('拒绝',async()=>{await action('decide',{operation_id:op.id,approve:false});toast('已拒绝。');},'btn danger-text'));card.append(row);
    }
    if(op.result?.backup_created && !['pending','executing'].includes(op.status)){
      card.append(button('从备份恢复为新文件', async()=>{
        const dest=prompt('在原授权目录内恢复为哪个相对路径？必须是尚不存在的路径，并保留原扩展名。',op.args.path);
        if(!dest)return;
        const confirmation=prompt('请再次输入恢复目标的完整文件名（含扩展名）确认：');
        if(confirmation===null)return;
        const out=await action('restore_backup',{operation_id:op.id,destination:dest,confirmation});
        toast('已恢复到 '+out.path+'；备份继续保留。');
      }));
    }
    host.append(card);
  }
}
function renderAudit(){const body=$('audit-body');body.replaceChildren();for(const a of state.audit){const tr=el('tr');[date(a.at),a.origin,a.action,a.path||'—',a.status+(a.code?' · '+a.code:'')].forEach(t=>tr.append(el('td','',t)));body.append(tr);}if(!state.audit.length){const tr=el('tr');const td=el('td','muted','尚无调用记录。');td.colSpan=5;tr.append(td);body.append(tr);}}
function render(){
  $('app-version').textContent='本机运行 · v'+state.status.version;
  $('local-status').textContent=state.status.paused?'访问已暂停':'正在运行';$('root-count').textContent=state.roots.length;$('overview-roots').textContent=state.roots.length;
  $('pending-count').textContent=state.operations.filter(o=>o.status==='pending').length;
  $('mode-label').textContent=state.status.paused?'访问已暂停':state.status.writes_enabled?'操作需本机审批':'默认只读';$('mode-label').classList.toggle('warning',state.status.writes_enabled||state.status.paused);
  $('pause-btn').textContent=state.status.paused?'恢复访问':'暂停访问';$('writes-switch').checked=state.status.writes_enabled;
  const t=state.tunnel;const cfg=t.configuration||{};const running=t.process_running;let title='尚未启动';if(running)title=t.ready===true?'就绪检查通过':'进程运行中';if(!cfg.tunnel_id)title='尚未配置';$('tunnel-status').textContent=title;
  $('tunnel-detail').textContent=running?'健康：'+(t.healthy===true?'通过':t.healthy===false?'未通过':'未确认')+' · 就绪：'+(t.ready===true?'通过':t.ready===false?'未通过':'未确认'):'启动后仍需验证 ChatGPT 实际读取';
  $('last-call').textContent=state.last_mcp_call?date(state.last_mcp_call.at)+' · '+state.last_mcp_call.tool+' · '+state.last_mcp_call.status+'（本机收到的 MCP 调用，仍应核对验证字符串）':'尚未收到 MCP 工具调用。本机自检和本机预览不计入这里。';
  const rootSig=JSON.stringify(state.roots);if(render.rootSig!==rootSig){renderRoots();render.rootSig=rootSig;}
  renderOperations();renderAudit();
  $('pdf-state').textContent=state.pdf_component_installed?'已安装到本程序':'未安装到本程序';
  $('key-state').textContent='当前密钥：'+(t.key_present?'可用（不回显）':'未载入')+'；加密保存：'+(t.remembered?'是':'否');
  $('tunnel-log').textContent=(t.logs||[]).join('\n')||'尚无隧道日志。';
  $('local-endpoints').textContent='管理页 '+state.admin_url+'；MCP '+state.mcp_url+'。本机接口均需独立凭证，请勿直接公开到互联网。';
  if(!hydrated){$('tunnel-binary').value=cfg.binary||'';$('tunnel-id').value=cfg.tunnel_id||'';$('remember-key').checked=!!t.remembered;hydrated=true;}
}
async function refresh(){if(busyPoll)return;busyPoll=true;try{state=await request('/api/state');show('offline-warning',false);render();}catch(e){if(token)show('offline-warning');}finally{busyPoll=false;}}
function currentScope(){if(!$('file-root').value)throw new Error('请先授权并选择一个目录。');return {root_id:$('file-root').value,path:$('file-path').value.trim()};}
async function browse(more){const args=currentScope();fileMode='browse';const data=await tool('list_files',{...args,offset:more?(listOffset||0):0,limit:100});listOffset=data.next_offset;searchCursor='';$('file-list-title').textContent='目录：'+(args.path||'/');renderFiles(data.items,args.root_id,false,more);show('more-files',listOffset!==null);$('file-coverage').textContent='本次可见目录项 '+data.visible_total+'；过滤或不可用 '+data.excluded_or_unavailable+'。'+(data.listing_truncated?'目录过大，候选列表已截断。':'')+(data.note||'');}
async function search(more){const args=currentScope();fileMode='search';const data=await tool('search_files',{...args,query:$('search-query').value,mode:$('search-mode').value,cursor:more?searchCursor:'',limit:30});searchCursor=data.next_cursor||'';listOffset=null;$('file-list-title').textContent='搜索结果';renderFiles(data.matches,args.root_id,true,more);show('more-files',!!searchCursor);$('file-coverage').textContent='已检查 '+data.inspected_so_far+' / '+data.candidate_count+' 个候选路径；本次不支持 '+data.unsupported_this_call+'。'+(data.candidate_collection_truncated?'候选收集达到上限，建议缩小目录。':'')+' '+data.note+(data.errors.length?'\n异常：'+data.errors.map(e=>e.path+' ['+e.code+']').join('；'):'');}
function renderFiles(items,rootId,isSearch,append){const host=$('file-results');if(!append){host.replaceChildren();host.classList.remove('empty');}if(!items.length&&!host.children.length){host.append(el('p','muted','当前批次没有可显示的匹配。若存在“下一批”，请继续；空批次不等于完整搜索结束。'));return;}for(const f of items){const row=el('div','file-item');const isDir=f.type==='folder';row.append(el('span','file-icon',isDir?'▱':'≡'));const text=el('div','file-copy');text.append(el('div','file-name',f.name||f.path));text.append(el('p','',isSearch?(f.match==='content'?'提取行 '+f.line+' · ':'文件名匹配 · ')+(f.snippet||''):bytes(f.bytes)+' · '+date(f.modified)));row.append(text);row.append(button(isDir?'打开':'读取',async()=>{if(isDir){$('file-root').value=rootId;$('file-path').value=f.path;await browse(false);}else await read(rootId,f.path,1,false);}));host.append(row);}}
async function read(rootId,path,start,append){const data=await tool('read_file',{root_id:rootId,path,start_line:start,line_count:160,expected_sha256:append?(readContext?.sha256||''):''});readContext={rootId,path,next:data.next_start_line,sha256:data.sha256};$('reader-title').textContent=path;$('reader-meta').textContent=bytes(data.bytes)+' · SHA-256 '+data.sha256;$('reader-warnings').textContent=(data.extraction_truncated?'提取范围已截断。 ':'')+data.warnings.join(' ');const text=data.lines.map(l=>String(l.line).padStart(5,' ')+'  '+l.text).join('\n');$('reader-text').textContent=(append?$('reader-text').textContent+'\n':'')+text;show('reader-card');show('read-more',!!data.next_start_line);if(!append)$('reader-card').scrollIntoView({behavior:'smooth',block:'start'});}
async function makeDemo(){const out=await action('create_demo');const prompt='使用本机文件插件，读取 root_id='+out.root_id+' 中的 '+out.path+'，原样返回文件中的验证字符串。不要猜测；读取失败请明确说明。';$('demo-result').textContent='已在本机生成验证文件。\n期望字符串（不要提供给 ChatGPT）：'+out.verification+'\n\n仅把下面这段发送给 ChatGPT：\n'+prompt;show('demo-result');tab('overview');toast('验证文件已生成。把提示词发到启用该插件的新对话。');}
bind('pick-root',async()=>{const out=await action('pick_folder');if(out.path)$('root-path').value=out.path;});
bind('add-root',async()=>{await action('add_root',{path:$('root-path').value,alias:$('root-alias').value});$('root-path').value='';$('root-alias').value='';toast('已授权读取。');});
bind('pause-btn',async()=>{await action('mode',{paused:!state.status.paused});});
$('writes-switch').addEventListener('change',()=>run($('writes-switch'),async()=>{const enabled=$('writes-switch').checked;if(enabled&&!confirm('启用文件操作提案？执行仍需对应目录授权和逐项本机审批。启用后请刷新 ChatGPT 插件工具。')){$('writes-switch').checked=false;return;}await action('mode',{writes:enabled});toast(enabled?'已启用提案；请同时设置目标目录操作权限并刷新插件。':'已关闭操作，待审批提案已取消。');}));
bind('browse-btn',()=>browse(false));bind('search-btn',()=>search(false));bind('more-files',()=>fileMode==='browse'?browse(true):search(true));bind('parent-btn',async()=>{const p=$('file-path').value.replaceAll('\\','/').split('/').filter(Boolean);p.pop();$('file-path').value=p.join('/');await browse(false);});
bind('read-more',()=>read(readContext.rootId,readContext.path,readContext.next,true));
bind('demo-btn',makeDemo);bind('demo-btn-2',makeDemo);bind('refresh-approvals',async()=>{opsSignature='';});bind('backups-btn',async()=>{await action('open_backups');});
bind('pick-tunnel',async()=>{const out=await action('pick_tunnel');if(out.path)$('tunnel-binary').value=out.path;});
bind('install-tunnel',async()=>{if(!confirm('从 OpenAI 官方 GitHub 发布页下载适配本机的隧道客户端及配套组件？'))return;toast('正在下载并校验，首次安装可能需要几分钟。');const out=await action('install_tunnel');$('tunnel-binary').value=out.binary;$('diagnostic-output').textContent=JSON.stringify(out,null,2);toast('下载已完成。继续填写 Tunnel ID 与运行密钥并保存。');});
bind('install-pdf',async()=>{toast('正在下载并校验 PDF 文字组件。');const out=await action('install_pdf');$('diagnostic-output').textContent=JSON.stringify(out,null,2);toast('PDF 组件已安装。');});
bind('save-tunnel',async()=>{await action('save_tunnel',{binary:$('tunnel-binary').value,tunnel_id:$('tunnel-id').value,key:$('tunnel-key').value,remember:$('remember-key').checked});$('tunnel-key').value='';toast('配置已保存。运行诊断后再启动隧道。');});
bind('doctor-btn',async()=>{$('diagnostic-output').textContent='正在运行官方 doctor…';const out=await action('doctor');$('diagnostic-output').textContent=JSON.stringify(out,null,2);});
bind('start-tunnel',async()=>{const out=await action('start_tunnel');$('diagnostic-output').textContent=JSON.stringify(out,null,2);toast('已请求启动。等待健康与就绪状态，再进行真实读取验证。');});
bind('stop-tunnel',async()=>{await action('stop_tunnel');toast('隧道已停止。');});
bind('forget-key',async()=>{if(confirm('停止隧道并清除内存及加密保存的运行密钥？')){await action('forget_key');$('tunnel-key').value='';toast('已清除运行密钥。');}});
bind('selftest-btn',async()=>{const out=await action('self_test');$('diagnostic-output').textContent=JSON.stringify(out,null,2);toast(out.passed?'本机 MCP 自检通过；尚不代表 ChatGPT 连接成功。':'自检未通过，请查看诊断输出。');});
bind('shutdown-btn',async()=>{if(confirm('停止本机服务和本次隧道？待审批提案将取消。')){await action('shutdown');toast('正在退出。重新启动请双击 START.cmd。');}});
$('search-query').addEventListener('keydown',e=>{if(e.key==='Enter')$('search-btn').click();});
show('auth-warning',!token);if(token){refresh();setInterval(refresh,4000);}
