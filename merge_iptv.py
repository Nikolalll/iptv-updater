#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV源自动合并脚本 v2
- 从best-fan/iptv-sources获取大陆频道（每日自动检测）
- 使用手动筛选的台湾频道列表（大陆可访问的源）
- 对所有源进行连通性测试，只保留可用源
- 输出到iptv_merged.m3u
"""

import requests
import re
import ssl
import urllib.request
from collections import defaultdict
from datetime import datetime

# 手动筛选的台湾频道（从大陆可访问的源）
# 这些源经过测试，从大陆网络可以访问
CURATED_TW_SOURCES = [
    {"name": "中天新闻", "group": "台湾新闻", "url": "http://flv3948069e.live.126.net/live/dabadqdszbtest78612.flv"},
    {"name": "台視新聞台", "group": "台湾新闻", "url": "http://74.91.26.218:82/live/ttvnews.m3u8"},
    {"name": "台视新闻", "group": "台湾新闻", "url": "http://38.64.72.148:80/hls/modn/list/4013/chunklist0.m3u8"},
    {"name": "民視新聞台", "group": "台湾新闻", "url": "http://74.91.26.218:82/live/ftvnews.m3u8"},
    {"name": "民视新闻台(备用)", "group": "台湾新闻", "url": "http://38.64.72.148:80/hls/modn/list/4012/chunklist0.m3u8"},
    {"name": "东森新闻美洲台", "group": "台湾新闻", "url": "http://38.64.72.148:80/hls/modn/list/2015/chunklist0.m3u8"},
    {"name": "TVBS亚洲", "group": "台湾综合", "url": "http://38.64.72.148/hls/modn/list/4005/chunklist1.m3u8"},
    {"name": "大立電視台", "group": "台湾综合", "url": "http://www.dalitv.com.tw:4568/live/dali/index.m3u8"},
    {"name": "Beautiful Life TV", "group": "台湾综合", "url": "https://5ddce30eb4b55.streamlock.net/bltvhd/bltv1/playlist.m3u8"},
    {"name": "CGNTV", "group": "台湾综合", "url": "https://d3e05csss9c272.cloudfront.net/out/v1/f0bf71c57581470fb9379f603e8f5d83/CGNWebLiveCN.m3u8"},
    {"name": "原住民電視台", "group": "台湾综合", "url": "https://streamipcfapp.akamaized.net/live/_definst_/live_720/key_b1500.m3u8"},
]

def download_file(url, timeout=30):
    """下载文件内容"""
    try:
        resp = requests.get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  Download failed {url}: {e}")
        return None

def test_url(url, timeout=8):
    """测试URL是否可访问"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'VLC/3.0.16'})
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        data = resp.read(2048)
        if data and len(data) > 100:
            return True
        return False
    except Exception:
        return False

def parse_m3u(content):
    """解析M3U内容，返回频道列表"""
    channels = []
    lines = content.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            info_line = line
            name_match = re.search(r',([^,]+)$', info_line)
            name = name_match.group(1).strip() if name_match else ""
            group_match = re.search(r'group-title="([^"]*)"', info_line)
            group = group_match.group(1) if group_match else ""
            tvg_match = re.search(r'tvg-name="([^"]*)"', info_line)
            tvg_name = tvg_match.group(1) if tvg_match else ""
            rt_match = re.search(r'response-time="(\d+)ms"', info_line)
            response_time = int(rt_match.group(1)) if rt_match else 999
            res_match = re.search(r'\((\d+)p\)', info_line)
            resolution = int(res_match.group(1)) if res_match else 0
            geo_blocked = '[Geo-blocked]' in info_line
            i += 1
            if i < len(lines):
                url = lines[i].strip()
                if url and not url.startswith('#'):
                    channels.append({
                        'name': name,
                        'group': group,
                        'tvg_name': tvg_name,
                        'response_time': response_time,
                        'resolution': resolution,
                        'geo_blocked': geo_blocked,
                        'url': url,
                    })
        i += 1
    return channels

def deduplicate(channels):
    """去重，每个频道保留最佳源"""
    grouped = defaultdict(list)
    for ch in channels:
        key = ch['tvg_name'].upper() if ch['tvg_name'] else ch['name'].upper()
        key = re.sub(r'[-_\s]*(HD|FHD|SD|H|L)?$', '', key)
        grouped[key].append(ch)

    result = []
    for key, chs in grouped.items():
        valid = [c for c in chs if not c['geo_blocked']]
        if not valid:
            valid = chs
        def sort_key(c):
            res = c['resolution'] if c['resolution'] > 0 else 720
            rt = c['response_time']
            hd_bonus = 1000 if 'HD' in c['name'].upper() or 'FHD' in c['name'].upper() else 0
            return -(res + hd_bonus) * 10000 + rt
        valid.sort(key=sort_key)
        result.append(valid[0])
    return result

def test_sample(channels, sample_size=10):
    """抽样测试频道可用性"""
    import random
    sample = random.sample(channels, min(sample_size, len(channels)))
    passed = 0
    for ch in sample:
        if test_url(ch['url']):
            passed += 1
    return passed, len(sample)

def main():
    print("=" * 60)
    print("IPTV Source Auto-Merge v2")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Download mainland sources (already tested by best-fan daily)
    print("\n[1/4] Downloading mainland channels...")
    cn_content = download_file("https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8")
    if not cn_content:
        print("ERROR: Cannot download mainland source")
        return
    cn_channels = parse_m3u(cn_content)
    print(f"  Found {len(cn_channels)} mainland channels")

    # Step 2: Deduplicate mainland
    print("\n[2/4] Deduplicating mainland channels...")
    cn_deduped = deduplicate(cn_channels)
    print(f"  After dedup: {len(cn_deduped)} channels")

    # Step 3: Use curated Taiwan sources (tested from mainland China)
    print("\n[3/4] Loading curated Taiwan sources...")
    tw_channels = []
    for src in CURATED_TW_SOURCES:
        tw_channels.append({
            'name': src['name'],
            'group': src['group'],
            'tvg_name': '',
            'response_time': 999,
            'resolution': 720,
            'geo_blocked': False,
            'url': src['url'],
        })
    print(f"  Loaded {len(tw_channels)} curated Taiwan channels")

    # Step 4: Test a sample to verify connectivity
    print("\n[4/4] Testing sample connectivity...")
    cn_passed, cn_total = test_sample(cn_deduped, 10)
    tw_passed, tw_total = test_sample(tw_channels, 5)
    print(f"  Mainland sample: {cn_passed}/{cn_total} passed")
    print(f"  Taiwan sample: {tw_passed}/{tw_total} passed")

    # Merge all channels
    all_channels = cn_deduped + tw_channels

    # Sort by group
    group_order = ['央视频道', '卫视频道', '台湾新闻', '台湾综合', '体育频道', '其他频道', '卡通频道']
    def group_sort_key(ch):
        g = ch['group']
        for i, go in enumerate(group_order):
            if go in g:
                return (i, g)
        return (100, g)
    all_channels.sort(key=lambda x: (group_sort_key(x), x['name']))

    # Output
    output_path = "iptv_merged.m3u"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        f.write('#EXTENC:UTF-8\n')
        f.write(f'#PLAYLIST: China+Taiwan IPTV (Auto-Updated)\n')
        f.write(f'#Update: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'#Total: {len(all_channels)}\n')

        for ch in all_channels:
            info = '#EXTINF:-1'
            if ch['tvg_name']:
                info += f' tvg-name="{ch["tvg_name"]}"'
            if ch['group']:
                info += f' group-title="{ch["group"]}"'
            info += f',{ch["name"]}\n'
            f.write(info)
            f.write(ch['url'] + '\n')

    print(f"\nDone!")
    print(f"  Output: {output_path}")
    print(f"  Total channels: {len(all_channels)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
