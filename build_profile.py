# -*- coding: utf-8 -*-
"""生成 iPhone 16 Pro / iOS 27 定制化描述文件（合法 payload 全利用 + 自签 CMS 签名）
产物：
  ios/ViewDL-unsigned.mobileconfig   原始 plist（校验用）
  ios/ViewDL.mobileconfig            CMS 签名版（装机用）
  ios/ViewDL-signing.crt             签名证书（卸载溯源/后续重签）
"""
import base64
import plistlib
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
IOS = BASE / "ios"
IOS.mkdir(exist_ok=True)

WEBCLIP_URL = "https://coffee.weizhiyu.top/vdl/"  # 任何网络可达（阿里云公网）


def make_icon() -> bytes:
    """图标由外部脚本预生成（ios/icon.png），这里直接读取"""
    return (IOS / "icon.png").read_bytes()


def payload(ptype: str, ident: str, name: str, desc: str, extra: dict) -> dict:
    p = {"PayloadType": ptype, "PayloadIdentifier": ident, "PayloadUUID": str(uuid.uuid4()).upper(),
         "PayloadVersion": 1, "PayloadDisplayName": name, "PayloadDescription": desc,
         "PayloadOrganization": "薇之雨"}
    p.update(extra)
    return p


profile = {
    "PayloadContent": [
        payload("com.apple.dnsSettings.managed", "com.weizhiyu.viewdl.doh",
                "加密 DNS（阿里 DoH）", "全局加密域名解析，降低劫持与解析延迟", {
                    "DNSSettings": {"DNSProtocol": "HTTPS",
                                    "ServerURL": "https://dns.alidns.com/dns-query"},
                }),
        payload("com.apple.webClip.managed", "com.weizhiyu.viewdl.webclip",
                "ViewDL", "主屏幕添加 ViewDL 全屏 Web 应用", {
                    "URL": WEBCLIP_URL,
                    "Label": "ViewDL",
                    "Icon": make_icon(),  # bytes → plistlib 输出 <data>（Apple 强制 Icon 为 data 类型）
                    "FullScreen": True,
                    "IsRemovable": True,
                    "IgnoreManifestScope": False,
                }),
    ],
    "PayloadDescription": "iPhone 16 Pro / iOS 27 定制化优化：加密 DNS + ViewDL 主屏应用",
    "PayloadDisplayName": "ViewDL 定制优化",
    "PayloadIdentifier": "com.weizhiyu.viewdl.profile",
    "PayloadOrganization": "薇之雨",
    "PayloadRemovalDisallowed": False,
    "PayloadScope": "System",
    "PayloadType": "Configuration",
    "PayloadUUID": str(uuid.uuid4()).upper(),
    "PayloadVersion": 1,
}

out_unsigned = IOS / "ViewDL-unsigned.mobileconfig"
with open(out_unsigned, "wb") as f:
    plistlib.dump(profile, f, fmt=plistlib.FMT_XML)

# 回读校验
with open(out_unsigned, "rb") as f:
    check = plistlib.load(f)
assert len(check["PayloadContent"]) == 2
print("plist OK:", out_unsigned, "| payloads:", [p["PayloadType"] for p in check["PayloadContent"]])
