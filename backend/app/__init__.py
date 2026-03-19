"""
MiroFish Backend - Factory dell'applicazione Flask
"""

import os
import warnings

# Sopprimi gli avvisi resource_tracker di multiprocessing (provenienti da librerie di terze parti come transformers)
# Deve essere impostato prima di tutte le altre importazioni
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Funzione factory dell'applicazione Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Impostazione codifica JSON: assicura che i caratteri non-ASCII vengano mostrati direttamente (invece del formato \uXXXX)
    # Flask >= 2.3 usa app.json.ensure_ascii, le versioni precedenti usano la configurazione JSON_AS_ASCII
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Configura i log
    logger = setup_logger('mirofish')

    # Stampa le informazioni di avvio solo nel processo figlio del reloader (evita stampe duplicate in modalità debug)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend in avvio...")
        logger.info("=" * 50)

    # Abilita CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Registra la funzione di pulizia dei processi di simulazione (assicura che tutti i processi vengano terminati alla chiusura del server)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Funzione di pulizia processi di simulazione registrata")

    # Middleware per il log delle richieste
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Richiesta: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Corpo richiesta: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Risposta: {response.status_code}")
        return response

    # Registra i blueprint
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    # Controllo di salute
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    if should_log_startup:
        logger.info("MiroFish Backend avvio completato")

    return app
