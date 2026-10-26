"""lessor_lookup 단위 테스트. 실행: python test_lessor_lookup.py [반납대장.xlsx]"""
import os
import sys
import tempfile

tmp = tempfile.mkdtemp()
os.environ["LEASE_INVENTORY_FILE"] = os.path.join(tmp, "inv.json")
os.environ["PREFIX_MAP_FILE"] = os.path.join(tmp, "prefix.json")

from config import lessor_lookup as ll  # noqa: E402

# 체크디짓: 실제 발급 이력이 있는 번호들
for cn in ["DFSU7487867", "TEMU0913089", "FCIU4708298", "BEAU2055648", "WBPU7074740", "TCNU4318593", "CSQU3054383"]:
    assert ll.check_digit_ok(cn), cn
assert not ll.check_digit_ok("DFSU7487868")
assert not ll.check_digit_ok("DFSU748786")

# 접두어 판별 (대장 없음)
r = ll.lookup("dfsu7487867")
assert r["lessor"] == "FLOR" and r["source"] == "prefix", r
assert ll.lookup("HALU2051800")["lessor"] == "MWSC"
assert ll.lookup("ZZZU1234567")["lessor"] is None
assert ll.normalize_lessor("TEXT") == "TEXA" and ll.normalize_lessor("INC08") is None

# 접두어 표 저장 → 반영
ll.save_prefix_map({"zzzu": "glod", "BAD!": "TEXA"})
assert ll.get_prefix_map() == {"ZZZU": "GOLD"}
os.remove(os.environ["PREFIX_MAP_FILE"])

if len(sys.argv) > 1:
    parsed = ll.parse_inventory_xlsx(open(sys.argv[1], "rb").read())
    s = ll.save_inventory(parsed, "test.xlsx")
    print("count", s["count"], "sheets", len(s["sheets"]))
    print("by_lessor", s["by_lessor"])
    r = ll.lookup("BEAU2055648")
    assert r["source"] == "inventory" and r["lessor"] == "BCON" and r["line"] == "HA", r
    print("BEAU candidates", r["candidates"])
    r = ll.lookup("FSCU8197554")
    assert r["line"] == "SK" and r["type"] == "45GP", r
    print("HALU5695494", ll.lookup("HALU5695494"))
print("OK")
