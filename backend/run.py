"""
Punto di ingresso MiroFish Backend
"""

import os
import sys

# Risolvi il problema dei caratteri non-ASCII nella console Windows: imposta la codifica UTF-8 prima di tutte le importazioni
if sys.platform == 'win32':
    # Imposta la variabile d'ambiente per assicurare che Python usi UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Riconfigura i flussi di output standard in UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Aggiungi la directory radice del progetto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Funzione principale"""
    # Verifica la configurazione
    errors = Config.validate()
    if errors:
        print("Errori di configurazione:")
        for err in errors:
            print(f"  - {err}")
        print("\nVerifica la configurazione nel file .env")
        sys.exit(1)

    # Crea l'applicazione
    app = create_app()

    # Ottieni la configurazione di esecuzione
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    # Avvia il servizio
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()
