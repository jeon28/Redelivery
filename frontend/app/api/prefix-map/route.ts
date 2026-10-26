import { NextRequest } from 'next/server'
import { proxyToScraper } from '@/lib/scraperProxy'

export async function GET(req: NextRequest) {
  return proxyToScraper(req, '/prefix-map')
}

export async function PUT(req: NextRequest) {
  return proxyToScraper(req, '/prefix-map', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(await req.json()),
  })
}
