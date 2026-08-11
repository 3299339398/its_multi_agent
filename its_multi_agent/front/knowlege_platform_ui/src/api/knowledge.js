import request from './request'

export function uploadFile(data) {
  return request({
    url: '/knowledge/upload',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function queryKnowledge(data) {
  return request({
    url: '/knowledge/query',
    method: 'post',
    data
  })
}

export function listDocuments(params) {
  return request({
    url: '/knowledge/documents',
    method: 'get',
    params
  })
}

export function getDocumentStatistics() {
  return request({
    url: '/knowledge/documents/statistics',
    method: 'get'
  })
}

export function deleteDocument(documentHash) {
  return request({
    url: `/knowledge/documents/${encodeURIComponent(documentHash)}`,
    method: 'delete'
  })
}

export function getIngestionTask(taskId) {
  return request({ url: `/knowledge/tasks/${encodeURIComponent(taskId)}`, method: 'get' })
}

export function retryIngestionTask(taskId) {
  return request({ url: `/knowledge/tasks/${encodeURIComponent(taskId)}/retry`, method: 'post' })
}
