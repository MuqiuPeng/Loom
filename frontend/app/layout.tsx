import type { Metadata } from 'next'
import './globals.css'
import { LanguageProvider } from './i18n'

export const metadata: Metadata = {
  title: 'Loom - Profile Builder',
  description: 'AI-powered career profile builder through conversation',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 min-h-screen">
        <LanguageProvider>
          {children}
        </LanguageProvider>
      </body>
    </html>
  )
}
