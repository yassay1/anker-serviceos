"""Local development supervisor. Uses existing dependencies and never resets data."""
import argparse
import ctypes
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime' / 'dev-launcher'
FRONT = 'http://127.0.0.1:5173'
API = 'http://127.0.0.1:8000'
CONTROL = 'http://127.0.0.1:5172'


def local_database(url):
    try:
        parsed = urlsplit(url)
        _ = parsed.port
        return (parsed.scheme == 'postgresql+psycopg' and parsed.hostname in ('127.0.0.1', 'localhost')
                and parsed.path == '/serviceos_dev')
    except ValueError:
        return False


def agent_enabled(env):
    return env.get('SERVICEOS_START_AGENT') == '1' and all(env.get(key) for key in (
        'SERVICEOS_LLM_MODEL', 'SERVICEOS_LLM_BASE_URL', 'SERVICEOS_LLM_API_KEY'))


def agent_worker_count(env):
    try:
        return max(1, min(4, int(env.get('SERVICEOS_AGENT_WORKERS', '1'))))
    except (TypeError, ValueError):
        return 1


def ensure_environment(root):
    destination = root / 'backend/.env'
    if not destination.exists():
        shutil.copy2(root / 'backend/.env.example', destination)


def request_json(url, data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)
    except urllib.error.HTTPError as failure:
        try:
            return json.load(failure)
        except (ValueError, OSError):
            return None
    except (OSError, ValueError):
        return None


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


class WindowsJob:
    """Windows kills owned child trees when the launcher window is closed."""
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        handle = self.kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not handle or not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            if handle:
                self.kernel.CloseHandle(handle)
            raise OSError('Cannot create the local process supervision job.')
        self.handle = handle

    def attach(self, process):
        if self.handle and not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.terminate()
            raise OSError('Cannot supervise the child process safely.')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--frontend-only', action='store_true')
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    state_file = RUNTIME / 'state.json'
    existing = request_json(CONTROL + '/status')
    if existing:
        if existing.get('root') != str(ROOT):
            print('[ERROR] Port 5172 is used by another project. No process was stopped.', flush=True)
            return 1
        if args.stop:
            state = json.loads(state_file.read_text(encoding='utf-8'))
            result = request_json(CONTROL + '/stop', b'', {'Authorization': 'Bearer ' + state['token']})
            print('Stop requested.' if result else 'Could not contact the launcher.', flush=True)
        else:
            print('Already running: ' + FRONT, flush=True)
            if not args.no_browser:
                webbrowser.open(FRONT)
        return 0
    if args.stop:
        print('No running launcher for this project.', flush=True)
        return 0
    if port_open(5172) or port_open(5173) or (not args.frontend_only and port_open(8000)):
        print('[ERROR] Ports 5172/5173/8000 are occupied. Close the other development server first.', flush=True)
        return 1
    node = shutil.which('node')
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.exists():
        print('[ERROR] Node.js 24 and frontend dependencies are needed. Run npm ci in frontend.', flush=True)
        return 1

    stop = threading.Event()
    token = secrets.token_urlsafe(32)
    status = {'root': str(ROOT), 'status': 'starting', 'services': {}, 'url': FRONT}

    class ControlHandler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != '/status':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode('utf-8'))

        def do_POST(self):
            if self.path != '/stop' or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(403)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"stopping":true}')
            stop.set()

    server = ThreadingHTTPServer(('127.0.0.1', 5172), ControlHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state_file.write_text(json.dumps({'root': str(ROOT), 'pid': os.getpid(), 'token': token}), encoding='utf-8')
    job = WindowsJob()
    children = []
    logs = []
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    backend_python = ROOT / 'backend/.venv/Scripts/python.exe'
    if os.name != 'nt':
        backend_python = ROOT / 'backend/.venv/bin/python'

    def report(name, value):
        status['services'][name] = value
        print(f'[{name}] {value}', flush=True)

    def run_step(name, command, timeout=40):
        with (RUNTIME / (name + '.log')).open('w', encoding='utf-8') as output:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                        timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                return result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                return False

    def start(name, command, cwd=ROOT):
        output = (RUNTIME / (name + '.log')).open('w', encoding='utf-8')
        logs.append(output)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        job.attach(process)
        children.append((name, process))
        report(name, 'starting')
        return process

    def wait_http(url, process, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and process.poll() is None and not stop.is_set():
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return True
            except OSError:
                time.sleep(0.3)
        return False

    try:
        print('Anker ServiceOS - local hot-reload preview', flush=True)
        frontend = start('frontend', [node, str(vite), '--host', '127.0.0.1'], ROOT / 'frontend')
        if not wait_http(FRONT, frontend):
            report('frontend', 'FAILED - see .runtime/dev-launcher/frontend.log')
            return 1
        report('frontend', 'ready ' + FRONT)
        if not args.no_browser:
            webbrowser.open(FRONT)
        if not args.frontend_only and backend_python.exists():
            ensure_environment(ROOT)
            try:
                from dotenv import dotenv_values
                env = {**{key: value for key, value in dotenv_values(ROOT / 'backend/.env').items() if value is not None}, **env}
            except ImportError:
                report('backend', 'Python dependencies missing; continuing with frontend')
            url = env.get('SERVICEOS_DATABASE_URL', '')
            local = local_database(url) and env.get('SERVICEOS_ENV') == 'development' and env.get('SERVICEOS_AUTH_MODE') == 'local'
            config_path = ROOT / '.runtime/launcher-local.json'
            if local and config_path.exists():
                try:
                    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
                except (OSError, ValueError):
                    config = {}
                    report('database', 'local launcher config invalid; automatic PostgreSQL start skipped')
                pg_ctl = ROOT / config.get('pg_ctl', '.runtime/tools/postgresql/bin/pg_ctl.exe')
                data = Path(config.get('data_dir', ''))
                port = urlsplit(url).port or 5432
                if pg_ctl.is_file() and (data / 'PG_VERSION').is_file() and not port_open(port):
                    ok = run_step('postgresql', [str(pg_ctl), 'start', '-D', str(data), '-l', str(RUNTIME / 'postgresql-server.log'),
                                                '-w', '-t', '15', '-o', f'-h 127.0.0.1 -p {port}'], timeout=20)
                    report('database', 'started; existing data preserved' if ok else 'not available; see postgresql.log')
            database_ready = local and run_step('migrate', [str(backend_python), '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'])
            if database_ready:
                database_ready = run_step('accounts', [str(backend_python), '-m', 'serviceos_api.bootstrap_local'])
            report('database', 'ready' if database_ready else 'unavailable or not an approved local dev database; business features may fail')
            api = start('api', [str(backend_python), '-m', 'uvicorn', 'serviceos_api.main:app', '--host', '127.0.0.1',
                                '--port', '8000', '--reload', '--reload-dir', str(ROOT / 'backend/serviceos_api')])
            report('api', 'ready ' + API + '/docs' if wait_http(API + '/api/v1/health', api) else 'FAILED - see api.log; frontend remains available')
            if database_ready:
                for worker in ('inspection', 'actions', 'followups', 'outbox'):
                    start(worker, [str(backend_python), '-m', 'serviceos_api.worker.' + worker])
                if agent_enabled(env) and run_step('checkpoints', [str(backend_python), '-m', 'serviceos_api.checkpoints']):
                    for index in range(agent_worker_count(env)):
                        name = 'agent' if index == 0 else f'agent-{index + 1}'
                        start(name, [str(backend_python), '-m', 'serviceos_api.worker.main'])
                else:
                    report('agent', 'off - configure Provider and SERVICEOS_START_AGENT=1 to enable')
        else:
            report('api', 'skipped - frontend-only mode or backend/.venv is missing')
        status['status'] = 'running'
        print('\nKeep this window open. Frontend/API edits reload automatically.\nCtrl+C or the Stop shortcut closes owned app services. PostgreSQL data is retained.\nLogs: ' + str(RUNTIME), flush=True)
        while not stop.wait(1):
            for name, process in children:
                if process.poll() is not None and status['services'].get(name) != 'exited':
                    report(name, 'exited - see ' + name + '.log')
                elif process.poll() is None and status['services'].get(name) == 'starting':
                    report(name, 'running')
    except KeyboardInterrupt:
        pass
    finally:
        status['status'] = 'stopped'
        job.close()
        for _, process in reversed(children):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for output in logs:
            output.close()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(f'[ERROR] Launcher could not complete ({type(failure).__name__}). Check .runtime/dev-launcher logs.', flush=True)
        raise SystemExit(1)
