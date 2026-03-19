"""
Modulo di configurazione log
Fornisce gestione log unificata, con output simultaneo su console e file
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Assicura che stdout/stderr utilizzino la codifica UTF-8
    Risolve il problema dei caratteri non-ASCII nella console Windows
    """
    if sys.platform == 'win32':
        # Su Windows riconfigura l'output standard in UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Directory dei log
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Configura il logger

    Args:
        name: Nome del logger
        level: Livello di log

    Returns:
        Logger configurato
    """
    # Assicura che la directory dei log esista
    os.makedirs(LOG_DIR, exist_ok=True)

    # Crea il logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Impedisci la propagazione dei log al logger root, evitando output duplicati
    logger.propagate = False

    # Se ci sono già handler, non aggiungerne altri
    if logger.handlers:
        return logger

    # Formato dei log
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    # 1. Handler file - log dettagliati (nome per data, con rotazione)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # 2. Handler console - log sintetici (INFO e superiori)
    # Assicura la codifica UTF-8 su Windows per evitare caratteri illeggibili
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Aggiungi gli handler
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Ottieni il logger (lo crea se non esiste)

    Args:
        name: Nome del logger

    Returns:
        Istanza del logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Crea il logger predefinito
logger = setup_logger()


# Metodi di convenienza
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)
