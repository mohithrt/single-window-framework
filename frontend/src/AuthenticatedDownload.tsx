import { useState, type MouseEvent, type ReactNode } from 'react'

export default function AuthenticatedDownload({ href, fileName, children }: {
  href: string
  fileName: string
  children: ReactNode
}) {
  const [error, setError] = useState('')

  async function download(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    setError('')
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) {
      window.location.assign('/login')
      return
    }
    try {
      const response = await fetch(href, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('Could not download this inspection photo.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not download this file.')
    }
  }

  return <span className="authenticated-download"><a href={href} onClick={(event) => void download(event)}>{children}</a>{error && <small role="alert">{error}</small>}</span>
}
