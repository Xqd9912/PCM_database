#!/usr/bin/env python3
"""在 NSCC HPC (10.68.0.1, gcn01) 上非交互执行命令（固定密码，pexpect 驱动系统 ssh）。

用法: python nscc_run.py <user> <remote_command> [timeout_sec]
账号: GK_xum02 / nscc1741_XM ，共用固定密码。
"""
import os
import shlex
import sys

import pexpect

HOST = os.environ.get("PCM_HPC_HOST", "10.68.0.1")
# 密码从环境变量读取，切勿硬编码进仓库： export PCM_HPC_PW=...
PW = os.environ.get("PCM_HPC_PW", "")
if not PW:
    import getpass
    PW = getpass.getpass("HPC password: ")


def run(user: str, cmd: str, timeout: int = 180) -> str:
    ssh = (
        "ssh -o StrictHostKeyChecking=accept-new -o HostKeyAlgorithms=+ssh-rsa "
        f"-o PubkeyAuthentication=no -o ConnectTimeout=15 {user}@{HOST} {shlex.quote(cmd)}"
    )
    ch = pexpect.spawn(ssh, timeout=timeout, encoding="utf-8")
    i = ch.expect([r"assword:", pexpect.EOF, pexpect.TIMEOUT])
    if i == 0:
        ch.sendline(PW)
        try:
            ch.expect(pexpect.EOF)
            out = ch.before
        except pexpect.TIMEOUT:
            # 后台任务可能让 ssh 通道不关闭；返回已缓冲输出即可
            out = ch.before or ""
    elif i == 1:
        out = ch.before  # 没要密码就结束（异常）
    else:
        out = "[TIMEOUT] " + (ch.before or "")
    try:
        ch.close(force=True)
    except Exception:
        pass
    # 去掉回显的密码行/首个空行
    lines = [ln for ln in out.splitlines() if ln.strip() != ""]
    return "\n".join(lines)


if __name__ == "__main__":
    user = sys.argv[1]
    cmd = sys.argv[2]
    to = int(sys.argv[3]) if len(sys.argv) > 3 else 180
    print(run(user, cmd, to))
