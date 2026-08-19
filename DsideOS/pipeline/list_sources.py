import json, sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
data = json.loads(Path("clients/target-academy/review/input/live-14jun-paper.json").read_text(encoding="utf-8"))
for q in data["questions"]:
    sol = bool(q.get("solution"))
    srcs = q.get("sources", [])
    flag = bool(q.get("flag"))
    if sol:
        marker = "SELF-VERIFY"
    elif flag:
        marker = "FLAGGED"
    else:
        marker = "srcs=" + ",".join(srcs[:3])
    print(f"Q{q['n']:3d} ({q['answer']}) {marker}")
