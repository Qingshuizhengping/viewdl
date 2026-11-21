import httpx
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile", "Referer": "https://www.xiaohongshu.com/"}
fid = "1040g34o31m8ag5ful0104a2tptoku0tildgojf8"
tok_u = "http://sns-webpic-qc.xhscdn.com/202611211320/1e1d3e3aa72c78f4629d925086f81f8a/spectrum/1040g34o31m8ag5ful0104a2tptoku0tildgojf8!h5_1080jpg"
variants = {
    "hw_fileid": f"https://sns-img-hw.xhscdn.com/{fid}",
    "hw_stream": f"https://sns-img-hw.xhscdn.com/stream/{fid}",
    "qc_stream": f"https://sns-img-qc.xhscdn.com/stream/{fid}",
    "hw_spectrum": f"https://sns-img-hw.xhscdn.com/spectrum/{fid}",
    "webpicqc_nosign": f"http://sns-webpic-qc.xhscdn.com/spectrum/{fid}!nd_dft_jpg",
    "ci_oss": f"https://ci.xiaohongshu.com/{fid}?x-oss-process=image/format,jpg",
}
ok = []
for tag, u in variants.items():
    try:
        r = httpx.get(u, headers=UA, verify=False, timeout=20, follow_redirects=True)
        open(f"/tmp/v2_{tag}.bin", "wb").write(r.content)
        print(f"{tag}: {r.status_code} {len(r.content)}B")
        if r.status_code == 200 and len(r.content) > 1000:
            ok.append((tag, len(r.content)))
    except Exception as e:
        print(f"{tag}: FAIL {type(e).__name__}")
print("OK:", ok)
