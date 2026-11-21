#!/bin/bash
set -e
curl -sk -H "Host: coffee.weizhiyu.top" -X POST -H "Content-Type: application/json" \
  -d '{"text":"66 【现代静奢|超凡自在，安闲从容 - 参见PPT大王 | 小红书 - 你的生活兴趣社区】 😆 w8Gyg6CmzlQk11Z 😆 https://www.xiaohongshu.com/discovery/item/68c12ab9000000001d00bc55?source=webshare&xhsshare=pc_web&xsec_token=CBPL3hGaSIGMs2nygQS308VnXEi2U3Go8AMgUuHKisUaQ=&xsec_source=pc_share"}' \
  https://127.0.0.1/vdl/api/parse -o /tmp/xhs2.json -w "parse: %{http_code}\n"
python3 <<'PYEOF'
import json
d = json.load(open("/tmp/xhs2.json"))
print("images:", len(d.get("items", [])), "| detail:", str(d.get("detail"))[:80])
for it in d.get("items", [])[:3]:
    print("  -", it["label"], "->", it["url"][:90])
PYEOF
ITEM=$(python3 -c 'import json;print(json.dumps(json.load(open("/tmp/xhs2.json"))["items"][0]))')
curl -sk -H "Host: coffee.weizhiyu.top" -X POST -H "Content-Type: application/json" \
  -d "{\"platform\":\"xiaohongshu\",\"title\":\"watermark-fix-check\",\"raw_url\":\"x\",\"items\":[$ITEM]}" \
  https://127.0.0.1/vdl/api/download > /dev/null
sleep 3
curl -sk -H "Host: coffee.weizhiyu.top" https://127.0.0.1/vdl/api/jobs | python3 -c 'import json,sys;j=json.load(sys.stdin)["jobs"][0];print("job:",j["status"],"|",j["file"],"| err:",(j["error"] or "")[:60])'
ls -la /opt/viewdl/downloads/ | tail -2
