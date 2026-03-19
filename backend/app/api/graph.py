"""
Route API per il grafo
Meccanismo di contesto progetto con stato persistente lato server
"""

import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# Ottieni il logger
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """Verifica se l'estensione del file è consentita"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Interfacce gestione progetto ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    Ottieni dettagli del progetto
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"Progetto non trovato: {project_id}"
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    Elenca tutti i progetti
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    Elimina progetto
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"Progetto non trovato o eliminazione fallita: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"Progetto eliminato: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    Reimposta lo stato del progetto (per ricostruire il grafo)
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"Progetto non trovato: {project_id}"
        }), 404
    
    # Reimposta allo stato di ontologia generata
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": f"Progetto reimpostato: {project_id}",
        "data": project.to_dict()
    })


# ============== Interfaccia 1: Caricamento file e generazione ontologia ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    Interfaccia 1: Carica file, analizza e genera definizione ontologia

    Metodo richiesta: multipart/form-data

    Parametri:
        files: File caricati (PDF/MD/TXT), multipli consentiti
        simulation_requirement: Descrizione dei requisiti di simulazione (obbligatorio)
        project_name: Nome progetto (opzionale)
        additional_context: Note aggiuntive (opzionale)

    Risposta:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== Inizio generazione definizione ontologia ===")

        # Ottieni parametri
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"Nome progetto: {project_name}")
        logger.debug(f"Requisiti simulazione: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Fornire la descrizione dei requisiti di simulazione (simulation_requirement)"
            }), 400
        
        # Ottieni i file caricati
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "Caricare almeno un file documento"
            }), 400
        
        # Crea progetto
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"Progetto creato: {project.project_id}")
        
        # Salva file ed estrai testo
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # Salva file nella directory del progetto
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # Estrai testo
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "Nessun documento elaborato con successo, verificare il formato dei file"
            }), 400
        
        # Salva il testo estratto
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Estrazione testo completata, totale {len(all_text)} caratteri")
        
        # Genera ontologia
        logger.info("Chiamata LLM per generare definizione ontologia...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # Salva ontologia nel progetto
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Generazione ontologia completata: {entity_count} tipi di entità, {edge_count} tipi di relazione")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== Generazione ontologia completata === ID progetto: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfaccia 2: Costruzione grafo ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    Interfaccia 2: Costruisci grafo in base al project_id

    Richiesta (JSON):
        {
            "project_id": "proj_xxxx",  // obbligatorio, dall'interfaccia 1
            "graph_name": "Nome grafo",  // opzionale
            "chunk_size": 500,          // opzionale, default 500
            "chunk_overlap": 50         // opzionale, default 50
        }

    Risposta:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Attività di costruzione grafo avviata"
            }
        }
    """
    try:
        logger.info("=== Inizio costruzione grafo ===")

        # Verifica configurazione
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("ZEP_API_KEY non configurata")
        if errors:
            logger.error(f"Errore di configurazione: {errors}")
            return jsonify({
                "success": False,
                "error": "Errore di configurazione: " + "; ".join(errors)
            }), 500
        
        # Analizza richiesta
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"Parametri richiesta: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "Fornire project_id"
            }), 400
        
        # Ottieni progetto
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Progetto non trovato: {project_id}"
            }), 404
        
        # Verifica stato progetto
        force = data.get('force', False)  # Forza ricostruzione
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "Ontologia non ancora generata per il progetto, chiamare prima /ontology/generate"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "Costruzione grafo in corso, non inviare richieste duplicate. Per forzare la ricostruzione, aggiungere force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        # Se ricostruzione forzata, reimposta stato
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # Ottieni configurazione
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        
        # Aggiorna configurazione progetto
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # Ottieni il testo estratto
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "Contenuto testuale estratto non trovato"
            }), 400
        
        # Ottieni ontologia
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "Definizione ontologia non trovata"
            }), 400
        
        # Crea attività asincrona
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Costruzione grafo: {graph_name}")
        logger.info(f"Attività costruzione grafo creata: task_id={task_id}, project_id={project_id}")
        
        # Aggiorna stato progetto
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # Avvia attività in background
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] Inizio costruzione grafo...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="Inizializzazione servizio costruzione grafo..."
                )
                
                # Crea servizio costruzione grafo
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                
                # Suddivisione in blocchi
                task_manager.update_task(
                    task_id,
                    message="Suddivisione testo in blocchi...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                # Crea grafo
                task_manager.update_task(
                    task_id,
                    message="Creazione grafo Zep...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                # Aggiorna graph_id del progetto
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                # Imposta ontologia
                task_manager.update_task(
                    task_id,
                    message="Impostazione definizione ontologia...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # Aggiungi testo (firma progress_callback: (msg, progress_ratio))
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                task_manager.update_task(
                    task_id,
                    message=f"Inizio aggiunta di {total_chunks} blocchi di testo...",
                    progress=15
                )
                
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )
                
                # Attendi completamento elaborazione Zep (verifica stato processed di ogni episode)
                task_manager.update_task(
                    task_id,
                    message="In attesa dell'elaborazione dati Zep...",
                    progress=55
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                # Ottieni dati del grafo
                task_manager.update_task(
                    task_id,
                    message="Recupero dati del grafo...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # Aggiorna stato progetto
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] Costruzione grafo completata: graph_id={graph_id}, nodi={node_count}, archi={edge_count}")
                
                # Completato
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="Costruzione grafo completata",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                # Aggiorna stato progetto a fallito
                build_logger.error(f"[{task_id}] Costruzione grafo fallita: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"Costruzione fallita: {str(e)}",
                    error=traceback.format_exc()
                )
        
        # Avvia thread in background
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "Attività di costruzione grafo avviata, verificare lo stato tramite /task/{task_id}"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interfacce query attività ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    Query stato attività
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": f"Attività non trovata: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    Elenca tutte le attività
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Interfacce dati grafo ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    Ottieni dati del grafo (nodi e archi)
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY non configurata"
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)
        
        return jsonify({
            "success": True,
            "data": graph_data
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    Elimina grafo Zep
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY non configurata"
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": f"Grafo eliminato: {graph_id}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
