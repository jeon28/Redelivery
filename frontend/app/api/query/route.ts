import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

export async function POST(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  if (!session?.userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  const body = await req.json()
  const railwayUrl = process.env.RAILWAY_API_URL

  if (railwayUrl) {
    try {
      const res = await fetch(`${railwayUrl}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      return NextResponse.json(data, { status: res.status })
    } catch {
      return NextResponse.json(
        { error: 'Railway 서버 연결 실패' },
        { status: 500 }
      )
    }
  }

  // Railway 미연결 시 Mock 데이터 반환 (개발용)
  const mockResults = (body.containers as string[]).map((no, i) =>
    i % 2 === 0
      ? {
          container_no: no,
          available: true,
          depot: 'INC05 - SEUNG JIN ENTERPRISES',
          booking_ref: `TKE${Math.random().toString(36).toUpperCase().slice(2, 6)}`,
          over_caps: 'NO',
          close_date: '2026-MAY-31',
          reason: null,
        }
      : {
          container_no: no,
          available: false,
          depot: null,
          booking_ref: null,
          over_caps: null,
          close_date: null,
          reason: 'CONTAINERS NOT HIRED BY SINOK1',
        }
  )

  return NextResponse.json({ results: mockResults })
}
