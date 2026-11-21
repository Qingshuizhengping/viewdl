# -*- coding: utf-8 -*-
"""
ViewDL — 全网视图解析下载（本地 Web App）

架构：
  FastAPI 后端
  ├─ yt-dlp 引擎：B站 / YouTube / TikTok / X(Twitter) / Instagram / Facebook 等 1000+ 站点
  └─ 专用解析器：抖音 / 快手 / 小红书(含实况图 Live Photo 视频轨) / 微博 / 微信公众号图文
交互流程参考：abLive(App Store id6739402998) 与 hellotik.app —— 粘贴链接 → 解析 → 选择文件与清晰度 → 保存
"""
import asyncio
import html as ihtml
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = BASE_DIR / "static"

PORT = int(os.environ.get("VIEWDL_PORT", "8770"))

UA_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
UA_ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

PLATFORM_LABELS = {
    "douyin": "抖音", "kuaishou": "快手", "xiaohongshu": "小红书", "weibo": "微博",
    "bilibili": "哔哩哔哩", "wechat_mp": "微信公众号", "youtube": "YouTube",
    "tiktok": "TikTok", "twitter": "X (Twitter)", "instagram": "Instagram",
    "facebook": "Facebook", "generic": "其他站点",
}
PLAT_NAME_FOR_FILE = {
    "douyin": "douyin", "kuaishou": "kuaishou", "xiaohongshu": "xhs", "weibo": "weibo",
    "bilibili": "bilibili", "wechat_mp": "wxmp", "youtube": "youtube", "tiktok": "tiktok",
    "twitter": "twitter", "instagram": "ins", "facebook": "facebook", "generic": "web",
}
DL_HEADERS = {
    "douyin": {"Referer": "https://www.douyin.com/"},
    "kuaishou": {"Referer": "https://www.kuaishou.com/"},
    "xiaohongshu": {"Referer": "https://www.xiaohongshu.com/"},
    "weibo": {"Referer": "https://weibo.com/"},
    "wechat_mp": {"Referer": "https://mp.weixin.qq.com/"},
    "bilibili": {"Referer": "https://www.bilibili.com/"},
    "twitter": {"Referer": "https://x.com/"},
    "tiktok": {"Referer": "https://www.tiktok.com/"},
    "instagram": {"Referer": "https://www.instagram.com/"},
    "youtube": {"Referer": "https://www.youtube.com/"},
}

URL_STOP = "，。；！？、）】》\"'”’,;!?)]}>"


class ParseError(Exception):
    pass


# 字符类内的 ] 必须转义；此类用于在口令文本中截停 URL
# 注意：? 与 = 必须允许出现在 URL 内（query/xsec_token 等），故排除类不含它们
_URL_BODY = r'[^\s<>"\'，。；！？、）】》\]\[,;)}]+'


def extract_url(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    m = re.search(r"https?://" + _URL_BODY, text, re.I)
    if m:
        return m.group(0).rstrip(".,;)]}")
    m = re.search(r"(?:www\.)?[a-z0-9\-]+\.(?:com|cn|net|tv|be|co|io|app|xyz|vip|link|top)/" + _URL_BODY,
                  text, re.I)
    if m:
        return "https://" + m.group(0).rstrip(".,;)]}")
    return None


def detect_platform(url: str) -> str:
    u = (url or "").lower()
    if "douyin.com" in u or "iesdouyin" in u:
        return "douyin"
    if "kuaishou" in u or "chenzhongtech" in u:
        return "kuaishou"
    if "xiaohongshu" in u or "xhslink" in u or "rednote.com" in u:
        return "xiaohongshu"
    if "weibo.com" in u or "weibo.cn" in u or "t.cn" in u:
        return "weibo"
    if "bilibili.com" in u or "b23.tv" in u:
        return "bilibili"
    if "mp.weixin.qq.com" in u:
        return "wechat_mp"
    if "tiktok.com" in u:
        return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "twitter.com" in u or re.search(r"//x\.com", u):
        return "twitter"
    if "instagram.com" in u:
        return "instagram"
    if "facebook.com" in u or "fb.watch" in u:
        return "facebook"
    return "generic"


def _raw_json_after(text: str, marker: str):
    """从 text 中 marker 之后第一个 '{' 开始做 JSON 前缀解析（对嵌套/收尾杂讯鲁棒）"""
    i = text.find(marker)
    if i < 0:
        return None
    j = text.find("{", i)
    if j < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[j:])
        return obj
    except Exception:
        return None


def _sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:60]


def _unique_name(platform: str, title: str, label: str, ext: str) -> str:
    base = f"{PLAT_NAME_FOR_FILE.get(platform, platform)}_{_sanitize(title) or 'media'}"
    if label:
        base += f"_{_sanitize(label)[:30]}"
    base = base.strip(" ._")
    name = f"{base}.{ext}"
    if (DOWNLOAD_DIR / name).exists():
        name = f"{base}_{int(time.time())}.{ext}"
    return name


def _mk_item(kind: str, label: str, url: Optional[str] = None, format_id: Optional[str] = None,
             ext: str = "mp4", quality: Optional[int] = None, size: Optional[int] = None) -> dict:
    return {"id": f"{kind}_{uuid.uuid4().hex[:8]}", "kind": kind, "label": label,
            "url": url, "format_id": format_id, "ext": ext, "quality": quality, "size": size}


def _pick_url(obj) -> Optional[str]:
    """抖音系 JSON 中 {url_list:[...]} 的取址"""
    if isinstance(obj, dict):
        lst = obj.get("url_list") or []
        if lst:
            return lst[-1] if "playwm" not in str(lst[0]) and len(lst) > 1 else lst[0]
    return None


async def expand(client: httpx.AsyncClient, url: str, ua: str = UA_IPHONE) -> str:
    try:
        r = await client.get(url, headers={"User-Agent": ua}, follow_redirects=True, timeout=15)
        return str(r.url)
    except Exception:
        return url


# ---------------------------------------------------------------- 抖音

def _find_douyin_item(data) -> Optional[dict]:
    found = {"item": None}

    def walk(o):
        if found["item"]:
            return
        if isinstance(o, dict):
            il = o.get("item_list")
            if isinstance(il, list) and il and isinstance(il[0], dict):
                found["item"] = il[0]
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return found["item"]


async def resolve_douyin(client: httpx.AsyncClient, url: str) -> dict:
    if "v.douyin.com" in url:
        url = await expand(client, url, UA_IPHONE)
    m = re.search(r"/(?:video|note|slides)/(\d+)", url)
    if not m:
        raise ParseError("未从链接中识别出抖音作品 ID，请用 App「分享-复制链接」得到的完整口令")
    wid = m.group(1)
    item, last_err = None, ""
    for path in ("video", "note", "slides"):
        try:
            r = await client.get(
                f"https://www.iesdouyin.com/share/{path}/{wid}/",
                headers={"User-Agent": UA_IPHONE, "Referer": "https://www.douyin.com/"},
                follow_redirects=True)
            data = _raw_json_after(r.text, "_ROUTER_DATA")
            if data:
                item = _find_douyin_item(data)
        except Exception as e:
            last_err = str(e)
        if item:
            break
    if not item:
        raise ParseError(f"抖音页面解析失败（{last_err or '页面结构变化或作品受限'}），请稍后重试")

    title = item.get("desc") or item.get("preview_title") or "抖音作品"
    author = (item.get("author") or {}).get("nickname", "")
    vid = item.get("video") or {}
    cover = _pick_url(vid.get("cover")) or _pick_url(vid.get("origin_cover"))

    items, seen = [], set()
    for br in vid.get("bit_rate") or []:
        pa = br.get("play_addr") or {}
        urls = pa.get("url_list") or []
        h = pa.get("height") or 0
        if not urls or h in seen:
            continue
        seen.add(h)
        u = urls[0]
        # aw.snssdk.com 域在部分网络环境（代理/TUN）下 TLS 握手被掐，统一走 www.douyin.com 域
        if "aw.snssdk.com" in u:
            u = u.replace("https://aw.snssdk.com", "https://www.douyin.com", 1)
        items.append(_mk_item("video", f"{h}P 视频（无水印）", url=u, ext="mp4", quality=h))
    items.sort(key=lambda x: x.get("quality") or 0, reverse=True)

    if not items and vid.get("play_addr", {}).get("uri"):
        uri = vid["play_addr"]["uri"]
        for ratio in (1080, 720, 540):
            items.append(_mk_item("video", f"{ratio}P 视频（无水印）",
                                  url=f"https://www.douyin.com/aweme/v1/play/?video_id={uri}&ratio={ratio}p&line=0",
                                  ext="mp4", quality=ratio))

    images = item.get("images") or []
    for i, img in enumerate(images):
        ul = img.get("url_list") or []
        if ul:
            items.append(_mk_item("image", f"图片 {i + 1}", url=ul[-1], ext="jpg"))

    music = ((item.get("music") or {}).get("play_url") or {}).get("url_list") or []
    if music:
        items.append(_mk_item("audio", "背景音乐", url=music[0], ext="mp3"))

    if not items:
        raise ParseError("该作品未返回可下载的媒体地址")
    note = "图集作品" if images else ""
    return {"platform": "douyin", "title": title[:60], "author": author, "cover": cover,
            "engine": "direct", "items": items, "note": note}


# ---------------------------------------------------------------- 快手

async def resolve_kuaishou(client: httpx.AsyncClient, url: str) -> dict:
    if re.search(r"v\.kuaishou\.com|/fw/", url):
        url = await expand(client, url, UA_IPHONE)
    m = re.search(r"(?:short-video/|photo/|fw/photo/)([0-9A-Za-z_-]+)", url)
    if not m:
        raise ParseError("未从链接中识别出快手作品 ID，请用 App 分享的链接")
    pid = m.group(1)
    r = await client.get(
        f"https://www.kuaishou.com/short-video/{pid}",
        headers={"User-Agent": UA_PC, "Referer": "https://www.kuaishou.com/",
                 "Cookie": f"did=web_{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))}; kpn=KUAISHOU_VISION; kpf=PC_WEB"},
        follow_redirects=True)
    st = _raw_json_after(r.text, "__APOLLO_STATE__")
    if not st:
        raise ParseError("快手页面数据缺失，请稍后重试")

    photo, author, cover = None, None, None

    def walk(o):
        nonlocal photo, author
        if isinstance(o, dict):
            if photo is None and (o.get("photoUrl") or o.get("manifest")):
                photo = o
            if author is None and o.get("name") and o.get("headUrl"):
                author = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(st)
    if not photo:
        raise ParseError("快手解析失败：未找到作品数据（作品可能受限）")

    title = photo.get("caption") or "快手作品"
    items, seen = [], set()
    reps = []
    for st_ in (photo.get("manifest") or {}).get("adaptationSet") or []:
        reps.extend(st_.get("representation") or [])
    reps.sort(key=lambda x: x.get("height") or 0, reverse=True)
    for rep in reps:
        u, h = rep.get("url"), rep.get("height")
        if not u or h in seen:
            continue
        seen.add(h)
        lab = rep.get("qualityLabel") or (f"{h}P" if h else "视频")
        items.append(_mk_item("video", f"{lab} 视频", url=u, ext="mp4", quality=h))
    if not items and photo.get("photoUrl"):
        items.append(_mk_item("video", "原画质视频", url=photo["photoUrl"], ext="mp4"))
    if not items:
        raise ParseError("该作品未返回可下载的视频地址")
    if not cover:
        cover = photo.get("coverUrl") or photo.get("thumbnailUrl")
    return {"platform": "kuaishou", "title": title[:60], "author": (author or {}).get("name", ""),
            "cover": cover, "engine": "direct", "items": items, "note": ""}


# ---------------------------------------------------------------- 小红书

def _g(obj: dict, *names):
    """多键名取值（兼容 snake_case / camelCase 双结构）"""
    for n in names:
        if isinstance(obj, dict) and obj.get(n) is not None:
            return obj[n]
    return None


def _collect_stream_entries(obj, out: list):
    """全树收集视频流条目（含 master_url/masterUrl + 尺寸字段的 dict）"""
    if isinstance(obj, dict):
        mu = obj.get("master_url") or obj.get("masterUrl") or obj.get("url")
        if mu and isinstance(mu, str) and mu.startswith("http") and (obj.get("height") or obj.get("fps")):
            out.append(obj)
            return
        for v in obj.values():
            _collect_stream_entries(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_stream_entries(v, out)


_XHS_JAR = httpx.Cookies()  # 跨请求保留小红书风控 Cookie（acw_tc/webId 等），降低重复解析被风控的概率


def _find_note_by_id(obj, nid: str) -> Optional[dict]:
    """在状态树任意位置找 noteId/note_id 匹配且带媒体字段的笔记对象（兼容页面结构变体）"""
    found = {"n": None}

    def walk(x):
        if found["n"] or not isinstance(x, dict):
            return
        if (x.get("noteId") == nid or x.get("note_id") == nid) and \
                (x.get("imageList") or x.get("image_list") or x.get("video")):
            found["n"] = x
            return
        for v in x.values():
            walk(v)

    walk(obj)
    return found["n"]


async def resolve_xhs(client: httpx.AsyncClient, url: str) -> dict:
    if "xhslink" in url:
        url = await expand(client, url, UA_IPHONE)
    m = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]{24})", url)
    if not m:
        raise ParseError("未从链接中识别出小红书笔记 ID，请从 App「分享-复制链接」复制完整内容")
    nid = m.group(1)
    headers = {"User-Agent": UA_ANDROID,
               "Accept": "text/html,application/xhtml+xml",
               "Referer": "https://www.xiaohongshu.com/"}
    note = None
    for attempt in range(2):
        r = await client.get(url, headers=headers, follow_redirects=True, cookies=_XHS_JAR)
        try:
            _XHS_JAR.update(r.cookies)
        except Exception:
            pass
        i = r.text.find("__INITIAL_STATE__")
        if i < 0:
            raise ParseError("小红书页面数据缺失：请使用 App 分享的原始链接（含 xsec_token 参数）")
        j = r.text.find("{", i)
        seg = re.sub(r"\bundefined\b", "null", r.text[j:j + 2_000_000])
        try:
            data, _ = json.JSONDecoder().raw_decode(seg)
        except Exception:
            raise ParseError("小红书数据解析失败，请重试")

        # 双结构 + 任意变体：国内 noteDetailMap / 国际 rednote noteData.data.noteData / 其余位置全树扫描
        for v in ((data.get("note") or {}).get("noteDetailMap") or {}).values():
            if isinstance(v, dict) and v.get("note"):
                note = v["note"]
                break
        if not note:
            note = _find_note_by_id(data, nid)
        if note:
            break
        if attempt == 0:
            await asyncio.sleep(1.5)  # 风控变体页面通常一次重试即可恢复
    if not note or not isinstance(note, dict):
        fin = str(r.url)
        nd = (data.get("noteData") or {})
        diag = (f"final={fin[:90]} len={len(r.text)} "
                f"noteData.data.noteData={'有' if isinstance(nd.get('data'), dict) and isinstance(nd['data'].get('noteData'), dict) else '无'} "
                f"hasError={nd.get('hasError')}")
        raise ParseError(f"笔记内容为空：作品可能已删除、受限，或需要登录后可见（可稍后重试）[{diag}]")

    title = _g(note, "title") or (_g(note, "desc") or "")[:40] or "小红书笔记"
    author = (_g(note, "user") or {}).get("nickname") or (_g(note, "user") or {}).get("nickName") or ""
    items, seen = [], set()

    # 原画无水印：originVideoKey（原视频 key 直拼 CDN，无水印；页面播放流是带水印转码）
    ovk = {"v": None}

    def _find_ovk(o):
        if ovk["v"]:
            return
        if isinstance(o, dict):
            for k in ("originVideoKey", "origin_video_key"):
                v = o.get(k)
                if isinstance(v, str) and 20 < len(v) < 200:
                    ovk["v"] = v
                    return
            for v in o.values():
                _find_ovk(v)
        elif isinstance(o, list):
            for v in o:
                _find_ovk(v)

    _find_ovk(note)
    if ovk["v"]:
        for host in ("sns-video-hw.xhscdn.com", "sns-video.xhscdn.com"):
            items.append(_mk_item("video", "原画视频（无水印）",
                                  url=f"https://{host}/stream/{ovk['v']}", ext="mp4", quality=9999))
        seen.add((None, "origin"))

    # 视频笔记：兼容 video.media.stream 与任意嵌套的视频流（转码，可能带水印）
    streams: list = []
    _collect_stream_entries(_g(note, "video") or {}, streams)
    streams.sort(key=lambda s: s.get("height") or 0, reverse=True)
    for s in streams:
        key = (s.get("width"), s.get("height"))
        u = s.get("master_url") or s.get("masterUrl") or ((s.get("backup_urls") or s.get("backupUrls") or [None])[0])
        if not u or key in seen:
            continue
        seen.add(key)
        h = s.get("height")
        lab = f"{h}P 转码（可能带水印）" + (" 高码率" if s.get("video_quality") in ("hq",) else "")
        items.append(_mk_item("video", lab, url=u, ext="mp4", quality=h))

    # 图片（含实况图视频轨）
    img_list = _g(note, "image_list") or _g(note, "imageList") or []
    cover = None
    if img_list:
        im0 = img_list[0]
        cover = (_g(im0, "url_default", "url")
                 or ((im0.get("info_list") or im0.get("infoList") or [{}])[-1].get("image_url")
                     or (im0.get("info_list") or im0.get("infoList") or [{}])[-1].get("url")))
    for i2, im in enumerate(img_list):
        u = (_g(im, "url_default", "url")
             or (((im.get("info_list") or im.get("infoList") or [{}])[-1].get("image_url"))
                 or ((im.get("info_list") or im.get("infoList") or [{}])[-1].get("url"))))
        if u:
            items.append(_mk_item("image", f"图片 {i2 + 1}", url=u, ext="jpg"))
        lp = _g(im, "live_photo_path", "livePhotoPath")
        if lp:
            items.append(_mk_item("video", f"实况视频 {i2 + 1}（Live Photo 视频轨）", url=lp, ext="mov"))
        elif im.get("live_photo") or im.get("livePhoto"):
            live_streams: list = []
            _collect_stream_entries(im.get("stream") or {}, live_streams)
            for s in live_streams:
                lu = s.get("master_url") or s.get("masterUrl")
                if lu:
                    items.append(_mk_item("video", f"实况视频 {i2 + 1}（Live Photo 视频轨）", url=lu, ext="mov"))

    if not items:
        raise ParseError("该笔记未检测到可下载的媒体")
    has_live = any(_g(im, "live_photo", "livePhoto") for im in img_list)
    return {"platform": "xiaohongshu", "title": str(title)[:60], "author": author, "cover": cover,
            "engine": "direct", "items": items,
            "note": "含实况图（照片 + 视频轨）" if has_live else ""}


# ---------------------------------------------------------------- 微博

async def resolve_weibo(client: httpx.AsyncClient, url: str) -> dict:
    if "t.cn" in url:
        url = await expand(client, url, UA_IPHONE)
    m = (re.search(r"/status(?:es)?/(\w+)", url)
         or re.search(r"weibo\.com/(?:u/\d+/)?([0-9A-Za-z]+)", url)
         or re.search(r"m\.weibo\.cn/status/(\w+)", url))
    if not m:
        raise ParseError("未从链接中识别出微博 ID，请复制微博正文链接")
    sid = m.group(1)
    numeric = sid if sid.isdigit() else None
    if not numeric:
        r = await client.get(f"https://m.weibo.cn/status/{sid}",
                             headers={"User-Agent": UA_IPHONE, "Referer": "https://m.weibo.cn/"},
                             follow_redirects=True)
        mm = re.search(r'"id":\s*"?(\d{15,})', r.text) or re.search(r"/status/(\d{15,})", r.text)
        numeric = mm and mm.group(1)
    if not numeric:
        raise ParseError("未能换算微博数字 ID，请复制完整微博链接重试")
    r = await client.get("https://m.weibo.cn/statuses/show", params={"id": numeric},
                         headers={"User-Agent": UA_IPHONE, "Referer": "https://m.weibo.cn/",
                                  "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    try:
        j = r.json()
    except Exception:
        raise ParseError("微博接口返回异常，请稍后重试")
    data = j.get("data") or {}
    if not data:
        raise ParseError("微博不存在、已删除或需要登录可见")

    text = data.get("text_raw") or data.get("text") or ""
    title = ihtml.unescape(re.sub(r"<[^>]+>", "", text)).strip()[:50] or "微博内容"
    author = (data.get("user") or {}).get("screen_name", "")
    items, seen = [], set()

    pi = data.get("page_info") or {}
    mi = pi.get("media_info") or {}
    if (pi.get("type") or "") == "video" or mi:
        for e in mi.get("playback_list") or []:
            pb = (e.get("playback_info") or {}) if isinstance(e, dict) else {}
            u, h = pb.get("url"), pb.get("height")
            lab = pb.get("label_text") or pb.get("quality_label") or (f"{h}P" if h else "视频")
            if u and (h, lab) not in seen:
                seen.add((h, lab))
                items.append(_mk_item("video", f"{lab} 视频", url=u, ext="mp4", quality=h))
        if not items:
            for k, lab in (("stream_url_hd", "高清视频"), ("stream_url", "标清视频"),
                           ("mp4_hd_url", "高清视频"), ("mp4_sd_url", "标清视频")):
                u = mi.get(k)
                if u:
                    items.append(_mk_item("video", lab, url=u, ext="mp4"))
                    break

    imgs = []
    for pid, info in (data.get("pic_infos") or {}).items():
        best = None
        for key in ("original", "largest", "large", "middle"):
            u = ((info or {}).get(key) or {}).get("url")
            if u:
                best = u
                break
        if best:
            imgs.append(best)
    if not imgs:
        for p in data.get("pics") or []:
            u = p.get("large", {}).get("url") or p.get("url")
            if u:
                imgs.append(u)
    for i, u in enumerate(imgs):
        u = u.replace("/thumb150/", "/large/").replace("/orj360/", "/large/")
        items.append(_mk_item("image", f"图片 {i + 1}", url=u, ext="jpg"))

    if not items:
        raise ParseError("该微博未检测到可下载的图片或视频")
    cover = imgs[0] if imgs else None
    return {"platform": "weibo", "title": title, "author": author, "cover": cover,
            "engine": "direct", "items": items, "note": ""}


# ---------------------------------------------------------------- 微信公众号图文

async def resolve_wechat_mp(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, headers={"User-Agent": UA_PC}, follow_redirects=True)
    t = r.text
    imgs, seen = [], set()
    for u in (re.findall(r'data-src="(https?://mmbiz\.qpic\.cn/[^"]+?)"', t)
              + re.findall(r'src="(https?://mmbiz\.qpic\.cn/[^"]+?)"', t)):
        u = ihtml.unescape(u)
        if u in seen or "wx_fmt=svg" in u:
            continue
        seen.add(u)
        imgs.append(u)
    mt = (re.search(r"var msg_title\s*=\s*'([^']*)'", t)
          or re.search(r'var msg_title\s*=\s*"([^"]*)"', t)
          or re.search(r"<h1[^>]*>([^<]+)</h1>", t))
    title = (mt.group(1).strip() if mt else "公众号图文")[:60]
    if not imgs:
        raise ParseError("该文章未检测到图片（公众号内嵌视频暂不支持，图文图片正常可用）")
    items = []
    for i, u in enumerate(imgs):
        fmt = re.search(r"wx_fmt=(\w+)", u)
        ext = {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}.get(
            fmt.group(1).lower() if fmt else "jpeg", "jpg")
        items.append(_mk_item("image", f"图片 {i + 1}", url=u, ext=ext))
    return {"platform": "wechat_mp", "title": title, "author": "", "cover": imgs[0],
            "engine": "direct", "items": items, "note": "公众号内嵌视频暂未支持"}


# ---------------------------------------------------------------- yt-dlp 通用引擎

def _find_ffmpeg() -> Optional[str]:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _cookiefile() -> Optional[str]:
    p = BASE_DIR / "cookies.txt"
    return str(p) if p.exists() else None


def _ytdlp_single_items(info: dict) -> list:
    items = [_mk_item("video", "自动最佳画质（合并音视频）", format_id="best", ext="mp4")]
    seen, vids = set(), []
    for f in info.get("formats") or []:
        if not f.get("url"):
            continue
        if (f.get("vcodec") or "none") != "none":
            h = f.get("height") or 0
            key = (h, f.get("ext"))
            if key in seen:
                continue
            seen.add(key)
            vids.append((h, f.get("tbr") or 0, f))
    vids.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for h, _tbr, f in vids[:10]:
        lab = f"{h}P · {f.get('ext', 'mp4')}" if h else f"{f.get('format_note') or f.get('format_id')} · {f.get('ext')}"
        if f.get("fps"):
            lab += f" {int(f['fps'])}fps"
        size = f.get("filesize") or f.get("filesize_approx")
        items.append(_mk_item("video", lab, format_id=str(f.get("format_id")),
                              ext=f.get("ext") or "mp4", quality=h or None, size=size))
    auds = [f for f in info.get("formats") or []
            if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") == "none"]
    auds.sort(key=lambda f: f.get("abr") or 0, reverse=True)
    for f in auds[:2]:
        items.append(_mk_item("audio", f"仅音频 {int(f.get('abr') or 0)}kbps · {f.get('ext')}",
                              format_id=str(f.get("format_id")), ext=f.get("ext") or "m4a",
                              size=f.get("filesize") or f.get("filesize_approx")))
    return items


def ytdlp_extract(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": False,
            "socket_timeout": 20, "retries": 2, "nocheckcertificate": True}
    cf = _cookiefile()
    if cf:
        opts["cookiefile"] = cf
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    plat = detect_platform(url)
    cover = info.get("thumbnail")
    author = info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""
    title = info.get("title") or "未命名"

    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        with_fmt = [e for e in entries if e.get("formats")]
        if entries and not with_fmt:  # 图集（如 X / Instagram 多图）
            items = []
            for i, e in enumerate(entries):
                u = e.get("url")
                if not u:
                    continue
                items.append(_mk_item("image", f"文件 {i + 1}", url=u,
                                      ext=e.get("ext") or "jpg"))
            if items:
                return {"platform": plat, "title": title[:60], "author": author, "cover": items[0]["url"],
                        "engine": "direct", "items": items,
                        "note": f"共 {len(items)} 个文件"}
        if with_fmt:  # 多视频列表：解析第一个
            sub = with_fmt[0]
            return {"platform": plat, "title": (sub.get("title") or title)[:60],
                    "author": sub.get("uploader") or author,
                    "cover": sub.get("thumbnail") or cover, "engine": "ytdlp",
                    "url": sub.get("webpage_url") or url,
                    "items": _ytdlp_single_items(sub), "note": "多视频列表已解析第一个"}
        raise ParseError("该链接返回了空列表")

    items = _ytdlp_single_items(info)
    return {"platform": plat, "title": title[:60], "author": author, "cover": cover,
            "engine": "ytdlp", "url": info.get("webpage_url") or url,
            "items": items, "note": ""}


# ---------------------------------------------------------------- 解析路由

RESOLVERS = {
    "douyin": resolve_douyin,
    "kuaishou": resolve_kuaishou,
    "xiaohongshu": resolve_xhs,
    "weibo": resolve_weibo,
    "wechat_mp": resolve_wechat_mp,
}
ROUTING = {
    "douyin": ["douyin", "ytdlp"],
    "kuaishou": ["kuaishou", "ytdlp"],
    "xiaohongshu": ["xiaohongshu", "ytdlp"],
    "weibo": ["weibo"],
    "wechat_mp": ["wechat_mp"],
    "bilibili": ["ytdlp"],
    "youtube": ["ytdlp"],
    "tiktok": ["ytdlp"],
    "twitter": ["ytdlp"],
    "instagram": ["ytdlp"],
    "facebook": ["ytdlp"],
    "generic": ["ytdlp"],
}


# ---------------------------------------------------------------- 下载任务

JOBS: dict = {}
JOBS_LOCK = threading.Lock()
SEM = threading.Semaphore(3)


def _new_job(label: str, platform: str, kind: str) -> dict:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "label": label, "platform": platform, "kind": kind, "status": "pending",
           "progress": 0, "downloaded": 0, "total": 0, "speed": 0, "file": None, "error": None,
           "file_title": "", "file_label": label, "created": time.time()}
    with JOBS_LOCK:
        JOBS[jid] = job
    return job


def _ext_from_url(u: str) -> str:
    m = re.search(r"\.(mp4|mov|m4a|mp3|jpg|jpeg|png|webp|gif|heic)(?:[?#]|$)", u or "", re.I)
    return m.group(1).lower() if m else "bin"


def _curl_fallback(job: dict, url: str, platform: str, ext: str, headers: dict):
    """python TLS 栈被 CDN/代理掐断时的 curl 兜底（Schannel 栈），进度按落盘字节轮询"""
    import subprocess

    curl = shutil.which("curl") or "curl.exe"
    ext = ext if ext and ext != "bin" else _ext_from_url(url)
    fname = _unique_name(platform, job.get("file_title") or "", job.get("file_label") or "", ext)
    tmp = DOWNLOAD_DIR / (fname + ".part")
    cmd = [curl, "-sL", "-f", "--retry", "2", "--connect-timeout", "15",
           "--max-time", "900", "-o", str(tmp), url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while p.poll() is None:
            try:
                job["downloaded"] = tmp.stat().st_size if tmp.exists() else 0
            except Exception:
                pass
            time.sleep(0.7)
        if p.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1024:
            with open(tmp, "rb") as f:
                head = f.read(2)
            if head.startswith(b"<"):
                tmp.unlink(missing_ok=True)
                job["status"] = "error"
                job["error"] = "直链已失效，请重新解析后再下载"
                return
            tmp.rename(DOWNLOAD_DIR / fname)
            sz = (DOWNLOAD_DIR / fname).stat().st_size
            job["file"] = fname
            job["total"] = job["downloaded"] = sz
            job["progress"] = 100
            job["status"] = "done"
            return
        job["status"] = "error"
        job["error"] = f"下载失败（curl 兜底退出码 {p.returncode}）"
    except Exception as e:
        job["status"] = "error"
        job["error"] = f"下载失败（curl 兜底异常 {e}）"


def _direct_worker(job: dict, url: str, platform: str, ext: str):
    headers = {"User-Agent": UA_PC}
    headers.update(DL_HEADERS.get(platform, {}))
    try:
        with SEM:
            job["status"] = "downloading"
            with httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                              verify=False) as cl:
                with cl.stream("GET", url, headers=headers) as resp:
                    if resp.status_code >= 400:
                        raise RuntimeError(f"HTTP {resp.status_code}")
                    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip()
                    if "text/html" in ctype:
                        raise RuntimeError("直链已失效，请重新解析后再下载")
                    if not ext or ext == "bin":
                        extmap = {"video/mp4": "mp4", "image/jpeg": "jpg", "image/png": "png",
                                  "image/webp": "webp", "image/gif": "gif", "audio/mp4": "m4a",
                                  "audio/mpeg": "mp3", "video/quicktime": "mov"}
                        ext = extmap.get(ctype, _ext_from_url(url))
                    job["total"] = int(resp.headers.get("content-length") or 0)
                    fname = _unique_name(platform, job.get("file_title") or "",
                                         job.get("file_label") or "", ext)
                    tmp = DOWNLOAD_DIR / (fname + ".part")
                    last_t, last_b = time.time(), 0
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes(65536):
                            f.write(chunk)
                            job["downloaded"] += len(chunk)
                            now = time.time()
                            if now - last_t >= 0.5:
                                job["speed"] = (job["downloaded"] - last_b) / (now - last_t)
                                last_t, last_b = now, job["downloaded"]
                                if job["total"]:
                                    job["progress"] = min(99, int(job["downloaded"] * 100 / job["total"]))
                    tmp.rename(DOWNLOAD_DIR / fname)
                    job["file"] = fname
                    job["progress"] = 100
                    job["status"] = "done"
    except Exception as e:
        # python TLS/网络栈失败 → curl 兜底（不动用 SEM，兜底自带限速意义不大）
        try:
            _curl_fallback(job, url, platform, ext, headers)
            if job.get("status") == "done":
                return
        except Exception:
            pass
        job["status"] = "error"
        job["error"] = str(e)[:300] or "下载失败"


def _ytdlp_hook(job: dict, d: dict):
    try:
        if d.get("status") == "downloading":
            job["downloaded"] = d.get("downloaded_bytes") or 0
            job["total"] = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            job["speed"] = d.get("speed") or 0
            if job["total"]:
                job["progress"] = min(99, int(job["downloaded"] * 100 / job["total"]))
        elif d.get("status") == "finished":
            job["progress"] = 99
    except Exception:
        pass


def _ytdlp_worker(job: dict, raw_url: str, format_id: str, title: str, platform: str):
    try:
        with SEM:
            job["status"] = "downloading"
            base = f"{PLAT_NAME_FOR_FILE.get(platform, platform)}_{_sanitize(title) or 'media'}"
            fmt = "bestvideo*+bestaudio/best" if (not format_id or format_id == "best") else format_id
            opts = {"format": fmt, "outtmpl": str(DOWNLOAD_DIR / (base + ".%(ext)s")),
                    "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
                    "merge_output_format": "mp4", "nocheckcertificate": True,
                    "concurrent_fragment_downloads": 4, "retries": 3, "fragment_retries": 3,
                    "progress_hooks": [lambda d: _ytdlp_hook(job, d)]}
            ff = _find_ffmpeg()
            if ff:
                opts["ffmpeg_location"] = str(Path(ff).parent)
            cf = _cookiefile()
            if cf:
                opts["cookiefile"] = cf
            t0 = time.time()
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([raw_url])
            cands = [p for p in DOWNLOAD_DIR.iterdir()
                     if p.is_file() and p.stat().st_mtime >= t0 - 1 and p.suffix.lower() != ".part"]
            if cands:
                p = max(cands, key=lambda p: p.stat().st_mtime)
                job["file"] = p.name
                job["total"] = job["downloaded"] = p.stat().st_size
            job["progress"] = 100
            job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)[:300] or "下载失败"


# ---------------------------------------------------------------- API

app = FastAPI(title="ViewDL")


class ParseReq(BaseModel):
    text: str


class DLItem(BaseModel):
    id: str
    kind: str = "video"
    label: str = ""
    ext: str = "mp4"
    url: Optional[str] = None
    format_id: Optional[str] = None


class DLReq(BaseModel):
    platform: str = "generic"
    title: str = ""
    raw_url: str = ""
    items: list[DLItem]


@app.post("/api/parse")
async def api_parse(req: ParseReq):
    url = extract_url(req.text)
    if not url:
        raise HTTPException(422, "未在输入中找到链接：请粘贴包含 http 的分享链接或口令")
    plat = detect_platform(url)
    chain = ROUTING.get(plat, ["ytdlp"])
    errs: list = []
    async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(20, read=25)) as client:
        for eng in chain:
            try:
                if eng == "ytdlp":
                    res = await asyncio.wait_for(asyncio.to_thread(ytdlp_extract, url), timeout=90)
                else:
                    res = await RESOLVERS[eng](client, url)
                res.setdefault("url", url)
                res.setdefault("platform", plat)
                res.setdefault("platform_label", PLATFORM_LABELS.get(plat, plat))
                res.setdefault("title", "未命名")
                res.setdefault("author", "")
                res.setdefault("cover", None)
                res.setdefault("note", "")
                res.setdefault("engine", "direct")
                return res
            except ParseError as e:
                errs.append(f"[{eng}] {e}")
            except asyncio.TimeoutError:
                errs.append(f"[{eng}] 解析超时，请重试")
            except Exception as e:
                errs.append(f"[{eng}] {type(e).__name__}: {e}")
    raise HTTPException(422, "解析失败：" + "；".join(errs))


@app.post("/api/download")
def api_download(req: DLReq):
    if not req.items:
        raise HTTPException(422, "请先勾选要下载的文件")
    jobs = []
    for it in req.items:
        job = _new_job(it.label or it.kind, req.platform, it.kind)
        job["file_title"] = req.title
        job["file_label"] = it.label
        if it.format_id:
            threading.Thread(target=_ytdlp_worker,
                             args=(job, req.raw_url, it.format_id, req.title, req.platform),
                             daemon=True).start()
        elif it.url:
            threading.Thread(target=_direct_worker, args=(job, it.url, req.platform, it.ext),
                             daemon=True).start()
        else:
            job["status"] = "error"
            job["error"] = "该条目缺少下载地址"
        jobs.append({"id": job["id"], "label": job["label"]})
    return {"jobs": jobs}


@app.get("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        lst = sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)
        return {"jobs": [{k: j[k] for k in
                          ("id", "label", "platform", "kind", "status", "progress", "downloaded",
                           "total", "speed", "file", "error", "created")} for j in lst[:60]]}


@app.get("/api/history")
def api_history():
    files = []
    for p in DOWNLOAD_DIR.iterdir():
        if p.is_file() and not p.name.endswith(".part"):
            st = p.stat()
            files.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files[:100]}


@app.get("/api/file")
def api_file(name: str):
    p = (DOWNLOAD_DIR / name).resolve()
    if not str(p).startswith(str(DOWNLOAD_DIR.resolve())) or not p.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(p, filename=p.name)


@app.post("/api/open-folder")
def api_open_folder():
    try:
        os.startfile(str(DOWNLOAD_DIR))  # noqa
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    ff = _find_ffmpeg()
    print(f"ViewDL 启动：http://127.0.0.1:{PORT}")
    print(f"下载目录：{DOWNLOAD_DIR}")
    print(f"ffmpeg：{'已就绪 ' + ff if ff else '未找到（B站/YT 高清合成将受限，建议安装）'}")
    host = os.environ.get("VIEWDL_HOST", "0.0.0.0")
    print(f"ViewDL 启动：http://{host}:{PORT}")
    uvicorn.run(app, host=host, port=PORT, log_level="warning")
