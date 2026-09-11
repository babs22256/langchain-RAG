import request from './request'

export const listSessions = () => request.get('/sessions')
export const createSession = () => request.post('/sessions')
export const listMessages = (sessionId) => request.get(`/sessions/${sessionId}/messages`)
export const deleteSession = (sessionId) => request.delete(`/sessions/${sessionId}`)
