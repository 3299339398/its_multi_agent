import { authFetch, readErrorMessage } from '../api/auth'

export const isHtmlArtifact = file => file?.mime_type === 'text/html' && /\.html?$/i.test(file.filename || '')

export const downloadArtifact = async file => {
  const response = await authFetch(`/api/files/${encodeURIComponent(file.id)}/download`)
  if (!response.ok) throw new Error(await readErrorMessage(response, '下载失败'))
  const objectUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = file.filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}
