import request from './request'

export const sendChat = (data) => request.post('/chat', data)
