"""Path policy. Remote inputs never select roots or local program settings."""
from __future__ import annotations
import ctypes
import fnmatch
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import stat

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
TEXT_EXTENSIONS = frozenset('.txt .md .markdown .csv .tsv .json .jsonl .yaml .yml .toml .ini .log .py .js .jsx .ts .tsx .css .html .htm .xml .sql .c .h .cpp .hpp .rs .go .java .kt .swift .sol .sh .ps1 .bat .cmd .rst .tex'.split())
DOCUMENT_EXTENSIONS = frozenset(('.pdf', '.docx', '.xlsx', '.pptx'))
WRITE_EXTENSIONS = frozenset(('.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.yaml', '.yml'))
DENY_NAMES = frozenset(x.casefold() for x in (
    'node_modules', '__pycache__', 'venv', 'env', 'AppData', 'Windows',
    'Program Files', 'Program Files (x86)', 'ProgramData', '$Recycle.Bin',
    'System Volume Information', 'LocalFolderBridge', 'credentials', 'secrets',
    'credentials.json', 'credentials.csv', 'secrets.json', 'token.json', 'tokens.json',
    'passwords.txt', 'passwords.csv', 'Login Data', 'Cookies', 'Web Data',
    'id_rsa', 'id_ed25519', 'id_dsa', 'id_ecdsa', 'NTUSER.DAT'))
DENY_GLOBS = ('*.pem', '*.key', '*.pfx', '*.p12', '*.kdbx', '*.keystore',
              '*.lnk', '*.url', '*.jks', '*credentials*', '*passwords*', '*secret*')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', re.I)

class BridgeError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)

def blocked_name(name: str) -> bool:
    low = name.casefold()
    return (name.startswith('.') or low in DENY_NAMES or
            any(fnmatch.fnmatchcase(low, pat) for pat in DENY_GLOBS))

def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value) > 1500:
        raise BridgeError('INVALID_PATH', '路径必须是长度不超过 1500 字符的相对路径。')
    if value == '' or value == '.':
        return ()
    if '\x00' in value or PureWindowsPath(value).drive or value.startswith(('/', '\\')):
        raise BridgeError('INVALID_PATH', '不接受绝对路径、盘符、UNC 路径或空字节。')
    parts = tuple(value.replace('\\', '/').split('/'))
    if len(parts) > 64:
        raise BridgeError('PATH_TOO_DEEP', '路径超过 64 层。')
    for p in parts:
        if (not p or p in ('.', '..') or any(ord(c) < 32 for c in p) or
                any(c in p for c in ':*?<>|"') or p.endswith((' ', '.')) or RESERVED.match(p)):
            raise BridgeError('INVALID_PATH', '路径含不允许的名称、上级引用或 Windows 特殊语法。')
        if blocked_name(p):
            raise BridgeError('EXCLUDED', '路径被敏感文件或系统目录排除规则拦截。')
    return parts

def is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & 0x400)

def reject_links(path: Path) -> None:
    """Inspect every extant component, including components above the chosen root."""
    for p in reversed((path, *path.parents)):
        try:
            if is_link(p.lstat()):
                raise BridgeError('LINK_BLOCKED', '不允许符号链接、目录联接或其他重解析点。')
        except FileNotFoundError:
            break

def identity(st: os.stat_result) -> str:
    return f'{st.st_dev}:{st.st_ino}'

def normalize_root(value: str, state_dir: Path, app_dir: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BridgeError('INVALID_ROOT', '请选择一个具体文件夹。')
    p = Path(value).expanduser().absolute()
    if str(p).startswith(('\\\\', '//')):
        raise BridgeError('NETWORK_ROOT', '首版仅支持本机磁盘，不授权 UNC 网络共享。')
    reject_links(p)
    p = p.resolve(strict=True)
    if not p.is_dir():
        raise BridgeError('INVALID_ROOT', '授权目标必须是已存在的文件夹。')
    if p == Path(p.anchor) or p == Path.home().resolve():
        raise BridgeError('ROOT_TOO_BROAD', '不能授权整个磁盘或整个用户主目录，请选择项目子目录。')
    if any(blocked_name(x) for x in p.parts[1:]):
        raise BridgeError('EXCLUDED_ROOT', '所选目录属于敏感、隐藏或系统目录。')
    for protected in (state_dir.resolve(), app_dir.resolve()):
        if p == protected or p in protected.parents or protected in p.parents:
            raise BridgeError('PROTECTED_ROOT', '不能授权程序、状态、日志、凭证或备份所在目录及其上级目录。')
    return p

def resolve_scoped(root: dict, rel: str, *, missing_leaf: bool = False) -> Path:
    parts = relative_parts(rel)
    base = Path(root['path'])
    try:
        st = base.lstat()
        if identity(st) != root['identity'] or is_link(st) or not stat.S_ISDIR(st.st_mode):
            raise BridgeError('ROOT_CHANGED', '授权文件夹已被替换或变成链接，请在本机重新授权。')
        reject_links(base)
        p = base
        for i, component in enumerate(parts):
            p = p / component
            try:
                st = p.lstat()
            except FileNotFoundError:
                if missing_leaf and i == len(parts) - 1:
                    return p
                raise BridgeError('NOT_FOUND', '找不到指定文件或文件夹。')
            if is_link(st):
                raise BridgeError('LINK_BLOCKED', '链接、目录联接及重解析点不允许访问。')
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                raise BridgeError('HARDLINK_BLOCKED', '多重硬链接文件不允许访问。')
        resolved = p.resolve(strict=True)
        if not resolved.is_relative_to(base):
            raise BridgeError('OUT_OF_SCOPE', '目标不在授权目录内。')
        return p
    except OSError as exc:
        raise BridgeError('FILE_UNAVAILABLE', '文件不可访问，可能已移动、离线或被占用。') from exc

def _handle_path(fd: int) -> Path | None:
    if os.name != 'nt':
        try:
            return Path(os.readlink(f'/proc/self/fd/{fd}'))
        except OSError:
            return None
    import msvcrt
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = k32.GetFinalPathNameByHandleW
    fn.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    fn.restype = ctypes.c_uint32
    buf = ctypes.create_unicode_buffer(32768)
    n = fn(msvcrt.get_osfhandle(fd), buf, len(buf), 0)
    if not n or n >= len(buf):
        raise BridgeError('HANDLE_CHECK_FAILED', '无法确认已打开文件的最终路径，已拒绝读取。')
    value = buf.value
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)

def read_bytes(root: dict, rel: str, max_bytes: int = MAX_FILE_BYTES) -> tuple[bytes, dict]:
    p = resolve_scoped(root, rel)
    before = p.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise BridgeError('NOT_A_FILE', '该路径不是普通文件。')
    if before.st_size > max_bytes:
        raise BridgeError('FILE_TOO_LARGE', f'单文件读取上限为 {max_bytes // (1024*1024)} MiB。')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(p, flags)
        with os.fdopen(fd, 'rb') as f:
            opened = os.fstat(f.fileno())
            if (identity(opened) != identity(before) or opened.st_nlink > 1 or
                    not stat.S_ISREG(opened.st_mode)):
                raise BridgeError('FILE_CHANGED', '文件在打开时发生变化，请重试。')
            final = _handle_path(f.fileno())
            if final is not None:
                base = Path(root['path'])
                try:
                    rel_final = final.relative_to(base).as_posix()
                except ValueError as exc:
                    raise BridgeError('OUT_OF_SCOPE', '文件句柄最终路径越过授权范围。') from exc
                relative_parts(rel_final)
                if final != p:
                    raise BridgeError('FILE_CHANGED', '文件句柄最终路径与请求路径不一致。')
            blob = f.read(max_bytes + 1)
            after = os.fstat(f.fileno())
            if len(blob) > max_bytes:
                raise BridgeError('FILE_TOO_LARGE', '读取过程中超过单文件大小限制。')
            if (opened.st_mtime_ns, opened.st_size) != (after.st_mtime_ns, after.st_size):
                raise BridgeError('FILE_CHANGED', '文件在读取期间被修改，请重试。')
        return blob, {'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob),
                      'modified_ns': after.st_mtime_ns, 'identity': identity(after)}
    except OSError as exc:
        raise BridgeError('READ_FAILED', '读取失败；请确认文件未被占用且本机用户有读取权限。') from exc
