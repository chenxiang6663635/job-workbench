# -*- coding: utf-8 -*-
"""Windows 凭据管理器后端（issue #203）：ctypes 直调 advapi32，零第三方依赖。

**为什么不用 keyring**：本仓库的分发纪律是零新依赖（领域包 dependencies 为空）；
`CredWriteW / CredReadW / CredDeleteW` 足够做这件事，引第三方 keyring 只多一份
供应链与打包成本，换不来额外保证。

**导入期永不失败**：本模块顶层只 import 标准库与声明纯 ctypes 结构体；
`ctypes.WinDLL("advapi32")` 只在 `_advapi32()` 内部、且先判平台——Linux / macOS
上 import 本模块（以及 `credentials`）都安全，CI 的 ubuntu job 照跑。

**不抛**：公开方法一律以 None / False 表达失败。日志只记形态、引用（ref）与成败，
**永不记密文**（含异常分支——只报类型，不报值）。

blob 编码选 **UTF-8**（读回同口径解码）：凭据只被自家代码读写，没有与其它
Windows 工具互认的需求。刻意**不做任何缓存**：缓存会把「用户刚修好却仍是旧状态」
变成幽灵问题。

策略层（形态选择、惰性迁移、保存与「清除即删」）在 `credentials.py`；本文件只做
存储后端，接口契约由 `tests/test_credentials.py` 与真机用例共同钉住。
"""

from __future__ import annotations

import ctypes
import logging
import sys

from .credentials import SecretStore

logger = logging.getLogger(__name__)

# Windows API 常量（credential.h / winerror.h）。
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _FileTime(ctypes.Structure):
    """FILETIME（两个 DWORD）——CREDENTIALW 的字段偏移要对齐，不能省。"""
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


class _CredentialW(ctypes.Structure):
    """CREDENTIALW（credential.h）。字段顺序 = ABI，不能重排、不能省尾字段。

    DWORD 用 c_uint32、指针用 c_void_p / c_wchar_p：刻意不走 ctypes.wintypes，
    让模块顶层与"只在 Windows 才有意义"的东西彻底无关（wintypes 在 Linux 上
    其实也能 import，但少一层依赖就少一处可怀疑点）。
    """
    _fields_ = [
        ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p), ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.c_void_p), ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        # 属性数组是 PCREDENTIAL_ATTRIBUTEW；本模块不写属性，指针形态足够。
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p),
    ]


def _advapi32():
    """加载 advapi32 并绑定函数签名；任何失败 → None（不抛）。

    非 Windows 直接 None：`ctypes.WinDLL` 在 Linux 上根本不存在，平台判定必须
    先于触碰它完成——这就是"导入期永不失败"的实现面。加载失败记 warning 留诊断。
    """
    if sys.platform != "win32":
        return None
    try:
        lib = ctypes.WinDLL("advapi32", use_last_error=True)
        lib.CredWriteW.argtypes = [ctypes.POINTER(_CredentialW), ctypes.c_uint32]
        lib.CredWriteW.restype = ctypes.c_int
        lib.CredReadW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.POINTER(_CredentialW))]
        lib.CredReadW.restype = ctypes.c_int
        lib.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                    ctypes.c_uint32]
        lib.CredDeleteW.restype = ctypes.c_int
        lib.CredFree.argtypes = [ctypes.c_void_p]  # 成功读出的结构由调用方释放
        lib.CredFree.restype = None
        return lib
    except Exception as exc:
        logger.warning("advapi32 不可用（凭据管理器加载失败）：%s", exc)
        return None


class CredManStore(SecretStore):
    """Windows 凭据管理器：Generic Credential、本机持久化、目标名 = 引用串。"""
    kind = "credman"

    def available(self):
        """Windows 且 advapi32 能加载才为真；任何异常 → False（不抛）。"""
        return _advapi32() is not None

    def get(self, ref):
        """读回密文；不存在 → None（ERROR_NOT_FOUND 是正常路径，不吵）。

        blob 按写入时的 UTF-8 口径解码；失败只记形态信息，不带内容。
        """
        if not ref:
            return None
        lib = _advapi32()
        if lib is None:
            return None
        cred_ptr = ctypes.POINTER(_CredentialW)()
        if not lib.CredReadW(ref, _CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)):
            err = ctypes.get_last_error()
            if err != _ERROR_NOT_FOUND:
                logger.warning("读取凭据失败（ref=%s，错误码=%s）", ref, err)
            return None
        try:
            size = int(cred_ptr.contents.CredentialBlobSize)
            raw = (b"" if size <= 0 else
                   ctypes.string_at(cred_ptr.contents.CredentialBlob, size))
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # 密文（或其片段）绝不进日志——只说明"不是本模块写的 UTF-8"。
            logger.warning("凭据 blob 不是 UTF-8（ref=%s）——外部工具写入？", ref)
            return None
        except Exception as exc:
            logger.warning("凭据内容读取失败（ref=%s）：%s", ref, exc)
            return None
        finally:
            if cred_ptr:  # CredReadW 成功才分配内存，失败路径无物可释放
                lib.CredFree(ctypes.cast(cred_ptr, ctypes.c_void_p))

    def set(self, ref, secret):
        """写入密文（UTF-8 blob）；成功 / 失败，不抛。"""
        if not ref:
            return False
        lib = _advapi32()
        if lib is None:
            return False
        try:
            payload = secret.encode("utf-8")
        except (AttributeError, UnicodeEncodeError) as exc:
            # 只报异常类型，绝不带值（值正是要保护的东西）。
            logger.warning("凭据值无法写入（ref=%s）：%s", ref, type(exc).__name__)
            return False
        cred = _CredentialW(
            Type=_CRED_TYPE_GENERIC, TargetName=ref,
            Comment="job-workbench 本地凭据",
            CredentialBlobSize=len(payload),
            Persist=_CRED_PERSIST_LOCAL_MACHINE)
        buffer = ctypes.create_string_buffer(payload, max(len(payload), 1))
        cred.CredentialBlob = ctypes.cast(buffer, ctypes.c_void_p)
        if lib.CredWriteW(ctypes.byref(cred), 0):
            logger.debug("凭据已写入凭据管理器（ref=%s）", ref)
            return True
        logger.warning("写入凭据失败（ref=%s，错误码=%s）", ref,
                       ctypes.get_last_error())
        return False

    def delete(self, ref):
        """删除凭据；**幂等**——本就不存在（ERROR_NOT_FOUND）也算成功。"""
        if not ref:
            return True
        lib = _advapi32()
        if lib is None:
            return False
        if lib.CredDeleteW(ref, _CRED_TYPE_GENERIC, 0):
            logger.debug("凭据已从凭据管理器删除（ref=%s）", ref)
            return True
        err = ctypes.get_last_error()
        if err == _ERROR_NOT_FOUND:
            return True
        logger.warning("删除凭据失败（ref=%s，错误码=%s）", ref, err)
        return False
