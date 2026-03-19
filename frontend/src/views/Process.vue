<template>
  <div class="process-page">
    <!-- Barra di navigazione superiore -->
    <nav class="navbar">
      <div class="nav-brand" @click="goHome">MIROFISH</div>
      
      <!-- Indicatore passi centrale -->
      <div class="nav-center">
        <div class="step-badge">STEP 01</div>
        <div class="step-name">Costruzione Grafo</div>
      </div>

      <div class="nav-status">
        <span class="status-dot" :class="statusClass"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
    </nav>

    <!-- Area contenuto principale -->
    <div class="main-content">
      <!-- Pannello sinistro: visualizzazione grafo in tempo reale -->
      <div class="left-panel" :class="{ 'full-screen': isFullScreen }">
        <div class="panel-header">
          <div class="header-left">
            <span class="header-deco">◆</span>
            <span class="header-title">Knowledge Graph in tempo reale</span>
          </div>
          <div class="header-right">
            <template v-if="graphData">
              <span class="stat-item">{{ graphData.node_count || graphData.nodes?.length || 0 }} nodi</span>
              <span class="stat-divider">|</span>
              <span class="stat-item">{{ graphData.edge_count || graphData.edges?.length || 0 }} relazioni</span>
              <span class="stat-divider">|</span>
            </template>
            <div class="action-buttons">
                <button class="action-btn" @click="refreshGraph" :disabled="graphLoading" title="Aggiorna grafo">
                  <span class="icon-refresh" :class="{ 'spinning': graphLoading }">↻</span>
                </button>
                <button class="action-btn" @click="toggleFullScreen" :title="isFullScreen ? 'Esci da schermo intero' : 'Schermo intero'">
                  <span class="icon-fullscreen">{{ isFullScreen ? '↙' : '↗' }}</span>
                </button>
            </div>
          </div>
        </div>
        
        <div class="graph-container" ref="graphContainer">
          <!-- Visualizzazione grafo (mostrato quando ci sono dati) -->
          <div v-if="graphData" class="graph-view">
            <svg ref="graphSvg" class="graph-svg"></svg>
            <!-- Avviso costruzione in corso -->
            <div v-if="currentPhase === 1" class="graph-building-hint">
              <span class="building-dot"></span>
              Aggiornamento in corso...
            </div>
            
            <!-- Pannello dettagli nodo/arco -->
            <div v-if="selectedItem" class="detail-panel">
              <div class="detail-panel-header">
                <span class="detail-title">{{ selectedItem.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
                <span v-if="selectedItem.type === 'node'" class="detail-badge" :style="{ background: selectedItem.color }">
                  {{ selectedItem.entityType }}
                </span>
                <button class="detail-close" @click="closeDetailPanel">×</button>
              </div>
              
              <!-- Dettagli nodo -->
              <div v-if="selectedItem.type === 'node'" class="detail-content">
                <div class="detail-row">
                  <span class="detail-label">Name:</span>
                  <span class="detail-value highlight">{{ selectedItem.data.name }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">UUID:</span>
                  <span class="detail-value uuid">{{ selectedItem.data.uuid }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.created_at">
                  <span class="detail-label">Created:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.created_at) }}</span>
                </div>
                
                <!-- Properties / Attributes -->
                <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
                  <span class="detail-label">Properties:</span>
                  <div class="properties-list">
                    <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                      <span class="property-key">{{ key }}:</span>
                      <span class="property-value">{{ value }}</span>
                    </div>
                  </div>
                </div>
                
                <!-- Summary -->
                <div class="detail-section" v-if="selectedItem.data.summary">
                  <span class="detail-label">Summary:</span>
                  <p class="detail-summary">{{ selectedItem.data.summary }}</p>
                </div>
                
                <!-- Labels -->
                <div class="detail-row" v-if="selectedItem.data.labels?.length">
                  <span class="detail-label">Labels:</span>
                  <div class="detail-labels">
                    <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">{{ label }}</span>
                  </div>
                </div>
              </div>
              
              <!-- Dettagli arco -->
              <div v-else class="detail-content">
                <!-- Visualizzazione relazione -->
                <div class="edge-relation">
                  <span class="edge-source">{{ selectedItem.data.source_name || selectedItem.data.source_node_name }}</span>
                  <span class="edge-arrow">→</span>
                  <span class="edge-type">{{ selectedItem.data.name || selectedItem.data.fact_type || 'RELATED_TO' }}</span>
                  <span class="edge-arrow">→</span>
                  <span class="edge-target">{{ selectedItem.data.target_name || selectedItem.data.target_node_name }}</span>
                </div>
                
                <div class="detail-subtitle">Relationship</div>
                
                <div class="detail-row">
                  <span class="detail-label">UUID:</span>
                  <span class="detail-value uuid">{{ selectedItem.data.uuid }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Label:</span>
                  <span class="detail-value">{{ selectedItem.data.name || selectedItem.data.fact_type || 'RELATED_TO' }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.fact_type">
                  <span class="detail-label">Type:</span>
                  <span class="detail-value">{{ selectedItem.data.fact_type }}</span>
                </div>
                
                <!-- Fact -->
                <div class="detail-section" v-if="selectedItem.data.fact">
                  <span class="detail-label">Fact:</span>
                  <p class="detail-summary">{{ selectedItem.data.fact }}</p>
                </div>
                
                <!-- Episodes -->
                <div class="detail-section" v-if="selectedItem.data.episodes?.length">
                  <span class="detail-label">Episodes:</span>
                  <div class="episodes-list">
                    <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">{{ ep }}</span>
                  </div>
                </div>
                
                <div class="detail-row" v-if="selectedItem.data.created_at">
                  <span class="detail-label">Created:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.created_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.valid_at">
                  <span class="detail-label">Valid From:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.valid_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.invalid_at">
                  <span class="detail-label">Invalid At:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.invalid_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.expired_at">
                  <span class="detail-label">Expired At:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.expired_at) }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Stato di caricamento -->
          <div v-else-if="graphLoading" class="graph-loading">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="loading-text">Caricamento dati del grafo...</p>
          </div>
          
          <!-- In attesa della costruzione -->
          <div v-else-if="currentPhase < 1" class="graph-waiting">
            <div class="waiting-icon">
              <svg viewBox="0 0 100 100" class="network-icon">
                <circle cx="50" cy="20" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="20" cy="60" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="80" cy="60" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <circle cx="50" cy="80" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
                <line x1="50" y1="28" x2="25" y2="54" stroke="#000" stroke-width="1"/>
                <line x1="50" y1="28" x2="75" y2="54" stroke="#000" stroke-width="1"/>
                <line x1="28" y1="60" x2="72" y2="60" stroke="#000" stroke-width="1" stroke-dasharray="4"/>
                <line x1="50" y1="72" x2="26" y2="66" stroke="#000" stroke-width="1"/>
                <line x1="50" y1="72" x2="74" y2="66" stroke="#000" stroke-width="1"/>
              </svg>
            </div>
            <p class="waiting-text">In attesa della generazione ontologia</p>
            <p class="waiting-hint">La costruzione del grafo inizierà automaticamente al completamento</p>
          </div>
          
          <!-- Costruzione in corso ma nessun dato ancora -->
          <div v-else-if="currentPhase === 1 && !graphData" class="graph-waiting">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="waiting-text">Costruzione grafo in corso</p>
            <p class="waiting-hint">I dati appariranno a breve...</p>
          </div>
          
          <!-- Stato di errore -->
          <div v-else-if="error" class="graph-error">
            <span class="error-icon">⚠</span>
            <p>{{ error }}</p>
          </div>
        </div>
        
        <!-- Legenda grafo -->
        <div v-if="graphData" class="graph-legend">
          <div class="legend-item" v-for="type in entityTypes" :key="type.name">
            <span class="legend-dot" :style="{ background: type.color }"></span>
            <span class="legend-label">{{ type.name }}</span>
            <span class="legend-count">{{ type.count }}</span>
          </div>
        </div>
      </div>

      <!-- Pannello destro: dettagli flusso di costruzione -->
      <div class="right-panel" :class="{ 'hidden': isFullScreen }">
        <div class="panel-header dark-header">
          <span class="header-icon">▣</span>
          <span class="header-title">Flusso di costruzione</span>
        </div>

        <div class="process-content">
          <!-- Fase 1: Generazione Ontologia -->
          <div class="process-phase" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
            <div class="phase-header">
              <span class="phase-num">01</span>
              <div class="phase-info">
                <div class="phase-title">Generazione Ontologia</div>
                <div class="phase-api">/api/graph/ontology/generate</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(0)">
                {{ getPhaseStatusText(0) }}
              </span>
            </div>
            
            <div class="phase-detail">
              <div class="detail-section">
                <div class="detail-label">Descrizione API</div>
                <div class="detail-content">
                  Dopo il caricamento, l'LLM analizza i documenti e genera automaticamente una struttura ontologica adatta alla simulazione (tipi di entità + tipi di relazione)
                </div>
              </div>
              
              <!-- Progresso generazione ontologia -->
              <div class="detail-section" v-if="ontologyProgress && currentPhase === 0">
                <div class="detail-label">Progresso generazione</div>
                <div class="ontology-progress">
                  <div class="progress-spinner"></div>
                  <span class="progress-text">{{ ontologyProgress.message }}</span>
                </div>
              </div>
              
              <!-- Informazioni ontologia generata -->
              <div class="detail-section" v-if="projectData?.ontology">
                <div class="detail-label">Tipi di entità generati ({{ projectData.ontology.entity_types?.length || 0 }})</div>
                <div class="entity-tags">
                  <span 
                    v-for="entity in projectData.ontology.entity_types" 
                    :key="entity.name"
                    class="entity-tag"
                  >
                    {{ entity.name }}
                  </span>
                </div>
              </div>
              
              <div class="detail-section" v-if="projectData?.ontology">
                <div class="detail-label">Tipi di relazione generati ({{ projectData.ontology.relation_types?.length || 0 }})</div>
                <div class="relation-list">
                  <div 
                    v-for="(rel, idx) in projectData.ontology.relation_types?.slice(0, 5) || []" 
                    :key="idx"
                    class="relation-item"
                  >
                    <span class="rel-source">{{ rel.source_type }}</span>
                    <span class="rel-arrow">→</span>
                    <span class="rel-name">{{ rel.name }}</span>
                    <span class="rel-arrow">→</span>
                    <span class="rel-target">{{ rel.target_type }}</span>
                  </div>
                  <div v-if="(projectData.ontology.relation_types?.length || 0) > 5" class="relation-more">
                    +{{ projectData.ontology.relation_types.length - 5 }} altre relazioni...
                  </div>
                </div>
              </div>
              
              <!-- Stato di attesa -->
              <div class="detail-section waiting-state" v-if="!projectData?.ontology && currentPhase === 0 && !ontologyProgress">
                <div class="waiting-hint">In attesa della generazione ontologia...</div>
              </div>
            </div>
          </div>

          <!-- Fase 2: Costruzione Grafo -->
          <div class="process-phase" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
            <div class="phase-header">
              <span class="phase-num">02</span>
              <div class="phase-info">
                <div class="phase-title">Costruzione Grafo</div>
                <div class="phase-api">/api/graph/build</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(1)">
                {{ getPhaseStatusText(1) }}
              </span>
            </div>
            
            <div class="phase-detail">
              <div class="detail-section">
                <div class="detail-label">Descrizione API</div>
                <div class="detail-content">
                  Sulla base dell'ontologia, i documenti vengono suddivisi e Zep API costruisce il knowledge graph, estraendo entità e relazioni
                </div>
              </div>
              
              <!-- In attesa del completamento ontologia -->
              <div class="detail-section waiting-state" v-if="currentPhase < 1">
                <div class="waiting-hint">In attesa del completamento dell'ontologia...</div>
              </div>
              
              <!-- Progresso costruzione -->
              <div class="detail-section" v-if="buildProgress && currentPhase >= 1">
                <div class="detail-label">Progresso costruzione</div>
                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: buildProgress.progress + '%' }"></div>
                </div>
                <div class="progress-info">
                  <span class="progress-message">{{ buildProgress.message }}</span>
                  <span class="progress-percent">{{ buildProgress.progress }}%</span>
                </div>
              </div>
              
              <div class="detail-section" v-if="graphData">
                <div class="detail-label">Risultati costruzione</div>
                <div class="build-result">
                  <div class="result-item">
                    <span class="result-value">{{ graphData.node_count }}</span>
                    <span class="result-label">Nodi Entità</span>
                  </div>
                  <div class="result-item">
                    <span class="result-value">{{ graphData.edge_count }}</span>
                    <span class="result-label">Archi Relazione</span>
                  </div>
                  <div class="result-item">
                    <span class="result-value">{{ entityTypes.length }}</span>
                    <span class="result-label">Tipi Entità</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Fase 3: Completamento -->
          <div class="process-phase" :class="{ 'active': currentPhase === 2, 'completed': currentPhase > 2 }">
            <div class="phase-header">
              <span class="phase-num">03</span>
              <div class="phase-info">
                <div class="phase-title">Costruzione Completata</div>
                <div class="phase-api">Pronto per il prossimo passaggio</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(2)">
                {{ getPhaseStatusText(2) }}
              </span>
            </div>
          </div>

          <!-- Pulsante prossimo passo -->
          <div class="next-step-section" v-if="currentPhase >= 2">
            <button class="next-step-btn" @click="goToNextStep" :disabled="currentPhase < 2">
              Configura Ambiente
              <span class="btn-arrow">→</span>
            </button>
          </div>
        </div>

        <!-- Pannello informazioni progetto -->
        <div class="project-panel">
          <div class="project-header">
            <span class="project-icon">◇</span>
            <span class="project-title">Informazioni Progetto</span>
          </div>
          <div class="project-details" v-if="projectData">
            <div class="project-item">
              <span class="item-label">Nome progetto</span>
              <span class="item-value">{{ projectData.name }}</span>
            </div>
            <div class="project-item">
              <span class="item-label">ID progetto</span>
              <span class="item-value code">{{ projectData.project_id }}</span>
            </div>
            <div class="project-item" v-if="projectData.graph_id">
              <span class="item-label">ID grafo</span>
              <span class="item-value code">{{ projectData.graph_id }}</span>
            </div>
            <div class="project-item">
              <span class="item-label">Requisiti simulazione</span>
              <span class="item-value">{{ projectData.simulation_requirement || '-' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import * as d3 from 'd3'

const route = useRoute()
const router = useRouter()

// ID progetto corrente (può cambiare da 'new' all'ID effettivo)
const currentProjectId = ref(route.params.projectId)

// Stato
const loading = ref(true)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const buildProgress = ref(null)
const ontologyProgress = ref(null) // Progresso generazione ontologia
const currentPhase = ref(-1) // -1: caricamento, 0: generazione ontologia, 1: costruzione grafo, 2: completato
const selectedItem = ref(null) // Nodo o arco selezionato
const isFullScreen = ref(false)

// Riferimenti DOM
const graphContainer = ref(null)
const graphSvg = ref(null)

// Timer polling
let pollTimer = null

// Proprietà calcolate
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return 'Costruzione fallita'
  if (currentPhase.value >= 2) return 'Costruzione completata'
  if (currentPhase.value === 1) return 'Costruzione grafo in corso'
  if (currentPhase.value === 0) return 'Generazione ontologia in corso'
  return 'Inizializzazione in corso'
})

const entityTypes = computed(() => {
  if (!graphData.value?.nodes) return []
  
  const typeMap = {}
  const colors = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C']
  
  graphData.value.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  
  return Object.values(typeMap)
})

// Metodi
const goHome = () => {
  router.push('/')
}

const goToNextStep = () => {
  // TODO: Passaggio alla configurazione ambiente
  alert('Funzionalità configurazione ambiente in sviluppo...')
}

const toggleFullScreen = () => {
  isFullScreen.value = !isFullScreen.value
  // Wait for transition to finish then re-render graph
  setTimeout(() => {
    renderGraph()
  }, 350) 
}

// Chiudi pannello dettagli
const closeDetailPanel = () => {
  selectedItem.value = null
}

// Formattazione data
const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('it-IT', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

// Seleziona nodo
const selectNode = (nodeData, color) => {
  selectedItem.value = {
    type: 'node',
    data: nodeData,
    color: color,
    entityType: nodeData.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity'
  }
}

// Seleziona arco
const selectEdge = (edgeData) => {
  selectedItem.value = {
    type: 'edge',
    data: edgeData
  }
}

const getPhaseStatusClass = (phase) => {
  if (currentPhase.value > phase) return 'completed'
  if (currentPhase.value === phase) return 'active'
  return 'pending'
}

const getPhaseStatusText = (phase) => {
  if (currentPhase.value > phase) return 'Completato'
  if (currentPhase.value === phase) {
    if (phase === 1 && buildProgress.value) {
      return `${buildProgress.value.progress}%`
    }
    return 'In corso'
  }
  return 'In attesa'
}

// Inizializzazione - gestisce nuovo progetto o caricamento progetto esistente
const initProject = async () => {
  const paramProjectId = route.params.projectId
  
  if (paramProjectId === 'new') {
    // Nuovo progetto: ottieni i dati da caricare dallo store
    await handleNewProject()
  } else {
    // Carica progetto esistente
    currentProjectId.value = paramProjectId
    await loadProject()
  }
}

// Gestione nuovo progetto - chiama API ontology/generate
const handleNewProject = async () => {
  const pending = getPendingUpload()
  
  if (!pending.isPending || pending.files.length === 0) {
    error.value = 'Nessun file da caricare, torna alla homepage e riprova'
    loading.value = false
    return
  }
  
  try {
    loading.value = true
    currentPhase.value = 0 // Fase generazione ontologia
    ontologyProgress.value = { message: 'Caricamento file e analisi documenti in corso...' }
    
    // Costruisci FormData
    const formDataObj = new FormData()
    pending.files.forEach(file => {
      formDataObj.append('files', file)
    })
    formDataObj.append('simulation_requirement', pending.simulationRequirement)
    
    // Chiama API generazione ontologia
    const response = await generateOntology(formDataObj)
    
    if (response.success) {
      // Cancella dati in attesa di caricamento
      clearPendingUpload()
      
      // Aggiorna ID progetto e dati
      currentProjectId.value = response.data.project_id
      projectData.value = response.data
      
      // Aggiorna URL (senza ricaricare la pagina)
      router.replace({
        name: 'Process',
        params: { projectId: response.data.project_id }
      })
      
      ontologyProgress.value = null
      
      // Avvia automaticamente la costruzione del grafo
      await startBuildGraph()
    } else {
      error.value = response.error || 'Generazione ontologia fallita'
    }
  } catch (err) {
    console.error('Handle new project error:', err)
    error.value = 'Inizializzazione progetto fallita: ' + (err.message || 'Errore sconosciuto')
  } finally {
    loading.value = false
  }
}

// Carica dati progetto esistente
const loadProject = async () => {
  try {
    loading.value = true
    const response = await getProject(currentProjectId.value)
    
    if (response.success) {
      projectData.value = response.data
      updatePhaseByStatus(response.data.status)
      
      // Avvia automaticamente la costruzione del grafo
      if (response.data.status === 'ontology_generated' && !response.data.graph_id) {
        await startBuildGraph()
      }
      
      // Continua polling dei task in costruzione
      if (response.data.status === 'graph_building' && response.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(response.data.graph_build_task_id)
      }
      
      // Carica grafo completato
      if (response.data.status === 'graph_completed' && response.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(response.data.graph_id)
      }
    } else {
      error.value = response.error || 'Caricamento progetto fallito'
    }
  } catch (err) {
    console.error('Load project error:', err)
    error.value = 'Caricamento progetto fallito: ' + (err.message || 'Errore sconosciuto')
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated':
      currentPhase.value = 0
      break
    case 'graph_building':
      currentPhase.value = 1
      break
    case 'graph_completed':
      currentPhase.value = 2
      break
    case 'failed':
      error.value = projectData.value?.error || 'Elaborazione fallita'
      break
  }
}

// Avvia costruzione grafo
const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    // Imposta progresso iniziale
    buildProgress.value = {
      progress: 0,
      message: 'Avvio costruzione grafo...'
    }
    
    const response = await buildGraph({ project_id: currentProjectId.value })
    
    if (response.success) {
      buildProgress.value.message = 'Task di costruzione grafo avviato...'

      // Salva task_id per il polling
      const taskId = response.data.task_id
      
      // Avvia polling dati grafo (indipendente dal polling stato task)
      startGraphPolling()
      
      // Avvia polling stato task
      startPollingTask(taskId)
    } else {
      error.value = response.error || 'Avvio costruzione grafo fallito'
      buildProgress.value = null
    }
  } catch (err) {
    console.error('Build graph error:', err)
    error.value = 'Avvio costruzione grafo fallito: ' + (err.message || 'Errore sconosciuto')
    buildProgress.value = null
  }
}

// Timer polling dati grafo
let graphPollTimer = null

// Avvia polling dati grafo
const startGraphPolling = () => {
  // Recupera immediatamente una volta
  fetchGraphData()
  
  // Recupera automaticamente i dati del grafo ogni 10 secondi
  graphPollTimer = setInterval(async () => {
    await fetchGraphData()
  }, 10000)
}

// Aggiorna grafo manualmente
const refreshGraph = async () => {
  graphLoading.value = true
  await fetchGraphData()
  graphLoading.value = false
}

// Ferma polling dati grafo
const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
  }
}

// Recupera dati grafo
const fetchGraphData = async () => {
  try {
    // Prima ottieni le informazioni del progetto per il graph_id
    const projectResponse = await getProject(currentProjectId.value)
    
    if (projectResponse.success && projectResponse.data.graph_id) {
      const graphId = projectResponse.data.graph_id
      projectData.value = projectResponse.data
      
      // Recupera dati grafo
      const graphResponse = await getGraphData(graphId)
      
      if (graphResponse.success && graphResponse.data) {
        const newData = graphResponse.data
        const newNodeCount = newData.node_count || newData.nodes?.length || 0
        const oldNodeCount = graphData.value?.node_count || graphData.value?.nodes?.length || 0
        
        console.log('Fetching graph data, nodes:', newNodeCount, 'edges:', newData.edge_count || newData.edges?.length || 0)
        
        // Aggiorna rendering quando i dati cambiano
        if (newNodeCount !== oldNodeCount || !graphData.value) {
          graphData.value = newData
          await nextTick()
          renderGraph()
        }
      }
    }
  } catch (err) {
    console.log('Graph data fetch:', err.message || 'not ready')
  }
}

// Polling stato task
const startPollingTask = (taskId) => {
  // Esegui immediatamente una query
  pollTaskStatus(taskId)
  
  // Poi polling periodico
  pollTimer = setInterval(() => {
    pollTaskStatus(taskId)
  }, 2000)
}

// Interroga stato task
const pollTaskStatus = async (taskId) => {
  try {
    const response = await getTaskStatus(taskId)
    
    if (response.success) {
      const task = response.data
      
      // Aggiorna visualizzazione progresso
      buildProgress.value = {
        progress: task.progress || 0,
        message: task.message || 'Elaborazione in corso...'
      }
      
      console.log('Task status:', task.status, 'Progress:', task.progress)
      
      if (task.status === 'completed') {
        console.log('Costruzione grafo completata, caricamento dati completi...')
        
        stopPolling()
        stopGraphPolling()
        currentPhase.value = 2
        
        // Aggiorna visualizzazione progresso a stato completato
        buildProgress.value = {
          progress: 100,
          message: 'Costruzione completata, caricamento grafo...'
        }
        
        // Ricarica dati progetto per ottenere graph_id
        const projectResponse = await getProject(currentProjectId.value)
        if (projectResponse.success) {
          projectData.value = projectResponse.data
          
          // Carica dati completi del grafo
          if (projectResponse.data.graph_id) {
            console.log('Caricamento grafo completo:', projectResponse.data.graph_id)
            await loadGraph(projectResponse.data.graph_id)
            console.log('Caricamento grafo completato')
          }
        }
        
        // Cancella visualizzazione progresso
        buildProgress.value = null
      } else if (task.status === 'failed') {
        stopPolling()
        stopGraphPolling()
        error.value = 'Costruzione grafo fallita: ' + (task.error || 'Errore sconosciuto')
        buildProgress.value = null
      }
    }
  } catch (err) {
    console.error('Poll task error:', err)
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Carica dati grafo
const loadGraph = async (graphId) => {
  try {
    graphLoading.value = true
    const response = await getGraphData(graphId)
    
    if (response.success) {
      graphData.value = response.data
      await nextTick()
      renderGraph()
    }
  } catch (err) {
    console.error('Load graph error:', err)
  } finally {
    graphLoading.value = false
  }
}

// Rendering grafo (D3.js)
const renderGraph = () => {
  if (!graphSvg.value || !graphData.value) {
    console.log('Cannot render: svg or data missing')
    return
  }
  
  const container = graphContainer.value
  if (!container) {
    console.log('Cannot render: container missing')
    return
  }
  
  // Ottieni dimensioni container
  const rect = container.getBoundingClientRect()
  const width = rect.width || 800
  const height = (rect.height || 600) - 60
  
  if (width <= 0 || height <= 0) {
    console.log('Cannot render: invalid dimensions', width, height)
    return
  }
  
  console.log('Rendering graph:', width, 'x', height)
  
  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
  
  svg.selectAll('*').remove()
  
  // Elabora dati nodi
  const nodesData = graphData.value.nodes || []
  const edgesData = graphData.value.edges || []
  
  if (nodesData.length === 0) {
    console.log('No nodes to render')
    // Mostra stato vuoto
    svg.append('text')
      .attr('x', width / 2)
      .attr('y', height / 2)
      .attr('text-anchor', 'middle')
      .attr('fill', '#999')
      .text('In attesa dei dati del grafo...')
    return
  }
  
  // Crea mappa nodi per ricerca nomi
  const nodeMap = {}
  nodesData.forEach(n => {
    nodeMap[n.uuid] = n
  })
  
  const nodes = nodesData.map(n => ({
    id: n.uuid,
    name: n.name || 'Senza nome',
    type: n.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity',
    rawData: n // Salva dati originali
  }))
  
  // Crea set ID nodi per filtrare archi validi
  const nodeIds = new Set(nodes.map(n => n.id))
  
  const edges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
    .map(e => ({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || 'RELATED_TO',
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name || 'Sconosciuto',
        target_name: nodeMap[e.target_node_uuid]?.name || 'Sconosciuto'
      }
    }))
  
  console.log('Nodes:', nodes.length, 'Edges:', edges.length)
  
  // Mappatura colori
  const types = [...new Set(nodes.map(n => n.type))]
  const colorScale = d3.scaleOrdinal()
    .domain(types)
    .range(['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#2D3436', '#6C5CE7'])
  
  // Layout forza-direzione
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(100).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(40))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05))
  
  // Aggiungi funzionalità zoom
  const g = svg.append('g')
  
  svg.call(d3.zoom()
    .extent([[0, 0], [width, height]])
    .scaleExtent([0.2, 4])
    .on('zoom', (event) => {
      g.attr('transform', event.transform)
    }))
  
  // Disegna archi (con linea trasparente larga cliccabile)
  const linkGroup = g.append('g')
    .attr('class', 'links')
    .selectAll('g')
    .data(edges)
    .enter()
    .append('g')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      selectEdge(d.rawData)
    })
  
  // Linea sottile visibile
  const link = linkGroup.append('line')
    .attr('stroke', '#ccc')
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.6)
  
  // Linea larga trasparente per area cliccabile
  linkGroup.append('line')
    .attr('stroke', 'transparent')
    .attr('stroke-width', 10)
  
  // Etichette archi
  const linkLabel = g.append('g')
    .attr('class', 'link-labels')
    .selectAll('text')
    .data(edges)
    .enter()
    .append('text')
    .attr('font-size', '9px')
    .attr('fill', '#999')
    .attr('text-anchor', 'middle')
    .text(d => d.type.length > 15 ? d.type.substring(0, 12) + '...' : d.type)
  
  // Disegna nodi
  const node = g.append('g')
    .attr('class', 'nodes')
    .selectAll('g')
    .data(nodes)
    .enter()
    .append('g')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      selectNode(d.rawData, colorScale(d.type))
    })
    .call(d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended))
  
  node.append('circle')
    .attr('r', 10)
    .attr('fill', d => colorScale(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .attr('class', 'node-circle')
  
  node.append('text')
    .attr('dx', 14)
    .attr('dy', 4)
    .text(d => d.name?.substring(0, 12) || '')
    .attr('font-size', '11px')
    .attr('fill', '#333')
    .attr('font-family', 'JetBrains Mono, monospace')
  
  // Click su area vuota chiude il pannello dettagli
  svg.on('click', () => {
    closeDetailPanel()
  })
  
  simulation.on('tick', () => {
    // Aggiorna posizione di tutti gli archi (linea visibile e area clic trasparente)
    linkGroup.selectAll('line')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)
    
    // Aggiorna posizione etichette archi
    linkLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 5)
    
    node.attr('transform', d => `translate(${d.x},${d.y})`)
  })
  
  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart()
    event.subject.fx = event.subject.x
    event.subject.fy = event.subject.y
  }
  
  function dragged(event) {
    event.subject.fx = event.x
    event.subject.fy = event.y
  }
  
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0)
    event.subject.fx = null
    event.subject.fy = null
  }
}

// Osserva cambiamenti nei dati del grafo
watch(graphData, () => {
  if (graphData.value) {
    nextTick(() => renderGraph())
  }
})

// Ciclo di vita
onMounted(() => {
  initProject()
})

onUnmounted(() => {
  stopPolling()
  stopGraphPolling()
})
</script>

<style scoped>
/* Variabili */
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF6B35;
  --gray-light: #F5F5F5;
  --gray-border: #E0E0E0;
  --gray-text: #666666;
}

.process-page {
  min-height: 100vh;
  background: var(--white);
  font-family: 'JetBrains Mono', 'Noto Sans SC', monospace;
  overflow: hidden; /* Prevent body scroll in fullscreen */
}

/* Barra di navigazione */
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #000;
  color: #fff;
  z-index: 10;
  position: relative;
}

.nav-brand {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: opacity 0.2s;
}

.nav-brand:hover {
  opacity: 0.8;
}

.nav-center {
  display: flex;
  align-items: center;
  gap: 12px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.step-badge {
  background: #FF6B35;
  color: #fff;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  border-radius: 2px;
}

.step-name {
  font-size: 0.85rem;
  letter-spacing: 0.05em;
  color: #fff;
}

.nav-status {
  display: flex;
  align-items: center;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #666;
  margin-right: 8px;
}

.status-dot.processing {
  background: #FF6B35;
  animation: pulse 1.5s infinite;
}

.status-dot.completed {
  background: #1A936F;
}

.status-dot.error {
  background: #C5283D;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 0.75rem;
  color: #999;
}

/* Area contenuto principale */
.main-content {
  display: flex;
  height: calc(100vh - 56px);
  position: relative;
}

/* Pannello sinistro - 50% default */
.left-panel {
  width: 50%;
  flex: none; /* Fixed width initially */
  display: flex;
  flex-direction: column;
  border-right: 1px solid #E0E0E0;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  background: #fff;
  z-index: 5;
}

.left-panel.full-screen {
  width: 100%;
  border-right: none;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #E0E0E0;
  background: #fff;
  height: 50px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-deco {
  color: #FF6B35;
  font-size: 0.8rem;
}

.header-title {
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 0.75rem;
  color: #666;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-val {
  font-weight: 600;
  color: #333;
}

.stat-divider {
  color: #eee;
}

.action-buttons {
    display: flex;
    align-items: center;
    gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  color: #666;
  border-radius: 2px;
}

.action-btn:hover:not(:disabled) {
  background: #F5F5F5;
  color: #000;
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.icon-refresh, .icon-fullscreen {
  font-size: 1rem;
  line-height: 1;
}

.icon-refresh.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Container grafo */
.graph-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.graph-loading,
.graph-waiting,
.graph-error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.loading-animation {
  position: relative;
  width: 80px;
  height: 80px;
  margin: 0 auto 20px;
}

.loading-ring {
  position: absolute;
  border: 2px solid transparent;
  border-radius: 50%;
  animation: ring-rotate 1.5s linear infinite;
}

.loading-ring:nth-child(1) {
  width: 80px;
  height: 80px;
  border-top-color: #000;
}

.loading-ring:nth-child(2) {
  width: 60px;
  height: 60px;
  top: 10px;
  left: 10px;
  border-right-color: #FF6B35;
  animation-delay: 0.2s;
}

.loading-ring:nth-child(3) {
  width: 40px;
  height: 40px;
  top: 20px;
  left: 20px;
  border-bottom-color: #666;
  animation-delay: 0.4s;
}

@keyframes ring-rotate {
  to { transform: rotate(360deg); }
}

.loading-text,
.waiting-text {
  font-size: 0.9rem;
  color: #333;
  margin: 0 0 8px;
}

.waiting-hint {
  font-size: 0.8rem;
  color: #999;
  margin: 0;
}

.waiting-icon {
  margin-bottom: 20px;
}

.network-icon {
  width: 100px;
  height: 100px;
  opacity: 0.6;
}

.graph-view {
  width: 100%;
  height: 100%;
  position: relative;
}

.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-building-hint {
  position: absolute;
  bottom: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255, 107, 53, 0.1);
  border: 1px solid #FF6B35;
  font-size: 0.8rem;
  color: #FF6B35;
}

.building-dot {
  width: 8px;
  height: 8px;
  background: #FF6B35;
  border-radius: 50%;
  animation: pulse 1s infinite;
}

/* Pannello dettagli nodo/arco */
.detail-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 320px;
  max-height: calc(100% - 32px);
  background: #fff;
  border: 1px solid #E0E0E0;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.detail-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #E0E0E0;
}

.detail-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
}

.detail-badge {
  padding: 2px 10px;
  font-size: 0.75rem;
  color: #fff;
  border-radius: 2px;
}

.detail-close {
  margin-left: auto;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  font-size: 1.2rem;
  color: #999;
  cursor: pointer;
  transition: color 0.2s;
}

.detail-close:hover {
  color: #333;
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}

.detail-label {
  font-size: 0.8rem;
  color: #999;
  min-width: 70px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 0.85rem;
  color: #333;
  word-break: break-word;
}

.detail-value.uuid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-summary {
  margin: 8px 0 0 0;
  font-size: 0.85rem;
  color: #333;
  line-height: 1.6;
  padding: 10px;
  background: #F9F9F9;
  border-left: 3px solid #FF6B35;
}

.detail-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.label-tag {
  padding: 2px 8px;
  font-size: 0.75rem;
  background: #F0F0F0;
  border: 1px solid #E0E0E0;
  color: #666;
}

/* Visualizzazione relazione arco */
.edge-relation {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: #F9F9F9;
  border: 1px solid #E0E0E0;
}

.edge-source,
.edge-target {
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
}

.edge-arrow {
  color: #999;
}

.edge-type {
  padding: 2px 8px;
  font-size: 0.75rem;
  background: #FF6B35;
  color: #fff;
}

.detail-value.highlight {
  font-weight: 600;
  color: #000;
}

.detail-subtitle {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #E0E0E0;
}

/* Lista proprietà */
.properties-list {
  margin-top: 8px;
  padding: 10px;
  background: #F9F9F9;
  border: 1px solid #E0E0E0;
}

.property-item {
  display: flex;
  margin-bottom: 6px;
  font-size: 0.85rem;
}

.property-item:last-child {
  margin-bottom: 0;
}

.property-key {
  color: #666;
  margin-right: 8px;
  font-family: 'JetBrains Mono', monospace;
}

.property-value {
  color: #333;
  word-break: break-word;
}

/* Lista episodi */
.episodes-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-tag {
  display: block;
  padding: 6px 10px;
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  background: #F0F0F0;
  border: 1px solid #E0E0E0;
  color: #666;
  word-break: break-all;
}

.error-icon {
  font-size: 2rem;
  display: block;
  margin-bottom: 10px;
}

/* Legenda grafo */
.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 24px;
  border-top: 1px solid #E0E0E0;
  background: #FAFAFA;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-label {
  color: #333;
}

.legend-count {
  color: #999;
}

/* Pannello destro - 50% default */
.right-panel {
  width: 50%;
  flex: none;
  display: flex;
  flex-direction: column;
  background: #fff;
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, transform 0.3s ease;
  overflow: hidden;
  opacity: 1;
}

.right-panel.hidden {
  width: 0;
  opacity: 0;
  transform: translateX(20px);
  pointer-events: none;
}

.right-panel .panel-header.dark-header {
  background: #000;
  color: #fff;
  border-bottom: none;
}

.right-panel .header-icon {
  color: #FF6B35;
  margin-right: 8px;
}

/* Contenuto flusso */
.process-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* Fasi del flusso */
.process-phase {
  margin-bottom: 24px;
  border: 1px solid #E0E0E0;
  opacity: 0.5;
  transition: all 0.3s;
}

.process-phase.active,
.process-phase.completed {
  opacity: 1;
}

.process-phase.active {
  border-color: #FF6B35;
}

.process-phase.completed {
  border-color: #1A936F;
}

.phase-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #E0E0E0;
}

.process-phase.active .phase-header {
  background: #FFF5F2;
}

.process-phase.completed .phase-header {
  background: #F2FAF6;
}

.phase-num {
  font-size: 1.5rem;
  font-weight: 700;
  color: #ddd;
  line-height: 1;
}

.process-phase.active .phase-num {
  color: #FF6B35;
}

.process-phase.completed .phase-num {
  color: #1A936F;
}

.phase-info {
  flex: 1;
}

.phase-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.phase-api {
  font-size: 0.75rem;
  color: #999;
  font-family: 'JetBrains Mono', monospace;
}

.phase-status {
  font-size: 0.75rem;
  padding: 4px 10px;
  background: #eee;
  color: #666;
}

.phase-status.active {
  background: #FF6B35;
  color: #fff;
}

.phase-status.completed {
  background: #1A936F;
  color: #fff;
}

/* Dettagli fase */
.phase-detail {
  padding: 16px;
}

/* Tag entità */
.entity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  font-size: 0.75rem;
  padding: 4px 10px;
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  color: #333;
}

/* Lista relazioni */
.relation-list {
  font-size: 0.8rem;
}

.relation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed #eee;
}

.relation-item:last-child {
  border-bottom: none;
}

.rel-source,
.rel-target {
  color: #333;
}

.rel-arrow {
  color: #ccc;
}

.rel-name {
  color: #FF6B35;
  font-weight: 500;
}

.relation-more {
  padding-top: 8px;
  color: #999;
  font-size: 0.75rem;
}

/* Progresso generazione ontologia */
.ontology-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #FFF5F2;
  border: 1px solid #FFE0D6;
}

.progress-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #FFE0D6;
  border-top-color: #FF6B35;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.progress-text {
  font-size: 0.85rem;
  color: #333;
}

/* Stato di attesa */
.waiting-state {
  padding: 16px;
  background: #F9F9F9;
  border: 1px dashed #E0E0E0;
  text-align: center;
}

.waiting-hint {
  font-size: 0.85rem;
  color: #999;
}

/* Barra di progresso */
.progress-bar {
  height: 6px;
  background: #E0E0E0;
  margin-bottom: 8px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #FF6B35;
  transition: width 0.3s;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
}

.progress-message {
  color: #666;
}

.progress-percent {
  color: #FF6B35;
  font-weight: 600;
}

/* Risultati costruzione */
.build-result {
  display: flex;
  gap: 16px;
}

.result-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: #F5F5F5;
}

.result-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #000;
  margin-bottom: 4px;
}

.result-label {
  font-size: 0.7rem;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Pulsante prossimo passo */
.next-step-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #E0E0E0;
}

.next-step-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  background: #000;
  color: #fff;
  border: none;
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s;
}

.next-step-btn:hover:not(:disabled) {
  background: #FF6B35;
}

.next-step-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-arrow {
  font-size: 1.2rem;
}

/* Pannello informazioni progetto */
.project-panel {
  border-top: 1px solid #E0E0E0;
  background: #FAFAFA;
}

.project-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  border-bottom: 1px solid #E0E0E0;
}

.project-icon {
  color: #FF6B35;
}

.project-title {
  font-size: 0.85rem;
  font-weight: 600;
}

.project-details {
  padding: 16px 24px;
}

.project-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px dashed #E0E0E0;
  font-size: 0.8rem;
}

.project-item:last-child {
  border-bottom: none;
}

.item-label {
  color: #999;
  flex-shrink: 0;
}

.item-value {
  color: #333;
  text-align: right;
  max-width: 60%;
  word-break: break-all;
}

.item-value.code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}

/* Responsive */
@media (max-width: 1024px) {
  .main-content {
    flex-direction: column;
  }
  
  .left-panel {
    width: 100% !important;
    border-right: none;
    border-bottom: 1px solid #E0E0E0;
    height: 50vh;
  }
  
  .right-panel {
    width: 100% !important;
    height: 50vh;
    opacity: 1 !important;
    transform: none !important;
  }
  
  .right-panel.hidden {
      display: none;
  }
}
</style>