"""Fixed, locally invoked native helpers. None are exposed as MCP tools."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
from .security import BridgeError

# No user input is interpolated into this script. Dialog result only returns to the local UI.
FOLDER_SCRIPT = r'''Add-Type -AssemblyName System.Windows.Forms; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Select a project folder to authorize'; $d.ShowNewFolderButton = $false; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($d.SelectedPath) }; $d.Dispose()'''
FILE_SCRIPT = r'''Add-Type -AssemblyName System.Windows.Forms; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'Select the official tunnel-client executable'; $d.Filter = 'Tunnel client (tunnel-client.exe)|tunnel-client.exe'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($d.FileName) }; $d.Dispose()'''

def pick(kind='folder'):
    if os.name != 'nt': raise BridgeError('WINDOWS_ONLY','文件夹选择器仅支持 Windows；其他系统可在输入框粘贴绝对路径。')
    script=FILE_SCRIPT if kind=='tunnel' else FOLDER_SCRIPT
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-STA','-Command',script],
                         stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180,
                         creationflags=0x08000000)
        if p.returncode: raise BridgeError('PICKER_FAILED','系统选择器打开失败，请改用手动粘贴路径。')
        return p.stdout.decode('utf-8-sig').strip()
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise BridgeError('PICKER_FAILED','选择器不可用或超时，请手动粘贴路径。') from exc

def protect_secret(secret: str) -> bytes:
    if os.name!='nt': raise BridgeError('WINDOWS_ONLY','只有 Windows 支持使用当前用户 DPAPI 加密保存凭证；本次可仅在内存使用。')
    return _dpapi(secret.encode('utf-8'),True)
def unprotect_secret(data: bytes) -> str: return _dpapi(data,False).decode('utf-8')

def _dpapi(data: bytes, protect: bool) -> bytes:
    class BLOB(ctypes.Structure): _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data); source=BLOB(len(data),buffer); output=BLOB()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True); kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    if protect:
        fn=crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(BLOB),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(source),'Local Folder Bridge',None,None,None,1,ctypes.byref(output))
    else:
        fn=crypt.CryptUnprotectData
        fn.argtypes=[ctypes.POINTER(BLOB),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    if not ok: raise BridgeError('DPAPI_FAILED','Windows 凭证加密/解密失败，请重新输入运行时密钥。')
    try: return ctypes.string_at(output.pbData,output.cbData)
    finally:
        kernel.LocalFree.argtypes=[ctypes.c_void_p]; kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(output.pbData)
