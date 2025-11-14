import bpy
import os
import subprocess
import tempfile
import select
import ctypes
from ctypes import wintypes

IS_WIN32 = os.name == 'nt'
if IS_WIN32:
    import msvcrt

def ensureBlendPath():
    path = bpy.data.filepath
    if path:
        return path
    bpy.ops.wm.save_mainfile()
    return bpy.data.filepath

def saveTempBlendCopy():
    handle, path = tempfile.mkstemp(suffix='.blend')
    os.close(handle)
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return path

def startBackgroundMeasurement(context, panel, line_handler, finish_handler):
    scene = context.scene
    meter = scene.light_meter
    if meter.background_pending:
        return 0
    if not ensureBlendPath():
        return 0
    temp_blend = saveTempBlendCopy()
    binary = bpy.app.binary_path
    if not binary:
        os.remove(temp_blend)
        return 0

    cmd = [
        binary,
        '--background', temp_blend,
        '--python', f'{os.path.dirname(__file__)}/background_runner.py',
    ]
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['TEMPDIR'] = bpy.app.tempdir
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=env,
        )
    except Exception as exc:
        print(f'Background measurement failed to start: {exc}')
        os.remove(temp_blend)
        return 0

    job = {
        'process': proc,
        'temp_blend': temp_blend,
        'panel': panel,
        'scene': scene,
        'result_line': '',
        'progress_count': 0,
        'samples': 0,
        'buffer': bytearray(),
        'line_handler': line_handler,
        'finish_handler': finish_handler,
    }

    meter.background_pending = 1
    meter.background_progress = 0.0
    bpy.app.timers.register(lambda: streamBackgroundProc(job), first_interval=0.05)
    return 1

def streamBackgroundProc(job):
    proc = job['process']
    pipe = proc.stdout
    if not pipe:
        return 0.05

    chunk = readAvailable(pipe)
    if chunk:
        buffer = job['buffer']
        buffer.extend(chunk)
        if processBufferedLines(job):
            job['finish_handler'](job)
            return None
        return 0.0

    if proc.poll() is not None:
        if processBufferedLines(job, flush=1):
            job['finish_handler'](job)
            return None
        if job.get('last_line', '').startswith('METER_'):
            job['result_line'] = job['last_line']
        job['finish_handler'](job)
        return None

    return 0.05

def readAvailable(pipe):
    fd = pipe.fileno()
    if IS_WIN32:
        handle = msvcrt.get_osfhandle(fd)
        avail = wintypes.DWORD()
        ok = ctypes.windll.kernel32.PeekNamedPipe(
            handle, None, 0, None, ctypes.byref(avail), None
        )
        if not ok or avail.value == 0:
            return b''
        to_read = min(avail.value, 4096)
        return os.read(fd, to_read)

    ready, _, _ = select.select([fd], [], [], 0)
    if not ready:
        return b''
    return os.read(fd, 4096)

def processBufferedLines(job, flush=0):
    buffer = job['buffer']
    while True:
        idx = buffer.find(b'\n')
        if idx < 0:
            if flush and buffer:
                line = buffer[:]
                buffer.clear()
                job['progress_count'] += 1
                text = line.decode('utf-8', 'replace').rstrip('\r')
                if job['line_handler'](text, job):
                    return 1
            break
        line = buffer[:idx]
        del buffer[:idx + 1]
        job['progress_count'] += 1
        text = line.decode('utf-8', 'replace').rstrip('\r')
        if job['line_handler'](text, job):
            return 1
    return 0
