#!/usr/bin/env python3
"""
APTV 订阅清洗：合并多个 m3u/txt 订阅 -> 一条 TVB 置顶的 tvb.m3u
- 按 URL 去重，再按归一化台名去重，每台最多留 2 条（第 2 条改名“（备用）”）
- TVB 系列排最前面，group-title 统一为 "01 TVB"
- 默认不做测活：很多港澳源要 Referer/特定头，测活容易误杀；
  上游公开源本身已每天测活重建，这里只做合并去重排序。
  如需测活：python3 build_playlist.py --check
用法：
  python3 build_playlist.py                 # 读 sources.yaml
  python3 build_playlist.py --check         # 附加测活（慢，易误杀）
只用你有权使用的公开或自有源。
"""
import argparse, json, re, sys, urllib.request, urllib.error
from collections import OrderedDict
from pathlib import Path
import yaml

ROOT = Path(__file__).parent
OUT = ROOT / "output" / "tvb.m3u"
REPORT_MD = ROOT / "output" / "report.md"
REPORT_JSON = ROOT / "output" / "report.json"

KEEP_PER_CHANNEL = 2

# TVB 置顶顺序：越靠前越先出。按归一化名匹配。
TVB_ORDER = [
    "翡翠台", "翡翠", "jade",
    "明珠台", "明珠", "pearl",
    "j2",
    "tvbplus", "tvb+",
    "无线新闻", "tvbnews", "tvb新闻",
    "娱乐新闻",
    "无线星河", "星河",
    "tvb",
]
GROUP_ORDER = ["01 TVB", "02 港澳台", "03 央视", "04 卫视", "05 地方台", "06 其他"]

def norm_name(name: str) -> str:
    n = name.strip()
    # 去重键：去掉“（备用）/ backup”后缀和 TVB 前缀，但保留 4K / 字幕 / 北美版等
    # 真正不同的版本（4K、字幕版、北美版）是不同源，要留着，不能并掉
    n = re.sub(r"(（备用）|\(备用\)|\s*backup\s*)", "", n, flags=re.I)
    n = re.sub(r"(1080p|1080P|720p|720P|超清|高清|标清|FHD|HD|SD|回看)", "", n)
    n = re.sub(r"[\s\-_·•]+", "", n).lower()
    n = n.replace("無綫", "无线").replace("無線", "无线")
    # TVB 翡翠台 == 翡翠台、TVB 明珠台 == 明珠台：去重键去掉开头的 tvb
    n = re.sub(r"^tvb", "", n)
    return n or name.strip().lower()

def is_tvb(name: str) -> bool:
    # 严格匹配：TVB 后面必须是中文/空格/结尾，不能是 TVBS，也不能跨词拼出来
    # （之前 "Stara TV Bandung" / "BeezyBeezTv" 会因去分隔符拼出 tvb 而误判）
    if re.search(r"TVB(?=[\u4e00-\u9fff\s\-_]|$)", name, re.I):
        return True
    return ("翡翠" in name) or ("明珠台" in name) or ("无线新闻" in name) or ("無綫新聞" in name)

def tvb_rank(name: str) -> int:
    n = norm_name(name)
    for i, key in enumerate(TVB_ORDER):
        if key in n:
            return i
    return len(TVB_ORDER)

def is_sports(ch) -> bool:
    name, g = ch["name"], ch.get("group", "")
    n = re.sub(r"[\s\-]+", "", name).lower()
    if "广东体育" in name:
        return True
    if re.search(r"cctv-?5\+?", n):
        return True
    if re.search(r"(?<![A-Za-z])NBA(?![A-Za-z])", name, re.I) or g == "NBA":
        return True
    if "体育" in name or "espn" in n:
        return True
    return False

def sports_rank(name: str) -> int:
    n = re.sub(r"[\s\-]+", "", name).lower()
    if "广东体育" in name:
        return 0
    if "cctv5+" in n or "cctv-5+" in n:
        return 2
    if "cctv5" in n:
        return 1
    if re.search(r"(?<![A-Za-z])NBA(?![A-Za-z])", name, re.I):
        return 3
    return 4

def category_of(ch):
    """0 TVB / 1 体育 / 2 港澳台 / 3 央视 / 4 卫视 / 5 其他"""
    if is_tvb(ch["name"]):
        return 0
    if is_sports(ch):
        return 1
    g, name = ch.get("group", ""), ch["name"]
    if any(k in g for k in ("港澳", "香港", "台湾", "澳门")) or "TVBS" in name or "凤凰" in name:
        return 2
    if "央视" in g or name.startswith("CCTV"):
        return 3
    if "卫视" in g or "卫视" in name:
        return 4
    return 5

def group_of(ch):
    cat = category_of(ch)
    if cat == 0:
        return "01 TVB"
    if cat == 1:
        return "02 体育"
    if cat == 2:
        return "03 港澳台"
    if cat == 3:
        return "04 央视"
    if cat == 4:
        return "05 卫视"
    return ch.get("group", "") or "其他"

def derive_label(url: str) -> str:
    # bit.ly/suxuang-v4 -> suxuang，bit.ly/iptv-aptv -> aptv，cdn.qd.je -> qd
    import urllib.parse
    p = urllib.parse.urlparse(url)
    path = p.path.strip("/").split("/")[0].split("-")[0] if p.path.strip("/") else ""
    if "bit.ly" in p.netloc and path:
        return path
    host = p.netloc.split(":")[0]
    parts = host.split(".")
    return parts[-2] if len(parts) >= 2 else host

def parse_m3u(text: str, source: str, label: str = ""):
    channels, lines = [], text.splitlines()
    cur = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            m = re.search(r'group-title="([^"]*)"', line)
            name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            tvg = re.search(r'tvg-name="([^"]*)"', line)
            cur = {"name": name or (tvg.group(1) if tvg else ""), "group": m.group(1) if m else "", "extinf": line, "source": source, "src": label}
        elif cur is not None and not line.startswith("#"):
            url = line.strip()
            if url.startswith("http"):
                cur["url"] = url
                channels.append(cur)
            cur = None
    return channels

def parse_txt(text: str, source: str, label: str = ""):
    channels = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            name, url = line.split(",", 1)
        elif "，" in line:
            name, url = line.split("，", 1)
        else:
            continue
        name, url = name.strip(), url.strip()
        if name and url.startswith("http"):
            channels.append({"name": name, "group": "", "extinf": None, "url": url, "source": source, "src": label})
    return channels

def fetch(url: str, timeout=40) -> str:
    # 带一次重试：jsDelivr / raw 偶尔超时
    last = None
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw.decode("utf-8", errors="ignore")
        except Exception as e:
            last = e
    raise last

def check_alive(url: str, timeout=8) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1023"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status < 400
        except Exception:
            return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="附加测活，失败的剔除（可能误杀需 Referer 的源）")
    ap.add_argument("--sources", default=str(ROOT / "sources.yaml"))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8")) or {}
    urls = cfg.get("sources", {}).get("urls", []) or []
    files = cfg.get("sources", {}).get("files", []) or []

    all_ch, per_source = [], {}
    for entry in urls:
        if isinstance(entry, dict):
            u, label = entry.get("url", ""), entry.get("label") or derive_label(entry.get("url", ""))
        else:
            u, label = entry, derive_label(entry)
        try:
            text = fetch(u)
            chs = parse_m3u(text, u, label) if "#EXTINF" in text[:50000] else parse_txt(text, u, label)
        except Exception as e:
            print(f"拉取失败 {u}: {e}", file=sys.stderr); chs = []
        per_source[f"{label} ({u})"] = len(chs); all_ch += chs
        print(f"{label} {u}: {len(chs)} 条")
    for f in files:
        p = ROOT / f
        if not p.exists():
            print(f"本地文件不存在 {f}", file=sys.stderr); continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        chs = parse_m3u(text, f, f) if "#EXTINF" in text[:50000] else parse_txt(text, f, f)
        per_source[f] = len(chs); all_ch += chs
        print(f"{f}: {len(chs)} 条")

    # 0) 剔死链占位：weizhi 源里有 278 条 host 是“服务器ip”的占位地址，永远播不了
    def is_bad_url(url: str) -> bool:
        if "服务器ip" in url:
            return True
        try:
            host = urllib.request.urlparse(url).netloc.split(":")[0]
        except Exception:
            return True
        if not host or any(ord(c) > 127 for c in host):
            return True
        # 内网地址（weizhi 源里 192.168.6.1 的高码/ITV，共 282 条）在你家播不了
        if host.startswith(("10.", "192.168.")) or re.match(r"172\.(1[6-9]|2[0-9]|3[01])\.", host):
            return True
        return host in ("localhost", "127.0.0.1", "0.0.0.0", "example.com", "192.0.2.1")

    bad = [c for c in all_ch if is_bad_url(c["url"])]
    bad_count = len(bad)
    if bad:
        print(f"剔除占位/死链 {bad_count} 条（例如 服务器ip）")
    all_ch = [c for c in all_ch if not is_bad_url(c["url"])]

    # 1) 按 URL 去重
    seen_url, dedup_url = set(), []
    for ch in all_ch:
        if ch["url"] in seen_url:
            continue
        seen_url.add(ch["url"]); dedup_url.append(ch)

    # 2) 按归一化台名去重，每台最多 KEEP_PER_CHANNEL 条
    by_name = OrderedDict()
    for ch in dedup_url:
        by_name.setdefault(norm_name(ch["name"]), []).append(ch)
    # 源优先顺序 = sources.yaml 里的顺序（Juli / suxuang / 裤佬 / lilei6900s 在前）
    src_order = {}
    for _i, _e in enumerate(urls):
        _label = _e.get("label") if isinstance(_e, dict) else derive_label(_e)
        src_order[_label] = _i
    kept = []
    for norm, lst in by_name.items():
        # 同名组内优先：源顺序在前、非备用、名字短的在前
        lst = sorted(lst, key=lambda c: (src_order.get(c.get("src", ""), 99),
                                         "备用" in c["name"] or "backup" in c["name"].lower(),
                                         len(c["name"])))
        for i, ch in enumerate(lst[:KEEP_PER_CHANNEL]):
            c = dict(ch)
            if i == 1 and not c["name"].endswith("（备用）"):
                c["name"] = c["name"] + "（备用）"
            kept.append(c)

    # 3) 测活（可选）
    if args.check:
        before = len(kept)
        kept = [c for c in kept if check_alive(c["url"])]
        print(f"测活剔除 {before - len(kept)} 条")

    # 4) 排序：TVB 在前，体育第二（广东体育 / CCTV5 / CCTV5+ / NBA 在前），再按分类
    def sort_key(c):
        cat = category_of(c)
        if cat == 0:
            return (cat, tvb_rank(c["name"]), c["name"])
        if cat == 1:
            return (cat, sports_rank(c["name"]), c["name"])
        return (cat, 99, c["name"])
    kept.sort(key=sort_key)

    # 5) 输出：全量 + 精简版（TVB + 体育 + 港澳台 + 央视 + 卫视，日常打开就看这个）
    OUT.parent.mkdir(parents=True, exist_ok=True)

    def display_name(c):
        # 频道名后加来源：翡翠台[qd]、翡翠台（备用）[裤佬]
        # 去重/排序用的还是原名 c["name"]，标签只在输出时加上
        src = c.get("src", "")
        return f"{c['name']}[{src}]" if src else c["name"]

    def write_m3u(path, channels):
        lines = ["#EXTM3U"]
        for c in channels:
            g = group_of(c)
            disp = display_name(c)
            extinf = c["extinf"]
            if extinf and 'group-title="' in extinf:
                extinf = re.sub(r'group-title="[^"]*"', f'group-title="{g}"', extinf, count=1)
                extinf = re.sub(r",[^,]*$", f",{disp}", extinf)
            else:
                extinf = f'#EXTINF:-1 tvg-name="{disp}" group-title="{g}",{disp}'
            lines += [extinf, c["url"]]
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_m3u(OUT, kept)
    # 精简版：只留 TVB + 体育 + 港澳台 + 央视 + 卫视（按分类，不按来源，避免地方台/直播混进来）
    slim = [c for c in kept if category_of(c) <= 4]
    slim_path = ROOT / "output" / "tvb-slim.m3u"
    write_m3u(slim_path, slim)

    tvb = [c for c in kept if category_of(c) == 0]
    sports = [c for c in kept if category_of(c) == 1]
    report = {
        "input_total": len(all_ch) + bad_count, "bad_url_removed": bad_count, "after_url_dedup": len(dedup_url),
        "output_total": len(kept), "slim_total": len(slim), "tvb_count": len(tvb),
        "tvb_channels": [display_name(c) for c in tvb],
        "sports_count": len(sports),
        "sports_channels": [display_name(c) for c in sports],
        "per_source": per_source,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(
        "# APTV 清洗报告\n\n"
        f"- 输入合计：{len(all_ch) + bad_count} 条\n- 剔除占位/死链：{bad_count} 条\n- URL 去重后：{len(dedup_url)} 条\n"
        f"- 输出合计：{len(kept)} 条（全量 tvb.m3u）\n"
        f"- 精简版：{len(slim)} 条（tvb-slim.m3u：TVB + 体育 + 港澳台 + 央视 + 卫视）\n"
        f"- TVB：{len(tvb)} 条：{', '.join(display_name(c) for c in tvb) or '无'}\n"
        f"- 体育：{len(sports)} 条：{', '.join(display_name(c) for c in sports) or '无'}\n\n"
        "## 各源\n\n" + "\n".join(f"- {k}: {v} 条" for k, v in per_source.items()) + "\n",
        encoding="utf-8")
    print(f"输出 {OUT}: {len(kept)} 条，精简 {slim_path}: {len(slim)} 条，TVB {len(tvb)} 条，体育 {len(sports)} 条")
    print("TVB:", ", ".join(display_name(c) for c in tvb))
    print("体育:", ", ".join(display_name(c) for c in sports))

if __name__ == "__main__":
    main()
