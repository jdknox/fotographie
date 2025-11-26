LOG_PREFIX = '[Fotographie]'

LEVEL_DEBUG = 0
LEVEL_INFO = 1
LEVEL_WARNING = 2
LEVEL_ERROR = 3

g_log_level = LEVEL_INFO
g_log_level = LEVEL_DEBUG
g_logging_enabled = 1

def _log(level, label, message):
    if not g_logging_enabled:
        return
    if level < g_log_level:
        return
    print(f'{LOG_PREFIX} {label}: {message}')

def debug(message):
    _log(LEVEL_DEBUG, 'DEBUG', message)

def info(message):
    _log(LEVEL_INFO, 'INFO', message)

def warning(message):
    _log(LEVEL_WARNING, 'WARNING', message)

def error(message):
    _log(LEVEL_ERROR, 'ERROR', message)
