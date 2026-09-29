"""Isolated regression tests. No personal directories, credentials or external network.
Run from the project root: python -m unittest discover -s tests -v
"""
from __future__ import annotations
import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import zipfile

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP/'third_party'))
from bridge import __version__
from bridge.security import (BridgeError, relative_parts, blocked_name, normalize_root,
                             resolve_scoped, read_bytes, identity, MAX_FILE_BYTES)
from tools.fixtures import isolated_directory
from bridge.engine import Engine
from bridge.extractors import extract, safe_zip, xml, decode_text
from bridge.protocol import Protocol, READ_TOOLS, WRITE_TOOLS, OUT, PROTOCOL_VERSIONS
from bridge.http_server import Application
from bridge import downloads
from bridge.tunnel import Tunnel


def zipped(parts):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items(): z.writestr(name, content)
    return out.getvalue()


def small_pdf(text='Local bridge PDF fixture'):
    stream = ('BT /F1 12 Tf 40 740 Td ('+text+') Tj ET').encode('ascii')
    objs = [b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    b = bytearray(b'%PDF-1.4\n'); offsets=[0]
    for i, obj in enumerate(objs,1):
        offsets.append(len(b)); b.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(b); b.extend(f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: b.extend(f'{offset:010} 00000 n \n'.encode())
    b.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(b)


def docx_fixture():
    return zipped({'word/document.xml':'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>中文正文</w:t><w:tab/><w:t>第二列</w:t><w:br/><w:t>换行</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>单元格甲</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>单元格乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''',
        'word/header1.xml': '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>页眉</w:t></w:r></w:p></w:hdr>'})


def xlsx_fixture():
    return zipped({'xl/workbook.xml': '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="测试表" sheetId="1" r:id="r1" state="hidden"/></sheets></workbook>''',
        'xl/_rels/workbook.xml.rels':'<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/sharedStrings.xml':'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>共享中文</t></si></sst>',
        'xl/worksheets/sheet1.xml':'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>1+2</f><v>3</v></c><c r="C1" t="inlineStr"><is><t>内联中文</t></is></c></row></sheetData></worksheet>'''})


def pptx_fixture():
    slide=lambda t: f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:sld>'
    return zipped({'ppt/presentation.xml':'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="2" r:id="r2"/><p:sldId id="1" r:id="r1"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels':'<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>',
        'ppt/slides/slide1.xml':slide('第二张'), 'ppt/slides/slide2.xml':slide('第一张')})


class Base(unittest.TestCase):
    def setUp(self):
        self.temp=isolated_directory(prefix='lfb-case-')
        self.base=Path(self.temp.name); self.folder=self.base/'project'; self.folder.mkdir()
        self.e=Engine(self.base/'state', APP)
        self.rid=self.e.add_root(str(self.folder),'测试资料')['root_id']
        self.root=self.e.root(self.rid); self.p=Protocol(self.e)
    def tearDown(self): self.temp.cleanup()
    def file(self, name='a.md', content='原文\n第二行\n'):
        p=self.folder/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(content if isinstance(content,bytes) else content.encode('utf-8'));return p
    def enable(self): self.e.set_mode(writes=True);self.e.root_writable(self.rid,True)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(BridgeError) as cm: fn(*args,**kwargs)
        self.assertEqual(cm.exception.code,code)
    def propose(self,kind='write',path='new.md',**kw):
        return self.e.propose(kind,self.rid,path,reason='明确的本机测试请求',**kw)
    def approve(self,op,path):return self.e.decide(op['operation_id'],True,Path(path.replace('\\','/')).name)


class PathPolicyTests(Base):
    def test_read_root_identity(self): self.assertEqual(resolve_scoped(self.root,''),self.folder)
    def test_unicode_valid_path(self): self.assertEqual(relative_parts('报告/结论.md'),('报告','结论.md'))
    def test_windows_separators(self): self.assertEqual(relative_parts('folder\\a.md'),('folder','a.md'))
    def test_empty_root_valid(self): self.assertEqual(relative_parts(''),())
    def test_dot_root_valid(self): self.assertEqual(relative_parts('.'),())
    def test_root_overlap(self):
        child=self.folder/'child';child.mkdir();self.error('OVERLAPPING_ROOT',self.e.add_root,str(child))
    def test_root_filesystem_anchor(self): self.error('ROOT_TOO_BROAD',normalize_root,str(self.folder.anchor),self.base/'state',APP)
    def test_root_user_home(self): self.error('ROOT_TOO_BROAD',normalize_root,str(Path.home()),self.base/'state',APP)
    def test_root_program_protected(self):
        # An ordinary name is used so the explicit protected-root branch is tested.
        program=self.base/'code';program.mkdir();self.error('PROTECTED_ROOT',normalize_root,str(program),self.base/'state',program)
    def test_root_state_ancestor(self): self.error('PROTECTED_ROOT',normalize_root,str(self.base),self.base/'state',APP)
    def test_root_removed(self): self.e.remove_root(self.rid);self.error('ROOT_NOT_AUTHORIZED',self.e.root,self.rid)
    def test_root_replaced(self):
        self.folder.rename(self.base/'old');self.folder.mkdir();self.error('ROOT_CHANGED',resolve_scoped,self.root,'')
    def test_missing_leaf_allowed(self): self.assertEqual(resolve_scoped(self.root,'new.md',missing_leaf=True),self.folder/'new.md')
    def test_missing_parent_rejected(self): self.error('NOT_FOUND',resolve_scoped,self.root,'missing/new.md',missing_leaf=True)
    def test_symlink_file_blocked(self):
        target=self.base/'outside.md';target.write_text('outside',encoding='utf-8');link=self.folder/'link.md'
        try:link.symlink_to(target)
        except OSError:self.skipTest('OS does not allow symbolic links for this test user')
        self.error('LINK_BLOCKED',read_bytes,self.root,'link.md')
    def test_symlink_directory_blocked(self):
        target=self.base/'outside';target.mkdir();link=self.folder/'link'
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:self.skipTest('OS does not allow symbolic links for this test user')
        self.error('LINK_BLOCKED',resolve_scoped,self.root,'link')
    def test_hardlink_blocked(self):
        f=self.file();os.link(f,self.folder/'linked.md');self.error('HARDLINK_BLOCKED',read_bytes,self.root,'a.md')
    def test_file_too_big(self):
        with self.file().open('wb') as f:f.truncate(MAX_FILE_BYTES+1)
        self.error('FILE_TOO_LARGE',read_bytes,self.root,'a.md')
    def test_directory_not_file(self): self.error('NOT_A_FILE',read_bytes,self.root,'')
    def test_hidden_filtered(self): self.file('.env','secret');self.file('ok.md','ok');self.assertEqual([f['name'] for f in self.e.list_files()['items']],['ok.md'])
    def test_binary_extensions_listable(self):self.file('photo.png',b'xxx');self.assertFalse(self.e.list_files()['items'][0]['readable_format'])
    def test_no_absolute_paths_in_status(self):self.assertNotIn(str(self.folder),json.dumps(self.e.status()))

BAD_PATHS=['../a.md','a/../../b','/etc/passwd','C:\\Windows\\x','C:relative','\\\\host\\share','\\?\\C:\\test','a\x00b','a:b','file.txt:stream','a//b','a/./b','a/../b','a/','a.','a ','CON','con.md','NUL','LPT1.txt','COM9','a*','a?','a<','a>','a|','a"','line\nfeed','.env','.git/config','node_modules/a','id_rsa','key.pem','secrets.json','credentials.csv','Passwords.txt','a.lnk','a.url','a/'*65+'end.md']
for n,value in enumerate(BAD_PATHS):
    def case(self,value=value):
        with self.assertRaises(BridgeError):relative_parts(value)
    setattr(PathPolicyTests,f'test_reject_path_{n:02d}',case)


class ReadAndSearchTests(Base):
    def test_read_real_parser_process(self):
        self.file();out=self.e.read_file(path='a.md');self.assertEqual(out['lines'][0]['text'],'原文');self.assertTrue(out['untrusted_content'])
    def test_read_hash(self):
        p=self.file();self.assertEqual(self.e.read_file(path='a.md')['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
    def test_read_pagination(self):
        self.file(content='\n'.join(map(str,range(420))));a=self.e.read_file(path='a.md',line_count=100);b=self.e.read_file(path='a.md',start_line=a['next_start_line'],expected_sha256=a['sha256'])
        self.assertEqual(a['next_start_line'],101);self.assertEqual(b['lines'][0]['text'],'100')
    def test_read_version_change(self):
        p=self.file();a=self.e.read_file(path='a.md');p.write_text('changed',encoding='utf-8');self.error('CONFLICT',self.e.read_file,path='a.md',expected_sha256=a['sha256'])
    def test_read_range(self):self.file();self.error('LINE_RANGE',self.e.read_file,path='a.md',start_line=999)
    def test_read_long_line_progress(self):
        self.file(content='x'*50000);out=self.e.read_file(path='a.md');self.assertTrue(out['next_start_line']);self.assertLessEqual(sum(len(x['text'])+1 for x in out['lines']),40000)
    def test_read_empty(self):self.file(content='');self.assertEqual(self.e.read_file(path='a.md')['lines'],[])
    def test_utf16_process(self):self.file('utf.txt','中文'.encode('utf-16'));self.assertEqual(self.e.read_file(path='utf.txt')['lines'][0]['text'],'中文')
    def test_gb18030_process(self):self.file('gb.txt','中文'.encode('gb18030'));self.assertEqual(self.e.read_file(path='gb.txt')['lines'][0]['text'],'中文')
    def test_binary_not_text(self):self.file('bin.txt',b'a\x00b');self.error('BINARY_FILE',self.e.read_file,path='bin.txt')
    def test_unsupported_format(self):self.file('x.exe',b'MZ');self.error('UNSUPPORTED_FORMAT',self.e.read_file,path='x.exe')
    def test_html_is_inert(self):
        self.file('x.html','<script>document.body.remove()</script>');out=self.e.read_file(path='x.html');self.assertIn('<script>',out['lines'][0]['text']);self.assertTrue(out['warnings'])
    def test_read_paused(self):self.file();self.e.set_mode(paused=True);self.error('PAUSED',self.e.read_file,path='a.md')
    def test_list_pagination(self):
        for x in range(7):self.file(f'{x}.md')
        a=self.e.list_files(limit=3);b=self.e.list_files(offset=a['next_offset'],limit=3);self.assertEqual(len(a['items']),3);self.assertNotEqual(a['items'][0]['name'],b['items'][0]['name'])
    def test_list_folder_first(self):self.file('a.md');(self.folder/'zfolder').mkdir();self.assertEqual(self.e.list_files()['items'][0]['type'],'folder')
    def test_list_multiple_roots_requires_selection(self):
        other=self.base/'other';other.mkdir();self.e.add_root(str(other));out=self.e.list_files();self.assertEqual(len(out['roots']),2);self.assertEqual(out['items'],[])
    def test_search_name(self):self.file('唯一报告.md');out=self.e.search_files('唯一',mode='name');self.assertEqual(out['matches'][0]['match'],'name')
    def test_search_content(self):self.file(content='needle 中文');out=self.e.search_files('needle',mode='content');self.assertEqual(out['matches'][0]['line'],1)
    def test_search_nested(self):self.file('folder/a.md','nestedword');self.assertEqual(self.e.search_files('nestedword')['matches'][0]['path'],'folder/a.md')
    def test_search_pages(self):
        for n in range(7):self.file(f'hit-{n}.md','content')
        a=self.e.search_files('hit',mode='name',limit=2);b=self.e.search_files('hit',mode='name',cursor=a['next_cursor'],limit=2)
        self.assertEqual(a['inspected_so_far'],2);self.assertEqual(b['inspected_so_far'],4);self.assertNotEqual(a['matches'],b['matches'])
    def test_search_cursor_mismatch(self):
        for n in range(3):self.file(f'hit{n}.md')
        a=self.e.search_files('hit',mode='name',limit=1);self.error('CURSOR_MISMATCH',self.e.search_files,'other',mode='name',cursor=a['next_cursor'])
    def test_search_expired(self):self.error('CURSOR_EXPIRED',self.e.search_files,'a',cursor='unknown')
    def test_search_empty(self):self.error('EMPTY_QUERY',self.e.search_files,' ')
    def test_search_unsupported_reported(self):self.file('x.exe',b'MZ');self.assertEqual(self.e.search_files('q',mode='content')['unsupported_this_call'],1)
    def test_search_parse_error_reported(self):self.file('x.docx',b'badzip');self.assertEqual(self.e.search_files('q')['errors'][0]['code'],'PARSE_FAILED')
    def test_docx_worker(self):self.file('x.docx',docx_fixture());self.assertIn('中文正文',str(self.e.read_file(path='x.docx')['lines']))
    def test_xlsx_worker(self):self.file('x.xlsx',xlsx_fixture());self.assertIn('公式=1+2',str(self.e.read_file(path='x.xlsx')['lines']))
    def test_pptx_worker(self):self.file('x.pptx',pptx_fixture());self.assertIn('第一张',str(self.e.read_file(path='x.pptx')['lines']))
    def test_parser_timeout(self):
        self.file()
        with patch('bridge.engine.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',12)):self.error('PARSE_TIMEOUT',self.e.read_file,path='a.md')
    def test_parser_busy(self):
        self.file();self.e._parse_slots.acquire();self.e._parse_slots.acquire()
        try:self.error('BUSY',self.e.read_file,path='a.md')
        finally:self.e._parse_slots.release();self.e._parse_slots.release()


class ExtractionTests(unittest.TestCase):
    def test_docx_body_table_header(self):
        t='\n'.join(extract(docx_fixture(),'.docx')['lines']);self.assertIn('中文正文\t第二列\n换行',t);self.assertIn('单元格甲 | 单元格乙',t);self.assertIn('页眉',t)
    def test_xlsx_cells_formulas_hidden(self):
        t='\n'.join(extract(xlsx_fixture(),'.xlsx')['lines']);self.assertIn('状态 hidden',t);self.assertIn('A1=共享中文',t);self.assertIn('B1=公式=1+2；缓存值=3',t);self.assertIn('C1=内联中文',t)
    def test_pptx_order(self):
        t='\n'.join(extract(pptx_fixture(),'.pptx')['lines']);self.assertLess(t.index('第一张'),t.index('第二张'))
    def test_xml_entity_block(self):
        with self.assertRaises(BridgeError):xml(b'<!DOCTYPE a [<!ENTITY x "unsafe">]><a>&x;</a>')
    def test_utf16_xml_entity_block(self):
        with self.assertRaises(BridgeError):xml('<!DOCTYPE a><a/>'.encode('utf-16'))
    def test_zip_traversal(self):
        with self.assertRaises(BridgeError):safe_zip(zipped({'../bad':'x'}))
    def test_zip_duplicate(self):
        out=io.BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(out,'w') as z:z.writestr('x','a');z.writestr('x','b')
        with self.assertRaises(BridgeError):safe_zip(out.getvalue())
    def test_zip_bomb_ratio(self):
        with self.assertRaises(BridgeError):safe_zip(zipped({'x':b'a'*2000000}))
    def test_extraction_truncated(self):self.assertTrue(extract(b'a'*1005000,'.txt')['extraction_truncated'])
    def test_long_line_split(self):self.assertEqual(len(extract(b'a'*8001,'.txt')['lines']),3)
    def test_utf16_binary_rejected(self):
        with self.assertRaises(BridgeError):decode_text('a\0b'.encode('utf-16'))
    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Optional pypdf not installed')
    def test_pdf_text(self):self.assertIn('Local bridge PDF fixture',' '.join(extract(small_pdf(),'.pdf')['lines']))
    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Optional pypdf not installed')
    def test_pdf_empty_text_warning(self):self.assertTrue(any('未发现' in w for w in extract(small_pdf(''),'.pdf')['warnings']))


class OperationTests(Base):
    def test_default_readonly(self):self.error('READ_ONLY',self.propose,content='new')
    def test_global_gate_only_insufficient(self):self.e.set_mode(writes=True);self.error('READ_ONLY',self.propose,content='new')
    def test_root_gate_only_insufficient(self):self.e.root_writable(self.rid,True);self.error('READ_ONLY',self.propose,content='new')
    def test_proposal_is_not_execution(self):
        self.enable();op=self.propose(content='new');self.assertFalse(op['executed']);self.assertFalse((self.folder/'new.md').exists())
    def test_create_approved(self):
        self.enable();op=self.propose(content='新内容');self.assertEqual(self.approve(op,'new.md')['status'],'completed');self.assertEqual((self.folder/'new.md').read_text(encoding='utf-8'),'新内容')
    def test_explicit_confirmation_required(self):
        self.enable();op=self.propose(content='new');self.error('CONFIRMATION_REQUIRED',self.e.decide,op['operation_id'],True,'wrong');self.assertFalse((self.folder/'new.md').exists())
    def test_reject(self):
        self.enable();op=self.propose(content='new');self.assertFalse(self.e.decide(op['operation_id'],False)['executed']);self.assertFalse((self.folder/'new.md').exists())
    def test_expiry(self):
        self.enable();op=self.propose(content='new')
        with self.e.store.db() as db:db.execute('UPDATE operations SET expires=0')
        self.error('ALREADY_HANDLED',self.approve,op,'new.md');self.assertEqual(self.e.get_operation(op['operation_id'])['status'],'expired')
    def test_repeat_approval(self):
        self.enable();op=self.propose(content='new');self.approve(op,'new.md');self.error('ALREADY_HANDLED',self.approve,op,'new.md')
    def test_overwrite_needs_hash(self):self.file();self.enable();self.error('HASH_REQUIRED',self.propose,path='a.md',content='new')
    def test_wrong_hash(self):self.file();self.enable();self.error('CONFLICT',self.propose,path='a.md',content='new',expected_sha256='0'*64)
    def test_backup_before_overwrite(self):
        f=self.file();original=f.read_bytes();self.enable();op=self.propose(path='a.md',content='new',expected_sha256=hashlib.sha256(original).hexdigest());out=self.approve(op,'a.md')
        self.assertEqual(f.read_text(encoding='utf-8'),'new');self.assertEqual((Path(out['backup_directory'])/'original.bin').read_bytes(),original)
    def test_change_during_approval(self):
        f=self.file();self.enable();op=self.propose(path='a.md',content='new',expected_sha256=hashlib.sha256(f.read_bytes()).hexdigest());f.write_text('user edit',encoding='utf-8');out=self.approve(op,'a.md')
        self.assertEqual(out['status'],'failed');self.assertEqual(f.read_text(encoding='utf-8'),'user edit');self.assertFalse(out['state_unknown'])
    def test_new_target_conflict(self):
        self.enable();op=self.propose(content='new');self.file('new.md','other');self.assertEqual(self.approve(op,'new.md')['status'],'failed');self.assertEqual((self.folder/'new.md').read_text(encoding='utf-8'),'other')
    def test_write_script_blocked(self):self.enable();self.error('WRITE_FORMAT',self.propose,path='run.py',content='print(1)')
    def test_write_limit_utf8_bytes(self):self.enable();self.error('WRITE_LIMIT',self.propose,content='中'*100000)
    def test_new_directory(self):self.enable();op=self.propose('mkdir','newfolder');self.approve(op,'newfolder');self.assertTrue((self.folder/'newfolder').is_dir())
    def test_mkdir_missing_parent(self):self.enable();self.error('NOT_FOUND',self.propose,'mkdir','notcreated/child')
    def test_mkdir_no_overwrite(self):self.enable();self.file();self.error('ALREADY_EXISTS',self.propose,'mkdir','a.md')
    def test_move_file(self):
        f=self.file();self.enable();op=self.propose('move','a.md',destination='renamed.md');out=self.approve(op,'a.md');self.assertEqual(out['status'],'completed');self.assertFalse(f.exists());self.assertTrue((self.folder/'renamed.md').exists())
    def test_move_no_overwrite(self):self.file();self.file('b.md');self.enable();self.error('ALREADY_EXISTS',self.propose,'move','a.md',destination='b.md')
    def test_move_no_extension_change(self):self.file();self.enable();self.error('EXTENSION_CHANGE',self.propose,'move','a.md',destination='run.cmd')
    def test_move_not_directory(self):
        (self.folder/'sub').mkdir();self.enable();self.error('NOT_A_FILE',self.propose,'move','sub',destination='renamed')
    def test_quarantine_and_restore(self):
        f=self.file();raw=f.read_bytes();self.enable();op=self.propose('trash','a.md');out=self.approve(op,'a.md');self.assertEqual(out['status'],'completed');self.assertFalse(f.exists());self.assertEqual((Path(out['backup_directory'])/'original.bin').read_bytes(),raw)
        restored=self.e.restore_backup(op['operation_id'],'restored.md','restored.md');self.assertTrue(restored['restored']);self.assertEqual((self.folder/'restored.md').read_bytes(),raw)
    def test_restore_no_overwrite(self):
        f=self.file();self.enable();op=self.propose('trash','a.md');self.approve(op,'a.md');self.file('restore.md','other');self.error('ALREADY_EXISTS',self.e.restore_backup,op['operation_id'],'restore.md','restore.md')
    def test_restore_hash_tamper(self):
        self.file();self.enable();op=self.propose('trash','a.md');out=self.approve(op,'a.md');(Path(out['backup_directory'])/'original.bin').write_bytes(b'tamper');self.error('BACKUP_FAILED',self.e.restore_backup,op['operation_id'],'restore.md','restore.md')
    def test_restore_no_script(self):
        self.file();self.enable();op=self.propose('trash','a.md');self.approve(op,'a.md');self.error('EXTENSION_CHANGE',self.e.restore_backup,op['operation_id'],'run.py','run.py')
    def test_remote_no_backup_absolute_path(self):
        self.file();self.enable();op=self.propose('trash','a.md');self.approve(op,'a.md');self.assertNotIn(str(self.base),json.dumps(self.e.get_operation(op['operation_id'])))
    def test_pending_dedup(self):
        self.enable();a=self.propose(content='a',request_id='unique');b=self.propose(content='a',request_id='unique');self.assertEqual(a['operation_id'],b['operation_id']);self.assertTrue(b['duplicate'])
    def test_reused_id_other_contents(self):
        self.enable();self.propose(content='a',request_id='unique');self.error('REQUEST_ID_REUSED',self.propose,content='b',request_id='unique')
    def test_terminal_id_not_replayed(self):
        self.enable();op=self.propose('mkdir','dir',request_id='unique');self.e.decide(op['operation_id'],False);self.error('REQUEST_ID_REUSED',self.propose,'mkdir','dir',request_id='unique')
    def test_pause_cancels(self):self.enable();op=self.propose(content='x');self.e.set_mode(paused=True);self.assertEqual(self.e.get_operation(op['operation_id'])['status'],'cancelled')
    def test_disable_cancels(self):self.enable();op=self.propose(content='x');self.e.set_mode(writes=False);self.assertEqual(self.e.get_operation(op['operation_id'])['status'],'cancelled')
    def test_remove_root_cancels(self):self.enable();op=self.propose(content='x');self.e.remove_root(self.rid);self.assertEqual(self.e.get_operation(op['operation_id'])['status'],'cancelled')
    def test_terminal_content_removed(self):
        self.enable();op=self.propose(content='SECRET_CONTENT');self.approve(op,'new.md');self.assertNotIn('content',self.e.store.operations()[0]['args'])
    def test_crash_state_no_replay(self):
        self.enable();op=self.propose(content='x')
        with self.e.store.db() as db:db.execute("UPDATE operations SET status='executing'")
        self.e.store.recover_interrupted();out=self.e.get_operation(op['operation_id']);self.assertEqual(out['status'],'interrupted');self.assertTrue(out['result']['state_unknown']);self.assertFalse((self.folder/'new.md').exists())
    def test_audit_no_content_query_secrets(self):
        self.file(content='sensitive-body');self.p.call('search_files',{'query':'sensitive-body'});self.assertNotIn('sensitive-body',json.dumps(self.e.store.audit()))
    def test_backup_disk_space_failure(self):
        self.file();self.enable();op=self.propose('trash','a.md')
        with patch('bridge.engine.shutil.disk_usage',return_value=types.SimpleNamespace(free=0)):
            out=self.approve(op,'a.md')
        self.assertEqual(out['status'],'failed');self.assertTrue((self.folder/'a.md').exists())


class ProtocolTests(Base):
    def rpc(self,method,params=None):return self.p.dispatch({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})
    def test_version(self):self.assertEqual(self.rpc('initialize',{'protocolVersion':'2025-11-25'})['result']['serverInfo']['version'],__version__)
    def test_version_negotiation(self):self.assertEqual(self.rpc('initialize',{'protocolVersion':'future'})['result']['protocolVersion'],PROTOCOL_VERSIONS[0])
    def test_notification(self):self.assertIsNone(self.p.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'}))
    def test_invalid_request(self):self.assertEqual(self.p.dispatch([])['error']['code'],-32600)
    def test_invalid_id_bool(self):self.assertEqual(self.p.dispatch({'jsonrpc':'2.0','id':True,'method':'ping'})['error']['code'],-32600)
    def test_unknown_method(self):self.assertEqual(self.rpc('admin/approve')['error']['code'],-32601)
    def test_read_tool_count(self):self.assertEqual(len(self.rpc('tools/list')['result']['tools']),5)
    def test_write_tool_count(self):self.enable();self.assertEqual(len(self.p.tools()),9)
    def test_read_annotations(self):self.assertTrue(all(t['annotations']['readOnlyHint'] and not t['annotations']['openWorldHint'] for t in READ_TOOLS))
    def test_write_annotations(self):self.assertTrue(all(not t['annotations']['readOnlyHint'] for t in WRITE_TOOLS))
    def test_schemas(self):self.assertTrue(all(t['outputSchema']==OUT and t['inputSchema']['additionalProperties'] is False for t in READ_TOOLS+WRITE_TOOLS))
    def test_no_remote_administration(self):
        for n in ('decide','add_root','restore_backup','exec','shell','run_command','remove_root','save_tunnel'):
            self.assertTrue(self.p.call(n,{})['isError'])
    def test_unknown_argument(self):self.assertTrue(self.p.call('get_status',{'unexpected':True})['isError'])
    def test_integer_bool_invalid(self):self.assertTrue(self.p.call('list_files',{'limit':True})['isError'])
    def test_limit_bounded(self):self.assertTrue(self.p.call('list_files',{'limit':999})['isError'])
    def test_required_path(self):self.assertTrue(self.p.call('read_file',{})['isError'])
    def test_enum(self):self.assertTrue(self.p.call('search_files',{'query':'a','mode':'regex'})['isError'])
    def test_string_limit(self):self.assertTrue(self.p.call('search_files',{'query':'a'*201})['isError'])
    def test_output_pair_consistency(self):
        out=self.p.call('get_status',{});self.assertEqual(json.loads(out['content'][0]['text']),out['structuredContent'])
    def test_protocol_no_root_leak(self):self.assertNotIn(str(self.folder),json.dumps(self.rpc('tools/call',{'name':'get_status','arguments':{}})))
    def test_error_no_absolute_path(self):self.assertNotIn(str(self.folder),json.dumps(self.p.call('read_file',{'path':'missing.md'})))
    def test_calls_have_audit(self):self.p.call('get_status',{});self.assertEqual(self.e.store.audit()[0]['origin'],'mcp')
    def test_selftest_not_counted_remote(self):self.p.call('get_status',{},origin='local-self-test');self.assertIsNone(self.e.last_mcp_call)
    def test_latest_call_tracked(self):self.p.call('get_status',{});self.assertEqual(self.e.last_mcp_call['tool'],'get_status')


class HTTPTests(Base):
    def setUp(self):super().setUp();self.app=Application(self.e,0,0);self.app.start()
    def tearDown(self):self.app.close();super().tearDown()
    def req(self,mcp=False,method='GET',path='/',body=None,headers=None,auth=True):
        port=self.app.mcp_port if mcp else self.app.admin_port
        h={}
        if auth:h['Authorization']='Bearer '+(self.app.mcp_token if mcp else self.app.admin_token)
        if body is not None:
            if not isinstance(body,(str,bytes)):body=json.dumps(body)
            h.update({'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
        h.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
        try:
            c.request(method,path,body=body,headers=h);r=c.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:c.close()
    def msg(self,m,p=None):return {'jsonrpc':'2.0','id':1,'method':m,'params':p or {}}
    def test_static_public_no_data(self):s,h,b=self.req(auth=False);self.assertEqual(s,200);self.assertNotIn(self.app.admin_token.encode(),b)
    def test_state_requires_auth(self):self.assertEqual(self.req(path='/api/state',auth=False)[0],401)
    def test_mcp_requires_auth(self):self.assertEqual(self.req(True,'POST','/mcp',self.msg('ping'),auth=False)[0],401)
    def test_admin_token_not_mcp_token(self):self.assertEqual(self.req(True,'POST','/mcp',self.msg('ping'),headers={'Authorization':'Bearer '+self.app.admin_token})[0],401)
    def test_mcp_token_not_admin_token(self):self.assertEqual(self.req(path='/api/state',headers={'Authorization':'Bearer '+self.app.mcp_token})[0],401)
    def test_invalid_host(self):self.assertEqual(self.req(headers={'Host':'evil.test'})[0],403)
    def test_invalid_origin(self):self.assertEqual(self.req(headers={'Origin':'https://evil.test'})[0],403)
    def test_null_origin(self):self.assertEqual(self.req(headers={'Origin':'null'})[0],403)
    def test_missing_origin_cli_ok(self):self.assertEqual(self.req(path='/api/state')[0],200)
    def test_wrong_content_type(self):self.assertEqual(self.req(True,'POST','/mcp','{}',headers={'Content-Type':'text/plain'})[0],415)
    def test_accept_contract(self):self.assertEqual(self.req(True,'POST','/mcp',self.msg('ping'),headers={'Accept':'application/json'})[0],406)
    def test_version_header_reject(self):self.assertEqual(self.req(True,'POST','/mcp',self.msg('ping'),headers={'MCP-Protocol-Version':'unknown'})[0],400)
    def test_malformed_json(self):self.assertEqual(self.req(True,'POST','/mcp','{bad')[0],400)
    def test_null_json(self):self.assertEqual(self.req(True,'POST','/mcp','null')[0],400)
    def test_notification_202(self):self.assertEqual(self.req(True,'POST','/mcp',{'jsonrpc':'2.0','method':'notifications/initialized'})[0],202)
    def test_get_mcp_405(self):self.assertEqual(self.req(True,'GET','/mcp')[0],405)
    def test_cors_options_denied(self):self.assertEqual(self.req(method='OPTIONS')[0],405)
    def test_delete_stateless_405(self):self.assertEqual(self.req(True,'DELETE','/mcp')[0],405)
    def test_security_headers(self):
        s,h,b=self.req();self.assertEqual(h['X-Frame-Options'],'DENY');self.assertIn("script-src 'self'",h['Content-Security-Policy']);self.assertEqual(h['Cache-Control'],'no-store');self.assertNotIn('Access-Control-Allow-Origin',h)
    def test_static_traversal(self):self.assertEqual(self.req(path='/../app.py')[0],404)
    def test_remote_admin_not_routed(self):self.assertEqual(self.req(True,'POST','/api/action',{'action':'add_root','args':{}})[0],404)
    def test_local_self_test(self):self.assertTrue(self.app.self_test()['passed']);self.assertIsNone(self.e.last_mcp_call)
    def test_actual_http_read(self):
        self.file('check.md','http nonce 7dc982');s,h,b=self.req(True,'POST','/mcp',self.msg('tools/call',{'name':'read_file','arguments':{'path':'check.md'}}));self.assertEqual(s,200);self.assertIn('http nonce 7dc982',b.decode());self.assertEqual(self.e.last_mcp_call['tool'],'read_file')
    def test_local_action_type_check(self):self.assertEqual(self.req(False,'POST','/api/action',{'action':'mode','args':{'writes':'yes'}})[0],400)
    def test_restoration_not_mcp_tool(self):
        s,h,b=self.req(True,'POST','/mcp',self.msg('tools/call',{'name':'restore_backup','arguments':{}}));self.assertTrue(json.loads(b)['result']['isError'])
    def test_readonly_approval_closed(self):
        s,h,b=self.req(True,'POST','/mcp',self.msg('tools/call',{'name':'propose_write_file','arguments':{'path':'x.md','content':'x','reason':'test'}}));self.assertTrue(json.loads(b)['result']['isError'])
    def test_request_too_large(self):self.assertEqual(self.req(True,'POST','/mcp','',{'Content-Length':str(512*1024+1)})[0],413)


class ComponentTests(unittest.TestCase):
    def test_download_https_only(self):
        with self.assertRaises(BridgeError):downloads.check_url('http://github.com/a')
    def test_download_domain_allowlist(self):
        with self.assertRaises(BridgeError):downloads.check_url('https://example.com/a')
    def test_download_userinfo_denied(self):
        with self.assertRaises(BridgeError):downloads.check_url('https://user@github.com/a')
    def test_zip_safe_extract(self):
        with isolated_directory() as d:
            downloads.unpack(zipped({'folder/a.txt':'data'}),Path(d));self.assertEqual((Path(d)/'folder/a.txt').read_text(encoding='utf-8'),'data')
    def test_zip_component_traversal(self):
        with isolated_directory() as d:
            with self.assertRaises(BridgeError):downloads.unpack(zipped({'../x':'bad'}),Path(d))
    def test_zip_component_symlink(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../x')
        with isolated_directory() as d:
            with self.assertRaises(BridgeError):downloads.unpack(out.getvalue(),Path(d))
    def test_pdf_hash_mismatch(self):
        with isolated_directory() as d, patch.object(downloads,'fetch',return_value=b'wrong'):
            with self.assertRaises(BridgeError) as cm:downloads.install_pdf(Path(d))
            self.assertEqual(cm.exception.code,'HASH_MISMATCH')
    def test_pdf_installer_with_fixture(self):
        blob=zipped({'pypdf/__init__.py':'__version__="fixture"','pypdf-fixture.dist-info/METADATA':'Name: test'})
        with isolated_directory() as d,patch.object(downloads,'fetch',return_value=blob),patch.object(downloads,'PDF_SHA256',hashlib.sha256(blob).hexdigest()):
            self.assertTrue(downloads.install_pdf(Path(d))['installed']);self.assertTrue((Path(d)/'third_party/pypdf/__init__.py').exists())
    def test_tunnel_selects_full_not_runtime_flavors(self):
        blob=zipped({'tunnel-client.exe':b'MZ-fixture-not-executable','cloudflared.exe':b'MZ-fixture'})
        sha=hashlib.sha256(blob).hexdigest();assets=[]
        for prefix in ('tunnel-client','tunnel-client-runtime','tunnel-client-runtime-cloudflared'):
            name=prefix+'-v0.0.14-windows-amd64.zip';assets.append({'name':name,'digest':'sha256:'+sha,'browser_download_url':'https://github.com/openai/tunnel-client/releases/download/v0.0.14/'+name})
        meta=json.dumps({'tag_name':'v0.0.14','assets':assets}).encode()
        def fake(url,*args):return meta if url.endswith('/latest') else blob
        with isolated_directory() as d, patch.object(downloads,'fetch',side_effect=fake),patch.object(downloads,'os',types.SimpleNamespace(name='nt',environ={})),patch.object(downloads.platform,'machine',return_value='AMD64'):
            out=downloads.install_tunnel(Path(d));self.assertTrue(out['installed']);self.assertEqual(Path(out['binary']).name,'tunnel-client.exe')
    def test_tunnel_digest_mismatch_rejected(self):
        a={'name':'tunnel-client-v0.0.14-windows-amd64.zip','digest':'sha256:'+'0'*64,'browser_download_url':'https://github.com/openai/tunnel-client/x.zip'}
        def fake(url,*args):return json.dumps({'assets':[a]}).encode() if url.endswith('/latest') else b'bad'
        with isolated_directory() as d,patch.object(downloads,'fetch',side_effect=fake),patch.object(downloads,'os',types.SimpleNamespace(name='nt',environ={})),patch.object(downloads.platform,'machine',return_value='AMD64'):
            with self.assertRaises(BridgeError) as cm:downloads.install_tunnel(Path(d))
            self.assertEqual(cm.exception.code,'HASH_MISMATCH')


class TunnelConfigurationTests(Base):
    def setUp(self):
        super().setUp();self.t=Tunnel(self.e.store,'http://127.0.0.1:18766/mcp','localtoken');self.bin=self.base/('tunnel-client.exe' if os.name=='nt' else 'tunnel-client');self.bin.write_text('fixture only',encoding='utf-8')
    def test_bad_id(self):self.error('TUNNEL_ID_INVALID',self.t.save,str(self.bin),'asdk_app_123','key')
    def test_wrong_executable(self):self.error('BINARY_INVALID',self.t.save,str(self.base/'other.exe'),'tunnel_'+'a'*32,'key')
    def test_requires_runtime_key(self):self.t.save(str(self.bin),'tunnel_'+'a'*32);self.error('KEY_REQUIRED',self.t._prepare)
    def test_profile_uses_env_secrets(self):
        self.t.save(str(self.bin),'tunnel_'+'a'*32,'runtime-secret');_,env=self.t._prepare();profile=self.t.profile.read_text(encoding='utf-8');self.assertNotIn('runtime-secret',profile);self.assertNotIn('localtoken',profile);self.assertEqual(env['LOCALFOLDER_MCP_AUTH'],'Bearer localtoken')
    def test_no_proxy_for_loopback(self):
        self.t.save(str(self.bin),'tunnel_'+'a'*32,'key');_,env=self.t._prepare();self.assertIn('127.0.0.1',env['NO_PROXY'])
    def test_stale_privileged_env_removed(self):
        self.t.save(str(self.bin),'tunnel_'+'a'*32,'key')
        with patch.dict(os.environ,{'OPENAI_ADMIN_KEY':'admin','MCP_COMMAND':'danger','CONTROL_PLANE_BASE_URL':'http://wrong'}):
            _,env=self.t._prepare();self.assertNotIn('OPENAI_ADMIN_KEY',env);self.assertNotIn('MCP_COMMAND',env);self.assertNotIn('CONTROL_PLANE_BASE_URL',env)
    def test_logs_redacted(self):
        self.t.key='specific-runtime-key';out=self.t._redact('specific-runtime-key localtoken Bearer abc123 sk-test_123456789');self.assertNotIn('specific-runtime-key',out);self.assertNotIn('localtoken',out);self.assertNotIn('abc123',out)
    def test_config_no_key_plaintext(self):
        self.t.save(str(self.bin),'tunnel_'+'a'*32,'private-key');self.assertNotIn('private-key',json.dumps(self.e.store.get('tunnel')))
    def test_not_running_not_ready(self):self.assertFalse(self.t.status()['ready']);self.assertFalse(self.t.status()['process_running'])
    def test_forget_key(self):self.t.key='x';self.t.forget_key();self.assertFalse(self.t.status()['key_present'])


class StdioAndStartupTests(unittest.TestCase):
    def test_stdio_real_process(self):
        with isolated_directory(prefix='lfb-stdio-') as d:
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_status','arguments':{}}}]
            proc=subprocess.run([sys.executable,str(APP/'app.py'),'--stdio','--state-dir',d],input=''.join(json.dumps(x)+'\n' for x in messages).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            self.assertEqual(proc.returncode,0);rows=[json.loads(x) for x in proc.stdout.splitlines()];self.assertEqual(len(rows),3);self.assertEqual(len(rows[1]['result']['tools']),5);self.assertTrue(rows[2]['result']['structuredContent']['ok'])
    def test_launcher_no_security_bypass(self):
        text=(APP/'START.cmd').read_text(encoding='utf-8');self.assertNotIn('ExecutionPolicy Bypass',text);self.assertNotIn('Unblock-File',text);self.assertIn('Get-FileHash',text);self.assertIn('python.org',text)
    def test_version_consistency(self):
        # Assert the live interfaces, not duplicated version literals in sources.
        with isolated_directory(prefix='lfb-version-') as d:
            engine=Engine(Path(d),APP)
            self.assertEqual(engine.status()['version'],__version__)
            self.assertEqual(Protocol(engine).dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})['result']['serverInfo']['version'],__version__)

if __name__=='__main__':unittest.main(verbosity=2)
