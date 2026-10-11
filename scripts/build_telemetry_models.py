"""Render an animated language mix SVG from a validated public card.

Language proportions come from a validated public source.
Use --offline to redraw the last complete snapshot without changing its timestamp.
"""
import argparse
import hashlib
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'assets/telemetry-data.json'
NS = {'s': 'http://www.w3.org/2000/svg'}
SOURCES = {
    'languages': 'https://github-readme-stats.vercel.app/api/top-langs/?username=hoangkhanh289&layout=compact&langs_count=10',
}


def texts(node):
    return [' '.join(''.join(n.itertext()).split()) for n in node.findall('.//s:text', NS)]


def parse_activity(raw):
    root = ET.fromstring(raw)
    result = {}
    for key in ('stars', 'commits', 'prs', 'issues', 'contribs'):
        n = root.find(f'.//s:text[@data-testid="{key}"]', NS)
        value = ''.join(n.itertext()).strip() if n is not None else ''
        if not re.fullmatch(r'\d+(?:[.,]\d+)*[kKmM]?', value):
            raise ValueError(f'Missing or invalid activity counter: {key}')
        result[key] = value
    return result


def parse_languages(raw):
    root = ET.fromstring(raw)
    result = []
    parents = {child: parent for parent in root.iter() for child in parent}
    for n in root.findall('.//s:text[@data-testid="lang-name"]', NS):
        value = ' '.join(''.join(n.itertext()).split())
        match = re.fullmatch(r'(.+?)\s+(\d+(?:\.\d+)?)%', value)
        if not match:
            raise ValueError('Invalid language percentage')
        pct = float(match[2])
        if not 0 <= pct <= 100:
            raise ValueError('Language percentage outside 0..100')
        dot = parents[n].find('s:circle', NS)
        color = dot.get('fill', '#7dcfff') if dot is not None else '#7dcfff'
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            color = '#7dcfff'
        result.append({'name': match[1], 'percent': pct, 'color': color})
    if not 1 <= len(result) <= 10 or not 98 <= sum(n['percent'] for n in result) <= 101:
        raise ValueError('Incomplete or unnormalized language distribution')
    return sorted(result, key=lambda item: -item['percent'])


def parse_streak(raw):
    root = ET.fromstring(raw)
    result = {}
    for key, label in (('total', 'Total Contributions'), ('current', 'Current Streak'), ('longest', 'Longest Streak')):
        candidates = []
        for group in root.findall('.//s:g', NS):
            values = texts(group)
            nums = [v for v in values if re.fullmatch(r'\d[\d,]*', v)]
            if label in values and len(nums) == 1:
                candidates.append((len(values), values, nums[0]))
        if not candidates:
            raise ValueError(f'Missing streak counter: {label}')
        _, values, number = min(candidates, key=lambda item: item[0])
        ranges = [v for v in values if v not in (label, number)]
        if len(ranges) != 1:
            raise ValueError(f'Missing streak range: {label}')
        result[key] = {'value': number, 'range': ranges[0].replace(' - ', ' – ')}
    return result


def fetch(pair):
    key, url = pair
    req = urllib.request.Request(url, headers={'User-Agent': 'Silicon-Profile-Telemetry/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(1024 * 1024)
    return key, {'activity': parse_activity, 'languages': parse_languages, 'streak': parse_streak}[key](raw)


def text(x, y, value, size=23, fill='#B9CCE0', weight=400, anchor='start', extra=''):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>'


def tint(color, amount):
    """Lighten a language material without changing the upstream color metadata."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(c + (255 - c) * amount):02x}' for c in rgb)


def language_icons(languages):
    """Embed only the required local logos, with a code-file icon for new languages."""
    raw = Path(__file__).with_name('language-icons.svg').read_text(encoding='utf-8')
    symbols = {}
    for markup in re.findall(r'<symbol\b.*?</symbol>', raw, re.DOTALL):
        node = ET.fromstring(markup)
        symbols[node.get('data-language')] = (node.get('id'), markup)
    fallback = ('lang-code', '<symbol id="lang-code" viewBox="0 0 24 24" fill="none" stroke="#B4CEE4" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H5v20h14V7z M14 2v5h5 M9 11l-3 3 3 3 M15 11l3 3-3 3"/></symbol>')
    selected = [symbols.get(item['name'], fallback) for item in languages]
    return '\n'.join(dict(selected).values()), [icon_id for icon_id, _ in selected]


def telemetry_3d_svg(data):
    """Animated proportional language rails with language logos."""
    langs = data['languages']
    height = 196 + 98 * math.ceil(len(langs) / 2)
    icon_defs, icon_ids = language_icons(langs)
    dt = datetime.fromisoformat(data['fetched_at'].replace('Z', '+00:00'))
    timestamp = dt.strftime('%d %b %Y %H:%M UTC').upper()
    desc = (
        "Animated language mix with language logos and proportional 3D rails. "
        "Language distribution by repository size: "
        + ', '.join(f"{item['name']} {item['percent']:.2f}%" for item in langs)
        + f". Source snapshot fetched at {data['fetched_at']}."
    )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-labelledby="telemetry-title telemetry-desc">',
        '<title id="telemetry-title">Animated language mix</title>',
        f'<desc id="telemetry-desc">{escape(desc)}</desc>',
        '''<style>
          text { font-family: "Segoe UI", Arial, sans-serif; }
          .num { font-variant-numeric: tabular-nums; }
          .overline { letter-spacing: 2px; }
          .rail-body { animation: railHover 6s ease-in-out infinite; }
          .rail-glint { animation: railGlint 5.4s ease-in-out infinite; }
          .rail-shadow { animation: shadow 6s ease-in-out infinite; }
          @keyframes railHover { 0%,100% { transform: translateY(0) skewY(0); } 50% { transform: translateY(-7px) skewY(-1deg); } }
          @keyframes railGlint { 0%,15% { transform: translateX(0); } 85%,100% { transform: translateX(485px); } }
          @keyframes shadow { 0%,100% { opacity:.6; } 50% { opacity:.25; } }
          @media (prefers-reduced-motion: reduce) {
            .rail-body, .rail-glint, .rail-shadow { animation: none !important; }
            .rail-glint { display:none; }
          }
        </style>
        <defs>
          <radialGradient id="space" cx="35%" cy="12%" r="90%">
            <stop stop-color="#0C1B2B"/><stop offset=".5" stop-color="#080F1C"/><stop offset="1" stop-color="#040911"/>
          </radialGradient>
          <radialGradient id="aura">
            <stop stop-color="#22D3EE" stop-opacity=".14"/><stop offset="1" stop-color="#22D3EE" stop-opacity="0"/>
          </radialGradient>
          <linearGradient id="rail-reflection">
            <stop stop-color="#FFF" stop-opacity="0"/><stop offset=".5" stop-color="#FFF" stop-opacity=".65"/><stop offset="1" stop-color="#FFF" stop-opacity="0"/>
          </linearGradient>
        </defs>''',
        f'<defs>{icon_defs}</defs>',
        f'<rect width="1000" height="{height}" rx="24" fill="url(#space)"/>',
        '<ellipse cx="315" cy="135" rx="390" ry="150" fill="url(#aura)"/>',
    ]

    def heading(y, title, subtitle):
        out.extend([
            text(52, y, title, 29, '#E7F2FA', 700, extra='class="overline"'),
            text(52, y + 32, subtitle, 22, '#96ADC3'),
        ])

    heading(73, 'LANGUAGE MIX', 'Share of repository code size')
    # Each rail has its own label row. Widths remain literal percentages, even 0%.
    rail_width, depth, thickness = 392, 27, 20
    for i, item in enumerate(langs):
        x, y = 52 + (i % 2) * 484, 156 + (i // 2) * 98
        color, pct = item['color'], item['percent']
        active = rail_width * pct / 100
        out += [
            f'<g id="rail-{i}" transform="translate({x} {y})" data-percent="{pct}" data-active-width="{active:.4f}" data-track-width="{rail_width}">',
            f'<use class="language-icon" href="#{icon_ids[i]}" x="0" y="-25" width="28" height="28"/>',
            text(40, 0, item['name'], 26, '#D9E8F3', 600),
            text(419, 0, f'{pct:.2f}%', 28, '#F1F6FF', 650, 'end', 'class="num"'),
            f'<ellipse class="rail-shadow" cx="209" cy="65" rx="209" ry="6" fill="#01050C" style="animation-delay:{-i * .65}s"/>',
            f'<g transform="translate(0 10)"><g class="rail-body" style="animation-delay:{-i * .65}s">',
            '<polygon points="0,35 27,15 419,15 392,35" fill="#1C2C42" stroke="#3A4E69" stroke-width="1.2"/>',
            f'<polygon points="0,35 392,35 392,{35 + thickness} 0,{35 + thickness}" fill="#0C1728" stroke="#2E4059" stroke-width="1.2"/>',
            f'<polygon points="392,35 419,15 419,{15 + thickness} 392,{35 + thickness}" fill="#101F33" stroke="#3A4E69" stroke-width="1.2"/>',
        ]
        if active > 0:
            out += [
                f'<polygon points="0,35 {depth},15 {active + depth:.4f},15 {active:.4f},35" fill="{tint(color, .36)}"/>',
                f'<polygon points="0,35 {active:.4f},35 {active:.4f},{35 + thickness} 0,{35 + thickness}" fill="{color}"/>',
                f'<polygon points="{active:.4f},35 {active + depth:.4f},15 {active + depth:.4f},{15 + thickness} {active:.4f},{35 + thickness}" fill="{tint(color, .12)}"/>',
                f'<path d="M0 35 L{depth} 15 H{active + depth:.4f}" fill="none" stroke="{tint(color, .7)}" stroke-width="1.5"/>',
                f'<clipPath id="rail-clip-{i}"><polygon points="0,35 {depth},15 {active + depth:.4f},15 {active + depth:.4f},{15 + thickness} {active:.4f},{35 + thickness} 0,{35 + thickness}"/></clipPath>',
                f'<g clip-path="url(#rail-clip-{i})"><rect class="rail-glint" x="-58" y="12" width="48" height="46" fill="url(#rail-reflection)" style="animation-delay:{-i * .65}s"/></g>',
            ]
        out.append('</g></g></g>')
    out += [
        text(500, height - 28, f'UPDATED {timestamp}', 18, '#8AA4BE', 500, 'middle', 'class="overline"'),
        '</svg>',
    ]
    return '\n'.join(out) + '\n'


def write_assets(data):
    assets = {
        'telemetry-3d': telemetry_3d_svg(data),
    }
    for name, svg in assets.items():
        ET.fromstring(svg)
        (ROOT / f'assets/{name}.svg').write_text(svg, encoding='utf-8', newline='\n')
    for rel in ('README.md', 'docs/telemetry-layout.html'):
        p = ROOT / rel
        content = p.read_text(encoding='utf-8')
        for name, svg in assets.items():
            digest = hashlib.sha256(svg.encode()).hexdigest()[:12]
            content = re.sub(rf'(assets/{name}\.svg)\?v=[\w.-]+', rf'\1?v={digest}', content)
        p.write_text(content, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args()
    if args.offline:
        data = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            data = dict(pool.map(fetch, SOURCES.items()))
        data.update(fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), sources=SOURCES)
    write_assets(data)
    if not args.offline:
        SNAPSHOT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Rendered 3D telemetry stage; source snapshot:', data['fetched_at'])


if __name__ == '__main__':
    main()
