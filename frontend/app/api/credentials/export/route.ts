import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

async function authed(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  if (!session?.userId) return false

  const unlock = req.cookies.get('credentials_unlock')?.value
  const unlockPayload = await decrypt(unlock)
  return !!unlockPayload?.unlocked
}

function scraperUrl() {
  const url = process.env.RAILWAY_API_URL
  if (!url) throw new Error('RAILWAY_API_URL 미설정')
  return url
}

function apiKey() {
  return process.env.SCRAPER_API_KEY ?? ''
}

// 임대사 베이스 코드 → 공식 홈페이지 URL.
// SearchForm.tsx 의 LESSOR_HOMEPAGES 와 동일. 현재 시스템 관리 대상은
// query 임대사 5개뿐이라 inline 정의 유지.
const HOMEPAGE: Record<string, string> = {
  TEXA: 'https://www.textainer.com/contact',
  TRIT: 'https://www.tritoncontainer.com/tritoncontainer/',
  GOLD: 'http://www.touax-container.com/?option=com_indexinfo',
  FLOR: 'http://www.florens.com/',
  GESE: 'https://seaweb.seacoglobal.com/',
}

function csvField(v: string): string {
  // RFC 4180: , " \r \n 중 하나라도 포함되면 " 로 감싸고 내부 " 는 "" 로 이스케이프.
  if (/[",\r\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`
  return v
}

type Cred = { id: string; pw: string }
type Creds = Record<string, Record<string, Cred>>
type Companies = Record<string, { prefix: string; lessors: string[] }>

export async function GET(req: NextRequest) {
  if (!(await authed(req)))
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })

  let payload: { companies: Companies; credentials: Creds }
  try {
    const res = await fetch(`${scraperUrl()}/credentials`, {
      headers: { 'X-API-Key': apiKey() },
      cache: 'no-store',
    })
    if (!res.ok) {
      return NextResponse.json(
        { error: `스크래퍼 응답 오류: ${res.status}` },
        { status: 502 }
      )
    }
    payload = await res.json()
  } catch {
    return NextResponse.json(
      { error: '스크래퍼 서버 연결 실패' },
      { status: 502 }
    )
  }

  const header = ['선사', '임대사', '아이디', '비밀번호', '홈페이지']
  const rows: string[][] = [header]
  for (const [company, cfg] of Object.entries(payload.companies ?? {})) {
    for (const lessor of cfg.lessors) {
      const c = payload.credentials?.[company]?.[lessor] ?? { id: '', pw: '' }
      rows.push([company, lessor, c.id, c.pw, HOMEPAGE[lessor] ?? ''])
    }
  }

  // Excel 한글 깨짐 방지용 UTF-8 BOM + RFC 4180 CRLF 라인 종료
  const body = '﻿' + rows.map((r) => r.map(csvField).join(',')).join('\r\n')

  const today = new Date().toISOString().slice(0, 10)
  return new NextResponse(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="credentials_${today}.csv"`,
      'Cache-Control': 'no-store',
    },
  })
}
