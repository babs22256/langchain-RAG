import request from './request'

export const uploadDocument = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/kb/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const listDocuments = () => request.get('/kb/documents')
export const previewChunks = (docId) => request.get(`/kb/documents/${docId}/chunks`)
export const deleteDocument = (docId) => request.delete(`/kb/documents/${docId}`)
export const getKBStats = () => request.get('/kb/stats')
