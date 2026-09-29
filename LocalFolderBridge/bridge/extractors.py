"""Bounded text extraction. No Office automation, macros, external links or OCR."""
from __future__ import annotations
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from .security import BridgeError, MAX_TEXT_CHARS, TEXT_EXTENSIONS

MAX_XML_BYTES = 16 * 1024 * 1024
MAX_ZIP_BYTES = 64 * 1024 * 1024
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def xml(data: bytes):
    if len(data) > MAX_XML_BYTES:
        raise BridgeError('XML_LIMIT', 'XML 部件超过 16 MiB，未解析该文件。')
    # XML declarations may be UTF-16. Remove NUL solely for the DTD guard.
    guard = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in guard or b'<!ENTITY' in guard:
        raise BridgeError('UNSAFE_XML', '不解析含 DTD 或实体声明的 XML。')
    return ET.fromstring(data)

def safe_zip(blob: bytes):
    z = zipfile.ZipFile(io.BytesIO(blob))
    infos = z.infolist()
    if len(infos) > 4000 or sum(x.file_size for x in infos) > MAX_ZIP_BYTES:
        z.close()
        raise BridgeError('ZIP_LIMIT', '文档解压规模超过安全上限。')
    if len({x.filename for x in infos}) != len(infos):
        z.close(); raise BridgeError('UNSAFE_ZIP', '文档包含重复部件名称。')
    for x in infos:
        if x.flag_bits & 1 or (x.file_size > 1_000_000 and x.file_size > max(1, x.compress_size) * 300):
            z.close()
            raise BridgeError('ZIP_LIMIT', '文档包含加密或异常压缩部件。')
        pp = PurePosixPath(x.filename)
        if pp.is_absolute() or '..' in pp.parts or '\\' in x.filename:
            z.close()
            raise BridgeError('UNSAFE_ZIP', '文档部件路径不安全。')
    return z

def decode_text(blob: bytes) -> tuple[str, str]:
    if blob.startswith((b'\xff\xfe', b'\xfe\xff')):
        text=blob.decode('utf-16')
        if '\x00' in text: raise BridgeError('BINARY_FILE', 'UTF-16 文本含二进制空字符。')
        return text, 'UTF-16 BOM'
    for enc in ('utf-8-sig', 'gb18030'):
        try:
            text = blob.decode(enc)
            if '\x00' in text:
                raise BridgeError('BINARY_FILE', '文件包含二进制内容，不作为文本读取。')
            return text, enc
        except UnicodeDecodeError:
            pass
    raise BridgeError('ENCODING', '无法按 UTF-8、带 BOM 的 UTF-16 或 GB18030 解码。')

def extract(blob: bytes, ext: str) -> dict:
    lines, warnings = [], []
    partial = False
    if ext in TEXT_EXTENSIONS:
        text, encoding = decode_text(blob)
        lines = text.splitlines()
        # Do not render HTML or visit its referenced URLs.
        if ext in ('.html', '.htm', '.xml'):
            warnings.append('返回原始文本；不执行脚本、不渲染 HTML、不请求外部资源。')
        warnings.append(f'文本编码：{encoding}')
    elif ext == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise BridgeError('PDF_COMPONENT_MISSING', 'PDF 组件尚未安装。请在本机「连接与诊断」中安装 PDF 组件；其他格式不受影响。') from exc
        reader = PdfReader(io.BytesIO(blob), strict=False)
        if reader.is_encrypted:
            raise BridgeError('ENCRYPTED_PDF', '不读取加密 PDF，请先在本机提供经授权解密的副本。')
        count, chars = min(len(reader.pages), 500), 0
        nonempty = False
        for i in range(count):
            text = reader.pages[i].extract_text() or ''
            nonempty = nonempty or bool(text.strip())
            lines.append(f'[PDF 第 {i+1} 页]')
            lines.extend(text.splitlines())
            chars += len(text)
            if chars > MAX_TEXT_CHARS:
                partial = True
                warnings.append('PDF 文本达到提取上限，后续页面未解析。')
                break
        if len(reader.pages) > count:
            partial = True
            warnings.append('仅处理前 500 页；未读取其余页面。')
        if not nonempty:
            warnings.append('未发现可提取文字，可能是扫描件；本程序未做 OCR，不能据此认为文件没有内容。')
        warnings.append('PDF 返回文字层，非页面视觉核验；多栏、表格、图片和阅读顺序可能不完整。')
    elif ext in ('.docx', '.xlsx', '.pptx'):
        with safe_zip(blob) as z:
            if ext == '.docx':
                body = xml(z.read('word/document.xml')).find(f'{W}body')
                if body is not None:
                    for i, child in enumerate(body):
                        if child.tag == f'{W}p':
                            text = ''.join((n.text or '') if n.tag==f'{W}t' else ('\t' if n.tag==f'{W}tab' else '\n') for n in child.iter() if n.tag in (f'{W}t', f'{W}tab', f'{W}br'))
                            if text: lines.append(f'[段落 {i+1}] {text}')
                        elif child.tag == f'{W}tbl':
                            lines.append(f'[表格 {i+1}]')
                            for tr in child.findall(f'{W}tr'):
                                cells = [' / '.join(''.join(n.text or '' for n in p.iter(f'{W}t'))
                                                    for p in tc.findall(f'{W}p')) for tc in tr.findall(f'{W}tc')]
                                lines.append(' | '.join(cells))
                extras = sorted(n for n in z.namelist() if re.fullmatch(r'word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml', n))
                for n in extras:
                    lines.append(f'[附属文本 {n.split("/")[-1]}]')
                    for p in xml(z.read(n)).iter(f'{W}p'):
                        t = ''.join(t.text or '' for t in p.iter(f'{W}t'))
                        if t: lines.append(t)
                warnings.append('DOCX 为正文、表格及附属文字提取；不提供排版页码、完整修订审阅或图片识别。')
            elif ext == '.pptx':
                rels = xml(z.read('ppt/_rels/presentation.xml.rels'))
                mapping = {x.attrib['Id']: x.attrib['Target'] for x in rels}
                pres = xml(z.read('ppt/presentation.xml'))
                slide_ids = pres.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId')
                for i, node in enumerate(slide_ids[:500]):
                    target = mapping.get(node.attrib.get(f'{R}id', ''), '')
                    n = target.lstrip('/') if target.startswith('/') else 'ppt/' + target
                    if '..' in PurePosixPath(n).parts or n not in z.namelist():
                        raise BridgeError('PPTX_RELATION', '幻灯片内部关系不受支持。')
                    lines.append(f'[幻灯片 {i+1}]')
                    for p in xml(z.read(n)).iter(f'{A}p'):
                        t = ''.join(t.text or '' for t in p.iter(f'{A}t'))
                        if t: lines.append(t)
                if len(slide_ids)>500:
                    partial = True
                    warnings.append('仅处理前 500 张幻灯片。')
                warnings.append('PPTX 按演示顺序提取形状文字和表格文字；不读取图表数据、图片、备注或动画。')
            else:
                shared = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    for si in xml(z.read('xl/sharedStrings.xml')).iter(f'{S}si'):
                        shared.append(''.join(t.text or '' for t in si.iter(f'{S}t')))
                rels = xml(z.read('xl/_rels/workbook.xml.rels'))
                mapping = {x.attrib['Id']: x.attrib['Target'] for x in rels}
                for sheet in xml(z.read('xl/workbook.xml')).findall(f'{S}sheets/{S}sheet'):
                    name = sheet.attrib.get('name', '?')
                    hidden = sheet.attrib.get('state', 'visible')
                    lines.append(f'[工作表 {name}；状态 {hidden}]')
                    target = mapping.get(sheet.attrib.get(f'{R}id', ''), '')
                    n = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                    if '..' in PurePosixPath(n).parts or n not in z.namelist():
                        raise BridgeError('XLSX_RELATION', '工作表内部关系不受支持。')
                    sheetxml = xml(z.read(n))
                    for row in sheetxml.iter(f'{S}row'):
                        cells = []
                        for c in row.findall(f'{S}c'):
                            v = c.find(f'{S}v')
                            text = v.text if v is not None and v.text else ''
                            typ = c.attrib.get('t', '')
                            if typ == 's':
                                idx = int(text) if text else -1
                                text = shared[idx] if 0 <= idx < len(shared) else '[无效共享字符串索引]'
                            elif typ == 'inlineStr':
                                text = ''.join(t.text or '' for t in c.iter(f'{S}t'))
                            f = c.find(f'{S}f')
                            if f is not None:
                                text = f'公式={f.text or "[共享/数组公式]"}；缓存值={text or "[缺失]"}'
                            cells.append(f'{c.attrib.get("r", "?")}={text}')
                        if cells: lines.append(' | '.join(cells))
                warnings.append('XLSX 含隐藏工作表；保留单元格地址、公式及已有缓存值，不计算公式，不保证日期/数字显示格式与 Excel 一致。')
    else:
        raise BridgeError('UNSUPPORTED_FORMAT', '该格式仅可列出，不能提取正文。支持文本、PDF、DOCX、XLSX、PPTX；旧版 Office、图片及压缩包不支持。')
    # Break pathological single lines without silently dropping their tail.
    wrapped = []
    for line in lines:
        if len(line) <= 4000: wrapped.append(line)
        else:
            warnings.append('个别超长行已拆为每段最多 4000 字符的提取行；行号不是原文件行号。')
            wrapped.extend(line[i:i+4000] for i in range(0, len(line), 4000))
    total = 0; out = []; truncated = False
    for line in wrapped:
        if total + len(line) + 1 > MAX_TEXT_CHARS:
            truncated = True; break
        out.append(line); total += len(line) + 1
    if truncated: warnings.append('累计提取达到 100 万字符上限，未返回的内容不在当前提取范围内。')
    return {'lines': out, 'warnings': list(dict.fromkeys(warnings)), 'extraction_truncated': truncated or partial}

def worker(ext: str) -> None:
    # The input is bytes supplied by the already-authorized reader, never a path.
    try:
        if sys.platform != 'win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
        blob = sys.stdin.buffer.read(25*1024*1024+1)
        if len(blob)>25*1024*1024: raise BridgeError('FILE_TOO_LARGE', '超过读取上限。')
        result = {'ok': True, **extract(blob, ext)}
    except BridgeError as exc:
        result = {'ok': False, 'error': {'code': exc.code, 'message': exc.message}}
    except Exception:
        result = {'ok': False, 'error': {'code': 'PARSE_FAILED', 'message': '文件解析失败，可能格式损坏、结构特殊或不受支持。'}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
