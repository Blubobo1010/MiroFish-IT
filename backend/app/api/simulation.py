"""
Route API simulazione
Step2: Lettura e filtraggio entità Zep, preparazione e esecuzione simulazione OASIS (completamente automatizzato)
"""

import os
import traceback
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..services.zep_entity_reader import ZepEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('mirofish.api.simulation')


# Prefisso ottimizzazione prompt Interview
# Aggiungere questo prefisso evita che l'Agent chiami strumenti, rispondendo direttamente con testo
INTERVIEW_PROMPT_PREFIX = "Combinando il tuo personaggio, tutti i ricordi e le azioni passate, rispondimi direttamente con testo senza chiamare alcuno strumento："


def optimize_interview_prompt(prompt: str) -> str:
    """
    Ottimizza domanda Interview, aggiunge prefisso per evitare che l'Agent chiami strumenti

    Args:
        prompt: Domanda originale

    Returns:
        Domanda ottimizzata
    """
    if not prompt:
        return prompt
    # Evita di aggiungere il prefisso più volte
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== Interfacce lettura entità ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    Ottieni tutte le entità nel grafo (filtrate)

    Restituisce solo i nodi conformi ai tipi di entità predefiniti (nodi con Labels non solo Entity)

    Parametri query:
        entity_types: Lista tipi entità separata da virgole (opzionale, per ulteriore filtraggio)
        enrich: Se ottenere informazioni sugli archi correlati (default true)
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY non configurata"
            }), 500
        
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(f"Recupero entità grafo: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")
        
        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Recupero entità grafo fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Ottieni informazioni dettagliate di una singola entità"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY non configurata"
            }), 500
        
        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": f"Entità non trovata: {entity_uuid}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Recupero dettagli entità fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Ottieni tutte le entità di un tipo specificato"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY non configurata"
            }), 500
        
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(f"Recupero entità fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce gestione simulazione ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    Crea nuova simulazione

    Nota: parametri come max_rounds sono generati intelligentemente dal LLM, non necessitano impostazione manuale

    Richiesta (JSON):
        {
            "project_id": "proj_xxxx",      // obbligatorio
            "graph_id": "mirofish_xxxx",    // opzionale, se non fornito viene preso dal progetto
            "enable_twitter": true,          // opzionale, default true
            "enable_reddit": true            // opzionale, default true
        }

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "Fornire project_id"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {project_id}"
            }), 404

        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Il progetto non ha ancora costruito il grafo, chiamare prima /api/graph/build"
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Creazione simulazione fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Verifica se la simulazione è già stata preparata

    Condizioni di verifica:
    1. state.json esiste e lo status è "ready"
    2. I file necessari esistono: reddit_profiles.json, twitter_profiles.csv, simulation_config.json

    Nota: gli script di esecuzione (run_*.py) restano nella directory backend/scripts/, non vengono più copiati nella directory di simulazione

    Args:
        simulation_id: ID simulazione

    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # Verifica se la directory esiste
    if not os.path.exists(simulation_dir):
        return False, {"reason": "La directory di simulazione non esiste"}

    # Lista dei file necessari (esclusi gli script, che si trovano in backend/scripts/)
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]
    
    # Verifica se i file esistono
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "File necessari mancanti",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # Verifica lo stato in state.json
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # Log dettagliato
        logger.debug(f"Verifica stato preparazione simulazione: {simulation_id}, status={status}, config_generated={config_generated}")

        # Se config_generated=True e i file esistono, la preparazione è considerata completata
        # I seguenti stati indicano che la preparazione è stata completata:
        # - ready: preparazione completata, pronta per l'esecuzione
        # - preparing: se config_generated=True significa che è completata
        # - running: in esecuzione, la preparazione è stata completata in precedenza
        # - completed: esecuzione completata, la preparazione è stata completata in precedenza
        # - stopped: fermata, la preparazione è stata completata in precedenza
        # - failed: esecuzione fallita (ma la preparazione è stata completata)
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # Ottieni statistiche dei file
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # Se lo stato è preparing ma i file sono completi, aggiorna automaticamente lo stato a ready
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Aggiornamento automatico stato simulazione: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"Aggiornamento automatico stato fallito: {e}")
            
            logger.info(f"Simulazione {simulation_id} risultato verifica: preparazione completata (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"Simulazione {simulation_id} risultato verifica: preparazione non completata (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"Lo stato non è nella lista degli stati preparati o config_generated è false: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"Lettura file di stato fallita: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    Prepara l'ambiente di simulazione (task asincrono, LLM genera tutti i parametri in modo intelligente)

    Questa è un'operazione che richiede tempo, l'interfaccia restituisce immediatamente il task_id,
    usare GET /api/simulation/prepare/status per verificare il progresso

    Caratteristiche:
    - Rileva automaticamente la preparazione già completata, evitando generazioni duplicate
    - Se già preparata, restituisce direttamente i risultati esistenti
    - Supporta la rigenerazione forzata (force_regenerate=true)

    Passaggi:
    1. Verifica se esiste già una preparazione completata
    2. Legge e filtra le entità dal grafo Zep
    3. Genera OASIS Agent Profile per ogni entità (con meccanismo di retry)
    4. LLM genera in modo intelligente la configurazione della simulazione (con meccanismo di retry)
    5. Salva i file di configurazione e gli script predefiniti

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",                   // obbligatorio, ID simulazione
            "entity_types": ["Student", "PublicFigure"],  // opzionale, specifica tipi di entità
            "use_llm_for_profiles": true,                 // opzionale, se usare LLM per generare profili
            "parallel_profile_count": 5,                  // opzionale, numero di profili generati in parallelo, default 5
            "force_regenerate": false                     // opzionale, rigenerazione forzata, default false
        }

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // restituito per nuovi task
                "status": "preparing|ready",
                "message": "Task di preparazione avviato|Preparazione già completata",
                "already_prepared": true|false    // se la preparazione è già completata
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        # Verifica se rigenerare forzatamente
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"Inizio elaborazione richiesta /prepare: simulation_id={simulation_id}, force_regenerate={force_regenerate}")

        # Verifica se la preparazione è già completata (evita generazioni duplicate)
        if not force_regenerate:
            logger.debug(f"Verifica se la simulazione {simulation_id} è già preparata...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"Risultato verifica: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"Simulazione {simulation_id} già preparata, salto generazione duplicata")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "Preparazione già completata, non è necessario rigenerare",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(f"Simulazione {simulation_id} non ancora preparata, avvio task di preparazione")

        # Ottieni informazioni necessarie dal progetto
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Il progetto non esiste: {state.project_id}"
            }), 404

        # Ottieni requisiti della simulazione
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Il progetto manca della descrizione dei requisiti di simulazione (simulation_requirement)"
            }), 400
        
        # Ottieni testo del documento
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        nuts2_region = data.get('nuts2_region')  # Calibrazione ICF regionale
        
        # ========== Ottieni sincrono il conteggio delle entità (prima dell'avvio del task in background) ==========
        # In questo modo il frontend può ottenere il numero totale di Agent attesi immediatamente dopo la chiamata a prepare
        try:
            logger.info(f"Ottenimento sincrono conteggio entità: graph_id={state.graph_id}")
            reader = ZepEntityReader()
            # Lettura rapida delle entità (non servono informazioni sugli archi, solo conteggio)
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # Non ottenere informazioni sugli archi, per velocizzare
            )
            # Salva il conteggio delle entità nello stato (per il frontend da ottenere immediatamente)
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"Conteggio entità previsto: {filtered_preview.filtered_count}, tipi: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"Ottenimento sincrono conteggio entità fallito (verrà riprovato nel task in background): {e}")
            # Il fallimento non influenza il flusso successivo, il task in background riotterrà il conteggio

        # Crea task asincrono
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # Aggiorna stato simulazione (contiene il conteggio entità ottenuto in anticipo)
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)
        
        # Definisci task in background
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Inizio preparazione ambiente di simulazione..."
                )
                
                # Prepara simulazione (con callback di progresso)
                # Memorizza i dettagli del progresso per fase
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    # Calcola progresso totale
                    stage_weights = {
                        "reading": (0, 20),           # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)       # 90-100%
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # Costruisci informazioni dettagliate sul progresso
                    stage_names = {
                        "reading": "Lettura entità del grafo",
                        "generating_profiles": "Generazione profili Agent",
                        "generating_config": "Generazione configurazione simulazione",
                        "copying_scripts": "Preparazione script di simulazione"
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # Aggiorna dettagli della fase
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # Costruisci informazioni dettagliate sul progresso
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # Costruisci messaggio conciso
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                    nuts2_region=nuts2_region
                )
                
                # Task completato
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )
                
            except Exception as e:
                logger.error(f"Preparazione simulazione fallita: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # Aggiorna stato simulazione a fallito
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        # Avvia thread in background
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "Task di preparazione avviato, verificare il progresso tramite /api/simulation/prepare/status",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # Numero totale di Agent previsto
                "entity_types": state.entity_types  # Lista dei tipi di entità
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Avvio task di preparazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    Verifica il progresso del task di preparazione

    Supporta due modalità di query:
    1. Tramite task_id per verificare il progresso del task in corso
    2. Tramite simulation_id per verificare se esiste una preparazione già completata

    Richiesta (JSON):
        {
            "task_id": "task_xxxx",          // opzionale, task_id restituito da prepare
            "simulation_id": "sim_xxxx"      // opzionale, ID simulazione (per verificare preparazione completata)
        }

    Risposta:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // se esiste una preparazione completata
                "prepare_info": {...}            // informazioni dettagliate quando la preparazione è completata
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # Se è stato fornito simulation_id, verifica prima se la preparazione è completata
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "Preparazione già completata",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
        
        # Se non c'è task_id, restituisci errore
        if not task_id:
            if simulation_id:
                # C'è simulation_id ma la preparazione non è completata
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "Preparazione non ancora iniziata, chiamare /api/simulation/prepare per iniziare",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "Fornire task_id o simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # Il task non esiste, ma se c'è simulation_id, verifica se la preparazione è completata
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "Task completato (preparazione già esistente)",
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": f"Il task non esiste: {task_id}"
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(f"Verifica stato task fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Ottieni stato della simulazione"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        result = state.to_dict()

        # Se la simulazione è pronta, allega istruzioni di esecuzione
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Ottenimento stato simulazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    Elenca tutte le simulazioni

    Parametri query:
        project_id: Filtra per ID progetto (opzionale)
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(f"Elenco simulazioni fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    Ottieni il report_id più recente corrispondente alla simulazione

    Attraversa la directory reports, trova i report che corrispondono al simulation_id,
    se ce ne sono più di uno restituisce il più recente (ordinato per created_at)

    Args:
        simulation_id: ID simulazione

    Returns:
        report_id o None
    """
    import json
    from datetime import datetime
    
    # Percorso directory reports: backend/uploads/reports
    # __file__ è app/api/simulation.py, bisogna salire di due livelli fino a backend/
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # Ordina per data di creazione decrescente, restituisci il più recente
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(f"Ricerca report per simulazione {simulation_id} fallita: {e}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    Ottieni lista storica delle simulazioni (con dettagli progetto)

    Usata per la visualizzazione dei progetti storici nella homepage, restituisce una lista di simulazioni
    con informazioni dettagliate come nome progetto, descrizione, ecc.

    Parametri query:
        limit: Limite del numero di risultati (default 20)

    Risposta:
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "Analisi opinione pubblica",
                    "simulation_requirement": "Se l'universita' pubblica...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # Arricchisci i dati della simulazione, leggi solo dal file Simulation
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            
            # Ottieni informazioni di configurazione simulazione (leggi simulation_requirement da simulation_config.json)
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # Numero di round raccomandato (valore di riserva)
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 / 
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0
            
            # Ottieni stato di esecuzione (leggi il numero effettivo di round impostato dall'utente da run_state.json)
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # Usa total_rounds impostato dall'utente, altrimenti usa il numero di round raccomandato
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds
            
            # Ottieni lista file del progetto associato (massimo 3)
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "File sconosciuto")}
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []
            
            # Ottieni report_id associato (cerca il report più recente per questa simulazione)
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
            
            # Aggiungi numero di versione
            sim_dict["version"] = "v1.0.2"
            
            # Formatta la data
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(f"Ottenimento storico simulazioni fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    Ottieni i profili Agent della simulazione

    Parametri query:
        platform: Tipo di piattaforma (reddit/twitter, default reddit)
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Ottenimento profili fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    Ottieni in tempo reale i profili Agent della simulazione (per visualizzare il progresso durante la generazione)

    Differenze dall'interfaccia /profiles:
    - Legge direttamente il file, senza passare per SimulationManager
    - Adatto per la visualizzazione in tempo reale durante la generazione
    - Restituisce metadati aggiuntivi (come data di modifica del file, se è in fase di generazione, ecc.)

    Parametri query:
        platform: Tipo di piattaforma (reddit/twitter, default reddit)

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // Totale previsto (se disponibile)
                "is_generating": true,  // Se è in fase di generazione
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')
        
        # Ottieni directory simulazione
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        # Determina percorso file
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")
        
        # Verifica se il file esiste
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None
        
        if file_exists:
            # Ottieni data di modifica del file
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Lettura file profiles fallita (potrebbe essere in fase di scrittura): {e}")
                profiles = []
        
        # Verifica se è in fase di generazione (tramite state.json)
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento profili in tempo reale fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    Ottieni in tempo reale la configurazione della simulazione (per visualizzare il progresso durante la generazione)

    Differenze dall'interfaccia /config:
    - Legge direttamente il file, senza passare per SimulationManager
    - Adatto per la visualizzazione in tempo reale durante la generazione
    - Restituisce metadati aggiuntivi (come data di modifica del file, se è in fase di generazione, ecc.)
    - Anche se la configurazione non è ancora completamente generata, può restituire informazioni parziali

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // Se è in fase di generazione
                "generation_stage": "generating_config",  // Fase di generazione attuale
                "config": {...}  // Contenuto della configurazione (se esiste)
            }
        }
    """
    import json
    from datetime import datetime
    
    try:
        # Ottieni directory simulazione
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        # Percorso file di configurazione
        config_file = os.path.join(sim_dir, "simulation_config.json")
        
        # Verifica se il file esiste
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None
        
        if file_exists:
            # Ottieni data di modifica del file
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Lettura file config fallita (potrebbe essere in fase di scrittura): {e}")
                config = None
        
        # Verifica se è in fase di generazione (tramite state.json)
        is_generating = False
        generation_stage = None
        config_generated = False
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)
                    
                    # Determina la fase attuale
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass
        
        # Costruisci dati di risposta
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config
        }
        
        # Se la configurazione esiste, estrai alcune statistiche chiave
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"Ottenimento configurazione in tempo reale fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    Ottieni la configurazione della simulazione (configurazione completa generata intelligentemente dal LLM)

    Contiene:
        - time_config: Configurazione temporale (durata simulazione, round, periodi di picco/calo)
        - agent_configs: Configurazione attività di ogni Agent (livello di attività, frequenza di pubblicazione, posizione, ecc.)
        - event_config: Configurazione eventi (post iniziali, argomenti caldi)
        - platform_configs: Configurazione piattaforme
        - generation_reasoning: Spiegazione del ragionamento di configurazione del LLM
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": "La configurazione della simulazione non esiste, chiamare prima l'interfaccia /prepare"
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"Ottenimento configurazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Scarica il file di configurazione della simulazione"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "Il file di configurazione non esiste, chiamare prima l'interfaccia /prepare"
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(f"Download configurazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    Scarica il file script di esecuzione della simulazione (script generico, nella directory backend/scripts/)

    Valori possibili per script_name:
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # Gli script si trovano nella directory backend/scripts/
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        # Valida il nome dello script
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py", 
            "run_parallel_simulation.py",
            "action_logger.py"
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"Script sconosciuto: {script_name}, disponibili: {allowed_scripts}"
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"Il file script non esiste: {script_name}"
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(f"Download script fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce generazione Profile (uso indipendente) ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    Genera OASIS Agent Profile direttamente dal grafo (senza creare una simulazione)

    Richiesta (JSON):
        {
            "graph_id": "mirofish_xxxx",     // obbligatorio
            "entity_types": ["Student"],      // opzionale
            "use_llm": true,                  // opzionale
            "platform": "reddit"              // opzionale
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Fornire graph_id"
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "Nessuna entita' trovata che soddisfi i criteri"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"Generazione profili fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce controllo esecuzione simulazione ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    Avvia l'esecuzione della simulazione

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",          // obbligatorio, ID simulazione
            "platform": "parallel",                // opzionale: twitter / reddit / parallel (default)
            "max_rounds": 100,                     // opzionale: numero massimo di round, per troncare simulazioni troppo lunghe
            "enable_graph_memory_update": false,   // opzionale: se aggiornare dinamicamente le attività degli Agent nella memoria del grafo Zep
            "force": false                         // opzionale: riavvio forzato (ferma la simulazione in corso e pulisce i log)
        }

    Riguardo il parametro force:
        - Se abilitato, se la simulazione è in esecuzione o completata, la ferma prima e pulisce i log di esecuzione
        - I contenuti puliti includono: run_state.json, actions.jsonl, simulation.log, ecc.
        - Non pulisce i file di configurazione (simulation_config.json) e i file dei profili
        - Adatto a scenari in cui è necessario rieseguire la simulazione

    Riguardo enable_graph_memory_update:
        - Se abilitato, tutte le attività degli Agent nella simulazione (post, commenti, like, ecc.) vengono aggiornate in tempo reale nel grafo Zep
        - Questo permette al grafo di "ricordare" il processo di simulazione, per analisi successive o conversazioni AI
        - Richiede che il progetto associato alla simulazione abbia un graph_id valido
        - Utilizza un meccanismo di aggiornamento batch per ridurre il numero di chiamate API

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // se l'aggiornamento memoria grafo è abilitato
                "force_restarted": true               // se è un riavvio forzato
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # Opzionale: numero massimo di round
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # Opzionale: se abilitare aggiornamento memoria grafo
        force = data.get('force', False)  # Opzionale: riavvio forzato

        # Valida parametro max_rounds
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds deve essere un intero positivo"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds deve essere un intero valido"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"Tipo di piattaforma non valido: {platform}, disponibili: twitter/reddit/parallel"
            }), 400

        # Verifica se la simulazione è pronta
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"La simulazione non esiste: {simulation_id}"
            }), 404

        force_restarted = False

        # Gestione intelligente dello stato: se la preparazione è completata, consenti il riavvio
        if state.status != SimulationStatus.READY:
            # Verifica se la preparazione è completata
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # La preparazione è completata, verifica se ci sono processi in esecuzione
                if state.status == SimulationStatus.RUNNING:
                    # Verifica se il processo di simulazione è davvero in esecuzione
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # Il processo è effettivamente in esecuzione
                        if force:
                            # Modalita' forzata: ferma la simulazione in esecuzione
                            logger.info(f"Modalita' forzata: arresto simulazione in esecuzione {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"Avviso durante l'arresto della simulazione: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": "La simulazione è in esecuzione, chiamare prima l'interfaccia /stop per fermarla, oppure usare force=true per riavviare forzatamente"
                            }), 400

                # Se in modalita' forzata, pulisci i log di esecuzione
                if force:
                    logger.info(f"Modalita' forzata: pulizia log simulazione {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"Avviso durante la pulizia dei log: {cleanup_result.get('errors')}")
                    force_restarted = True

                # Il processo non esiste o è terminato, reimposta lo stato a ready
                logger.info(f"Simulazione {simulation_id} preparazione completata, reimpostazione stato a ready (stato precedente: {state.status.value})")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # La preparazione non è completata
                return jsonify({
                    "success": False,
                    "error": f"La simulazione non è pronta, stato attuale: {state.status.value}, chiamare prima l'interfaccia /prepare"
                }), 400
        
        # Ottieni ID del grafo (per aggiornamento memoria grafo)
        graph_id = None
        if enable_graph_memory_update:
            # Ottieni graph_id dallo stato della simulazione o dal progetto
            graph_id = state.graph_id
            if not graph_id:
                # Prova a ottenerlo dal progetto
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "L'abilitazione dell'aggiornamento memoria grafo richiede un graph_id valido, assicurarsi che il progetto abbia costruito il grafo"
                }), 400
            
            logger.info(f"Aggiornamento memoria grafo abilitato: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # Avvia simulazione
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # Aggiorna stato simulazione
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Avvio simulazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    Ferma la simulazione

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx"  // obbligatorio, ID simulazione
        }

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        run_state = SimulationRunner.stop_simulation(simulation_id)

        # Aggiorna stato simulazione
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Arresto simulazione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce monitoraggio stato in tempo reale ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    Ottieni lo stato in tempo reale dell'esecuzione della simulazione (per il polling del frontend)

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Ottenimento stato di esecuzione fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    Ottieni lo stato dettagliato dell'esecuzione della simulazione (incluse tutte le azioni)

    Usato per la visualizzazione delle dinamiche in tempo reale nel frontend

    Parametri query:
        platform: Filtra per piattaforma (twitter/reddit, opzionale)
    
    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Tutte le azioni della piattaforma Twitter
                "reddit_actions": [...]    # Tutte le azioni della piattaforma Reddit
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        # Ottieni la lista completa delle azioni
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )
        
        # Ottieni azioni per piattaforma
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []
        
        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []
        
        # Ottieni le azioni del round attuale (recent_actions mostra solo l'ultimo round)
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []
        
        # Ottieni informazioni di stato base
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions mostra solo i contenuti dell'ultimo round per entrambe le piattaforme
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Ottenimento stato dettagliato fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    Ottieni lo storico delle azioni degli Agent nella simulazione

    Parametri query:
        limit: Numero di risultati (default 100)
        offset: Offset (default 0)
        platform: Filtra per piattaforma (twitter/reddit)
        agent_id: Filtra per Agent ID
        round_num: Filtra per round
    
    Risposta:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento storico azioni fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    Ottieni la timeline della simulazione (riepilogo per round)

    Usata per la visualizzazione della barra di avanzamento e della timeline nel frontend

    Parametri query:
        start_round: Round iniziale (default 0)
        end_round: Round finale (default tutti)

    Restituisce informazioni riepilogative per ogni round
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento timeline fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    Ottieni le statistiche di ogni Agent

    Usato per la visualizzazione della classifica di attività degli Agent, distribuzione delle azioni, ecc. nel frontend
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento statistiche Agent fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce query database ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    Ottieni i post della simulazione

    Parametri query:
        platform: Tipo di piattaforma (twitter/reddit)
        limit: Numero di risultati (default 50)
        offset: Offset

    Restituisce la lista dei post (letti dal database SQLite)
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "Il database non esiste, la simulazione potrebbe non essere ancora stata eseguita"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento post fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    Ottieni i commenti della simulazione (solo Reddit)

    Parametri query:
        post_id: Filtra per ID post (opzionale)
        limit: Numero di risultati
        offset: Offset
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"Ottenimento commenti fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce Interview (interviste) ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    Intervista un singolo Agent

    Nota: questa funzione richiede che l'ambiente di simulazione sia in stato di esecuzione (dopo aver completato il ciclo di simulazione ed essere entrato in modalita' attesa comandi)

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",       // obbligatorio, ID simulazione
            "agent_id": 0,                     // obbligatorio, Agent ID
            "prompt": "Cosa ne pensi di questo?",  // obbligatorio, domanda dell'intervista
            "platform": "twitter",             // opzionale, specifica piattaforma (twitter/reddit)
                                               // se non specificato: simulazione dual-platform intervista entrambe le piattaforme
            "timeout": 60                      // opzionale, timeout (secondi), default 60
        }

    Risposta (senza specificare platform, modalita' dual-platform):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "Cosa ne pensi di questo?",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Risposta (con platform specificata):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "Cosa ne pensi di questo?",
                "result": {
                    "agent_id": 0,
                    "response": "Penso che...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Opzionale: twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "Fornire agent_id"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "Fornire prompt (domanda dell'intervista)"
            }), 400
        
        # Valida parametro platform
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "Il parametro platform puo' essere solo 'twitter' o 'reddit'"
            }), 400
        
        # Verifica stato ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è stato chiuso. Assicurarsi che la simulazione sia completata ed entrata in modalita' attesa comandi."
            }), 400
        
        # Ottimizza prompt, aggiungi prefisso per evitare che l'Agent chiami strumenti
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta Interview: {str(e)}"
        }), 504
        
    except Exception as e:
        logger.error(f"Interview fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    Intervista in batch piu' Agent

    Nota: questa funzione richiede che l'ambiente di simulazione sia in stato di esecuzione

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",       // obbligatorio, ID simulazione
            "interviews": [                    // obbligatorio, lista interviste
                {
                    "agent_id": 0,
                    "prompt": "Cosa ne pensi di A?",
                    "platform": "twitter"      // opzionale, specifica piattaforma per questo Agent
                },
                {
                    "agent_id": 1,
                    "prompt": "Cosa ne pensi di B?"  // senza platform usa il valore predefinito
                }
            ],
            "platform": "reddit",              // opzionale, piattaforma predefinita (sovrascritta dal platform di ogni elemento)
                                               // se non specificato: simulazione dual-platform intervista ogni Agent su entrambe le piattaforme
            "timeout": 120                     // opzionale, timeout (secondi), default 120
        }

    Risposta:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # Opzionale: twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "Fornire interviews (lista interviste)"
            }), 400

        # Valida parametro platform
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "Il parametro platform puo' essere solo 'twitter' o 'reddit'"
            }), 400

        # Valida ogni elemento dell'intervista
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"L'elemento {i+1} della lista interviste manca di agent_id"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"L'elemento {i+1} della lista interviste manca di prompt"
                }), 400
            # Valida il platform di ogni elemento (se presente)
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"Il platform dell'elemento {i+1} della lista interviste puo' essere solo 'twitter' o 'reddit'"
                }), 400

        # Verifica stato ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è stato chiuso. Assicurarsi che la simulazione sia completata ed entrata in modalita' attesa comandi."
            }), 400

        # Ottimizza il prompt di ogni elemento dell'intervista, aggiungi prefisso per evitare che l'Agent chiami strumenti
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta Interview batch: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Interview batch fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    Intervista globale - usa la stessa domanda per intervistare tutti gli Agent

    Nota: questa funzione richiede che l'ambiente di simulazione sia in stato di esecuzione

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",            // obbligatorio, ID simulazione
            "prompt": "Qual e' la tua opinione complessiva su questo?",  // obbligatorio, domanda dell'intervista (stessa per tutti gli Agent)
            "platform": "reddit",                   // opzionale, specifica piattaforma (twitter/reddit)
                                                    // se non specificato: simulazione dual-platform intervista ogni Agent su entrambe le piattaforme
            "timeout": 180                          // opzionale, timeout (secondi), default 180
        }

    Risposta:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Opzionale: twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "Fornire prompt (domanda dell'intervista)"
            }), 400

        # Valida parametro platform
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "Il parametro platform puo' essere solo 'twitter' o 'reddit'"
            }), 400

        # Verifica stato ambiente
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "L'ambiente di simulazione non è in esecuzione o è stato chiuso. Assicurarsi che la simulazione sia completata ed entrata in modalita' attesa comandi."
            }), 400

        # Ottimizza prompt, aggiungi prefisso per evitare che l'Agent chiami strumenti
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Timeout in attesa della risposta Interview globale: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Interview globale fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    Ottieni lo storico delle Interview

    Legge tutti i record delle Interview dal database della simulazione

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",  // obbligatorio, ID simulazione
            "platform": "reddit",          // opzionale, tipo piattaforma (reddit/twitter)
                                           // se non specificato restituisce lo storico di entrambe le piattaforme
            "agent_id": 0,                 // opzionale, ottieni solo lo storico delle interviste di questo Agent
            "limit": 100                   // opzionale, numero di risultati, default 100
        }

    Risposta:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "Penso che...",
                        "prompt": "Cosa ne pensi di questo?",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # Se non specificato restituisce lo storico di entrambe le piattaforme
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"Ottenimento storico Interview fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    Ottieni lo stato dell'ambiente di simulazione

    Verifica se l'ambiente di simulazione è attivo (puo' ricevere comandi Interview)

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx"  // obbligatorio, ID simulazione
        }

    Risposta:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "L'ambiente è in esecuzione, puo' ricevere comandi Interview"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # Ottieni informazioni di stato piu' dettagliate
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "L'ambiente è in esecuzione, puo' ricevere comandi Interview"
        else:
            message = "L'ambiente non è in esecuzione o è stato chiuso"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"Ottenimento stato ambiente fallito: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    Chiudi l'ambiente di simulazione

    Invia un comando di chiusura all'ambiente di simulazione, facendolo uscire in modo ordinato dalla modalita' attesa comandi.

    Nota: questo è diverso dall'interfaccia /stop, che termina forzatamente il processo,
    mentre questa interfaccia fa chiudere l'ambiente di simulazione in modo ordinato.

    Richiesta (JSON):
        {
            "simulation_id": "sim_xxxx",  // obbligatorio, ID simulazione
            "timeout": 30                  // opzionale, timeout (secondi), default 30
        }

    Risposta:
        {
            "success": true,
            "data": {
                "message": "Comando di chiusura ambiente inviato",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Fornire simulation_id"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # Aggiorna stato simulazione
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Chiusura ambiente fallita: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
