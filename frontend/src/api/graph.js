import service, { requestWithRetry } from './index'

/**
 * Genera l'ontologia (caricamento documenti e requisiti di simulazione)
 * @param {Object} data - contiene files, simulation_requirement, project_name ecc.
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Costruisci il grafo
 * @param {Object} data - contiene project_id, graph_name ecc.
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Interroga lo stato del task
 * @param {String} taskId - ID del task
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Ottieni i dati del grafo
 * @param {String} graphId - ID del grafo
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Ottieni le informazioni del progetto
 * @param {String} projectId - ID del progetto
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}
