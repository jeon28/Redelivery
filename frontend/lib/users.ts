import 'server-only'

export type Office = '인천' | '부산' | '평택' | '광양' | '울산' | '본사'

type UserDef = {
  office: Office
  pwEnv: string
  pinEnv: string
}

// 사무소별 로그인 계정.
// 신규 사무소 추가 시 이 맵에 한 줄 + 환경변수(PW/PIN) 두 개 추가하면 끝.
export const USERS: Record<string, UserDef> = {
  skrinc: { office: '인천', pwEnv: 'SKRINC_PW', pinEnv: 'ADMIN_PIN_INC' },
  skrpus: { office: '부산', pwEnv: 'SKRPUS_PW', pinEnv: 'ADMIN_PIN_PUS' },
}

/**
 * username/password 조합이 USERS 맵에 매칭되면 office를 반환.
 * 매칭 실패 시 null.
 *
 * 레거시 환경변수(APP_USER_ID/APP_USER_PW) fallback도 유지.
 * 이때 office는 '인천'으로 처리한다 (기존 사용자는 인천 소속이었음).
 */
export function authenticate(
  username: string,
  password: string,
): Office | null {
  const user = USERS[username]
  if (user) {
    const expected = process.env[user.pwEnv]
    if (expected && password === expected) return user.office
  }
  // 레거시 fallback (배포 후 1주 이내 제거 예정)
  const legacyId = process.env.APP_USER_ID
  const legacyPw = process.env.APP_USER_PW
  if (legacyId && legacyPw && username === legacyId && password === legacyPw) {
    return '인천'
  }
  return null
}

/**
 * 해당 사무소의 자격증명 페이지 PIN을 환경변수에서 가져온다.
 * 매핑이 없으면 레거시 ADMIN_PIN으로 폴백.
 */
export function pinForOffice(office: Office): string | undefined {
  for (const user of Object.values(USERS)) {
    if (user.office === office) {
      const v = process.env[user.pinEnv]
      if (v) return v
    }
  }
  return process.env.ADMIN_PIN
}
