#!/usr/bin/python3
"""Open one reverse proxy tunnel per SSH host while its connections exist."""

from contextlib import closing
import fcntl
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys

def start_watcher(host, forwarding, directory, address):
    with socket.socket(socket.AF_UNIX) as listener:
        # 先监听再启动后台进程，登记方可以立即连接，不必等后台初始化。
        listener.bind(str(address))
        listener.listen()
        fd = listener.fileno()
        with (directory / "tunnel.log").open("w") as log:
            subprocess.Popen(
                [sys.executable, __file__, host, forwarding, "--watch", str(fd)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                # 后台进程独立于终端，并接管已经打开的监听套接字。
                start_new_session=True, pass_fds=(fd,),
            )


def register(host, forwarding, directory):
    address = directory / "watch.sock"
    with socket.socket(socket.AF_UNIX) as client:
        # 超时只限制套接字操作，等待文件锁可能更久。
        client.settimeout(5)
        # 登记和关闭共用同一把锁，避免新连接发给正在退出的后台进程。
        with (directory / "sessions.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                client.connect(str(address))
            except (FileNotFoundError, ConnectionRefusedError):
                address.unlink(missing_ok=True)
                start_watcher(host, forwarding, directory, address)
                client.connect(str(address))
            # LocalCommand 用 exec 替换中间 shell，父进程就是触发它的 SSH。
            client.sendall(str(os.getppid()).encode("ascii") + b"\n")
        # 释放锁后再等回执，后台才能拿锁处理登记。
        # 回执只确认 PID 已登记，隧道可能还在建立。
        if client.recv(1) != b"1":
            sys.exit(f"{host} proxy registration failed. See {directory / 'tunnel.log'}")


def subscribe_exit(queue, pid):
    event = select.kevent(
        pid, filter=select.KQ_FILTER_PROC,
        flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
        fflags=select.KQ_NOTE_EXIT,
    )
    try:
        queue.control([event], 0)
    except ProcessLookupError:
        # SSH 可能在发送登记请求后、内核完成订阅前退出。
        return False
    return True


def accept_registrations(listener, queue, sessions):
    registered = False
    while True:
        try:
            client, _ = listener.accept()
        except BlockingIOError:
            return registered
        with client, client.makefile("rb") as request:
            try:
                value = request.readline(16)
                if not value:
                    continue
                pid = int(value)
                # 如果父 SSH 先退出，登记进程可能已被 PID 1 接管。
                if pid > 1 and subscribe_exit(queue, pid):
                    sessions.add(pid)
                    registered = True
                    client.sendall(b"1")
            except ConnectionError:
                # 对端可能先断开。已订阅的 PID 仍由退出事件清理。
                continue


# 调用方持有登记锁。先停隧道，再释放本地登记入口。
def close_watcher(listener, address, tunnel):
    if tunnel is not None:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=3)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait()
    listener.close()
    address.unlink()


def watch(host, forwarding, directory, listener_fd):
    def terminate(_signum, _frame):
        # 让 SIGTERM 走 finally，清理隧道和套接字。
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    tunnel_command = [
        "/usr/bin/ssh", "-nNT", "-S", "none",
        "-o", "BatchMode=yes",
        # Host * 也会匹配专用 SSH，必须禁止它再次触发 LocalCommand。
        "-o", "PermitLocalCommand=no",
        "-o", "ExitOnForwardFailure=yes",
        "-R", forwarding, host,
    ]
    address = directory / "watch.sock"
    sessions = set()
    tunnel = None
    with socket.socket(fileno=listener_fd) as listener, closing(select.kqueue()) as queue:
        # 监听器使用非阻塞模式，处理完排队的登记后就能回到事件循环。
        listener.setblocking(False)
        queue.control([select.kevent(
            listener, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_ADD,
        )], 0)
        try:
            while True:
                exited = {
                    event.ident for event in queue.control(None, 32)
                    if event.filter == select.KQ_FILTER_PROC
                }
                if tunnel is not None and tunnel.pid in exited:
                    print(f"{host} proxy SSH exited with status {tunnel.wait()}.", flush=True)
                    tunnel = None
                sessions.difference_update(exited)
                with (directory / "sessions.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    # 先处理已排队的登记，再决定是否关闭。
                    registered = accept_registrations(listener, queue, sessions)
                    if not sessions:
                        close_watcher(listener, address, tunnel)
                        return
                    # 隧道退出后，等下一次有效登记再启动。
                    if registered and tunnel is None:
                        tunnel = subprocess.Popen(tunnel_command)
                        if not subscribe_exit(queue, tunnel.pid):
                            print(f"{host} proxy SSH exited with status {tunnel.wait()}.", flush=True)
                            tunnel = None
        finally:
            # 正常退出已关闭监听器。异常或 SIGTERM 退出时在这里补做清理。
            if listener.fileno() != -1:
                with (directory / "sessions.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    close_watcher(listener, address, tunnel)


def main():
    host, forwarding, *watch_args = sys.argv[1:]
    # 使用 macOS 的用户临时目录，让终端和桌面客户端找到同一个套接字。
    temp = subprocess.check_output(
        ["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True
    ).strip()
    directory = Path(temp) / f"ssh-proxy-{host}"
    directory.mkdir(mode=0o700, exist_ok=True)
    if watch_args:
        _, listener_fd = watch_args
        watch(host, forwarding, directory, int(listener_fd))
    else:
        register(host, forwarding, directory)


if __name__ == "__main__":
    main()
