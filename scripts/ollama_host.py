#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享：解析 Windows 宿主机 Ollama 地址（WSL 环境）。

在 WSL2 里，Ollama 运行在 Windows 宿主侧（利用 Arc iGPU 加速），
WSL 脚本通过默认网关 IP 访问 Windows 的 11434 端口。
"""
import socket, subprocess

PORT = 11434


def host_ip():
    """解析 Windows 宿主机 IP（WSL2 默认网关）。"""
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for tok in out.split():
            if tok.count(".") == 3:
                return tok
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def base_url():
    return f"http://{host_ip()}:{PORT}"


def generate_url():
    return f"{base_url()}/api/generate"
