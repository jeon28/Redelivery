import { NextRequest } from 'next/server'
import { proxyToScraper } from '@/lib/scraperProxy'

export async function GET(req: NextRequest) {
  const container = req.nextUrl.searchParams.get('container') ?? ''
  return proxyToScraper(req, `/lookup?container=${encodeURIComponent(container)}`)
}
