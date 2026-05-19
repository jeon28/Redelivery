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
      const res = await fetch(`${railwayUrl}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      return NextResponse.json(await res.json(), { status: res.status })
    } catch {
      return NextResponse.json(
        { error: 'Railway 서버 연결 실패' },
        { status: 500 }
      )
    }
  }

  // Railway 미연결 시 Mock 응답 (개발용): 입력 그대로 모두 취소 성공 처리
  const items = (body.items ?? []) as { container_no: string; booking_ref: string }[]
  const mockResults = items.map((it) => ({
    container_no: it.container_no,
    booking_ref: it.booking_ref,
    cancelled: true,
    reason: null,
  }))

  return NextResponse.json({ results: mockResults })
}
