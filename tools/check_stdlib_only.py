#!/usr/bin/env python3
"""AST import scan of python files: fails on any import that is not part of the standard library.

Usage:
    python tools/check_stdlib_only.py <dir>
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

# Python 3.9 fallback set of all standard library and builtin module names
# Note: sys.stdlib_module_names was added in Python 3.10.
STDLIB_MODULES_3_9 = frozenset({
    "__future__", "_thread", "abc", "aifc", "argparse", "array", "ast", "asynchat",
    "asyncio", "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "cProfile", "calendar", "cgi", "cgitb", "chunk",
    "cmath", "cmd", "code", "codecs", "codeop", "collections", "colorsys", "compileall",
    "concurrent", "configparser", "contextlib", "contextvars", "copy", "copyreg",
    "crypt", "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings", "ensurepip",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "formatter", "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "idlelib", "imaplib", "imghdr", "imp", "importlib", "inspect",
    "io", "ipaddress", "itertools", "json", "keyword", "lib2to3", "linecache",
    "locale", "logging", "lzma", "mailbox", "mailcap", "marshal", "math",
    "mimetypes", "mmap", "modulefinder", "msilib", "msvcrt", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os", "ossaudiodev",
    "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri",
    "random", "re", "readline", "reprlib", "resource", "rlcompleter", "runpy",
    "sched", "secrets", "select", "selectors", "shelve", "shlex", "shutil",
    "signal", "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symbol", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "trace", "traceback", "tracemalloc", "tty", "turtle", "turtledemo", "types",
    "typing", "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
    "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
    "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
} | set(sys.builtin_module_names))


def get_stdlib_modules() -> frozenset[str]:
    """Return standard library module names (using sys.stdlib_module_names on 3.10+)."""
    if hasattr(sys, "stdlib_module_names"):
        return frozenset(sys.stdlib_module_names | set(sys.builtin_module_names))
    return STDLIB_MODULES_3_9


def check_file(path: Path, stdlib_modules: frozenset[str]) -> list[str]:
    """Scan a single Python file for non-stdlib imports.

    Allows:
    - Standard library modules
    - Relative imports (e.g., from . import contracts)
    - Imports from 'verity'
    """
    violations: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(path))
    except Exception as e:
        return [f"{path}: failed to parse AST: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module != "verity" and top_module not in stdlib_modules:
                    violations.append(
                        f"{path}:{node.lineno}: import {alias.name} (module '{top_module}' is not stdlib)"
                    )
        elif isinstance(node, ast.ImportFrom):
            # Relative imports have node.level > 0
            if node.level > 0:
                continue
            if node.module:
                top_module = node.module.split(".")[0]
                if top_module != "verity" and top_module not in stdlib_modules:
                    violations.append(
                        f"{path}:{node.lineno}: from {node.module} import ... (module '{top_module}' is not stdlib)"
                    )

    return violations


def check_directory(dir_path: Path) -> list[str]:
    stdlib_modules = get_stdlib_modules()
    violations: list[str] = []
    for root, _, files in os.walk(dir_path):
        for f in files:
            if f.endswith(".py"):
                file_path = Path(root) / f
                violations.extend(check_file(file_path, stdlib_modules))
    return violations


def main() -> int:
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "verity"
    p = Path(target_dir)
    if not p.exists():
        print(f"Error: directory does not exist: {p}", file=sys.stderr)
        return 2

    violations = check_directory(p)
    if violations:
        print(f"Found {len(violations)} non-stdlib import violations in {p}:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(f"OK: All imports in {p} are stdlib-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
