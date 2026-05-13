import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '반납컨테이너 조회 시스템',
  description: '장금상선 · 흥아라인 컨테이너 반납 가능 여부 조회',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={geist.className}>
      <body className="min-h-screen bg-gray-50">{children}</body>
    </html>
  )
}
