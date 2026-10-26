import { NextRequest } from 'next/server'
import { proxyToScraper } from '@/lib/scraperProxy'

export async function GET(req: NextRequest) {
  return proxyToScraper(req, '/lease-inventory/summary')
}

// 반납 대장 엑셀 원본 바이트를 그대로 전달 (파싱은 백엔드 openpyxl)
export async function POST(req: NextRequest) {
  return proxyToScraper(req, '/lease-inventory', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Filename': req.headers.get('x-filename') ?? '',
    },
    body: await req.arrayBuffer(),
  })
}
