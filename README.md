# APTV TVB 置顶订阅

12 条订阅（截图）整理后 10 条唯一源合并、去重、TVB 置顶，每天 08:00（北京时间）自动重建。

## APTV 里只加这一条

精简版（日常用，TVB + 港澳台 + 央视 + 卫视，748 台）：

```
https://raw.githubusercontent.com/jasonfung9/aptv-tvb/main/output/tvb-slim.m3u
```

国内 raw 打不开就用 jsDelivr 镜像：

```
https://cdn.jsdelivr.net/gh/jasonfung9/aptv-tvb@main/output/tvb-slim.m3u
```

全量版（6838 台）：

```
https://raw.githubusercontent.com/jasonfung9/aptv-tvb/main/output/tvb.m3u
```

> 上面地址是仓库建好并推送后才生效。没建仓库前，先用本地文件试。

APTV 操作：配置 → 右上角 + → 订阅配置 → 贴精简版链接 → 勾自动刷新 → 回频道页，`01 TVB` 分组排在最前面。

## 体育分组（2026-11-24 09:03 新增）

精简版分组顺序：01 TVB、02 体育、03 港澳台、04 央视、05 卫视。

体育组 82 条，排在前面的就是你要的那 4 个：广东体育、 CCTV5、 CCTV5+、 NBA（裤佬源里的当日比赛，每场有直播 / 原声 / 中文解说三条，比赛每天换，今天 6 场 18 条）。后面还跟了劲爆体育、五星体育、纬来体育、 ELEVEN 体育、 NewTV 超级体育等。

注意：bit.ly/jsnzkpg 那个裤佬的单独 IPTV 文件已 404，裤佬的 NBA 比赛就是裤佬源（iptv.445569.xyz）里的 NBA 分组，不用再单独加源。

## 本次实测（2026-11-24）

- 输入：10 条源合计 9782 条
  - Juli：121 条，suxuang：1211 条，裤佬：3209 条，lilei6900s：794 条
  - weizhi：1282 条，APTV：119 条，YanG：171 条，itvlist：600 条
  - FMM：82 条（纯 IPv6），Free-TV：2193 条
- 剔除：Kimentanm（与 APTV 同链接重复）、Gary（APTV 标已失效，链接截断无法恢复）
- 剔除占位/死链 1217 条：weizhi 源里 host 是“服务器ip”或“肥羊IP”的占位地址，以及 192.168.6.1 内网地址的高码/ITV（共 282 条），在你家都播不了
- URL 去重后 7999 条 → 输出全量 6634 条，精简版 734 条
- TVB 57 条：翡翠台、翡翠台 4K、明珠台、TVB Plus、无线新闻、娱乐新闻、无线星河、翡翠剧集台等，每台留 1 条主用 + 1 条“（备用）”，来自不同源
- 精简版构成：TVB 57 + 体育 82 + 港澳台 200 + 央视 202 + 卫视 193
- 445569 就是裤佬：iptv.445569.xyz 是裤佬（Jsnzkpg）的 IPTV 订阅，裤佬的 GitHub 是 Jsnzkpg/Jsnzkpg，README 里“永久IPTV订阅”就是这个地址
- 标签取自 APTV 标题，去掉括号部分：裤佬、APTV、FMM、suxuang、weizhi、itvlist、Free-TV、Juli、YanG、lilei6900s
  - 例：`翡翠台[Juli]`、`翡翠台（备用）[裤佬]`、`明珠台[suxuang]`
- 注意：上游源每天会变，条数每次重建都可能上下浮动，属正常。单个流能不能播需在 Apple TV 上实测，服务器侧测不了。

## 怎么改

- 加 / 换源：改 `sources.yaml` 里的 `urls`，再跑 `python3 build_playlist.py`
- 只用你有权使用的公开或自有源。
- 脚本默认不测活：很多港澳源要 Referer/特定头，测活容易误杀；上游源本身已每天重建。
  如需测活：`python3 build_playlist.py --check`

## 文件

- `build_playlist.py`：合并、去重、剔占位、TVB 置顶脚本
- `sources.yaml`：订阅源列表（顺序 = 主用优先顺序）
- `output/tvb.m3u`：全量
- `output/tvb-slim.m3u`：精简版（APTV 订阅用这个）
- `output/report.md` / `report.json`：每次重建的报告
- `.github/workflows/daily.yml`：每天自动重建并提交
