"""Protect upstream parsing, snapshot validation, and telemetry 3D model generation."""
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import build_telemetry_models as models


class TelemetryDataTests(unittest.TestCase):
    def test_zero_is_a_real_counter_but_missing_counter_is_an_error(self):
        fields = ''.join(f'<text data-testid="{key}">0</text>' for key in ('stars', 'commits', 'prs', 'issues', 'contribs'))
        raw = f'<svg xmlns="http://www.w3.org/2000/svg">{fields}</svg>'
        self.assertEqual(models.parse_activity(raw)['stars'], '0')
        with self.assertRaises(ValueError):
            models.parse_activity(raw.replace('<text data-testid="stars">0</text>', ''))

    def test_service_error_page_is_not_a_valid_snapshot(self):
        raw = '<svg xmlns="http://www.w3.org/2000/svg"><text>API rate limit exceeded</text></svg>'
        for parser in (models.parse_activity, models.parse_languages, models.parse_streak):
            with self.subTest(parser=parser.__name__), self.assertRaises(ValueError):
                parser(raw)

    def test_language_names_and_colors_are_preserved_and_sorted(self):
        raw = '''<svg xmlns="http://www.w3.org/2000/svg">
        <g><circle fill="#f34b7d"/><text data-testid="lang-name">C++ 40.00%</text></g>
        <g><circle fill="#3572A5"/><text data-testid="lang-name">Python 60.00%</text></g>
        </svg>'''
        parsed = models.parse_languages(raw)
        self.assertEqual([n['name'] for n in parsed], ['Python', 'C++'])
        self.assertEqual(parsed[1]['color'], '#f34b7d')
        with self.assertRaises(ValueError):
            models.parse_languages(raw.replace('60.00%', '5.00%'))

    def test_streak_is_bound_to_labels_even_when_groups_reorder(self):
        groups = ''.join(f'<g><g><text>{label}</text></g><g><text>{number}</text></g><g><text>{date}</text></g></g>'
                         for label, number, date in (('Longest Streak', '13', 'Jan 1 - Jan 13'),
                                                    ('Total Contributions', '1,234', '2022 - Present'),
                                                    ('Current Streak', '0', 'Today')))
        parsed = models.parse_streak(f'<svg xmlns="http://www.w3.org/2000/svg">{groups}</svg>')
        self.assertEqual(parsed['total']['value'], '1,234')
        self.assertEqual(parsed['current']['value'], '0')
        self.assertEqual(parsed['longest']['range'], 'Jan 1 – Jan 13')

    def test_failed_fetch_cannot_overwrite_existing_assets(self):
        with patch('sys.argv', ['build_telemetry_models.py']), patch.object(models, 'fetch', side_effect=ValueError('source unavailable')), patch.object(models, 'write_assets') as writer:
            with self.assertRaises(ValueError):
                models.main()
            writer.assert_not_called()

    def test_offline_redraw_preserves_retrieval_time(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        with patch('sys.argv', ['build_telemetry_models.py', '--offline']), patch.object(models, 'fetch') as fetch, patch.object(models, 'write_assets') as writer:
            models.main()
            fetch.assert_not_called()
            self.assertEqual(writer.call_args.args[0]['fetched_at'], data['fetched_at'])

    def test_telemetry_3d_stage_is_valid_svg_and_contains_all_metrics(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        svg = models.telemetry_3d_svg(data)
        # Parse XML to verify well-formedness
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
        expected_height = 196 + 98 * ((len(data['languages']) + 1) // 2)
        self.assertEqual(root.attrib.get('viewBox'), f'0 0 1000 {expected_height}')

        # Check every returned language and percentage.
        for lang in data['languages']:
            self.assertIn(f'>{lang["name"]}<', svg)
            self.assertIn(f'{lang["percent"]:.2f}%', svg)

        # New refreshes need only the language distribution and retrieval time.
        minimal_data = {k: data[k] for k in ('languages', 'fetched_at')}
        self.assertEqual(models.telemetry_3d_svg(minimal_data), svg)
        self.assertEqual(set(models.SOURCES), {'languages'})
        self.assertIn('langs_count=10', models.SOURCES['languages'])

        # Check reduced motion rule is present
        self.assertIn('prefers-reduced-motion: reduce', svg)
        self.assertIn('animation: none !important', svg)

        # Confirm no deprecated card-border and dashed line effects
        self.assertNotIn('stroke-dasharray="7 35"', svg)
        self.assertNotIn('stroke-dashoffset', svg)

    def test_top_ten_languages_have_room_icons_and_updated_only_footer(self):
        names = ['Python', 'HTML', 'CSS', 'C++', 'JavaScript', 'C',
                 'TypeScript', 'Jupyter Notebook', 'Shell', 'New Language']
        raw = '<svg xmlns="http://www.w3.org/2000/svg">' + ''.join(
            f'<g><circle fill="#3572A5"/><text data-testid="lang-name">{name} 10.00%</text></g>'
            for name in names) + '</svg>'
        languages = models.parse_languages(raw)
        self.assertEqual(len(languages), 10)
        with self.assertRaises(ValueError):
            models.parse_languages(raw.replace('</svg>', '<g><text data-testid="lang-name">Extra 0%</text></g></svg>'))
        data = {'languages': languages, 'fetched_at': '2026-10-11T06:01:33+00:00'}
        root = ET.fromstring(models.telemetry_3d_svg(data))
        ns = models.NS
        self.assertEqual(root.get('viewBox'), '0 0 1000 686')
        symbols = {node.get('id') for node in root.findall('.//s:symbol', ns)}
        for i, name in enumerate(names):
            rail = root.find(f'.//s:g[@id="rail-{i}"]', ns)
            self.assertFalse(rail.findall('s:circle', ns))
            icon = rail.find('s:use[@class="language-icon"]', ns)
            self.assertIn(icon.get('href')[1:], symbols)
            self.assertEqual(icon.get('width'), '28')
            if name == 'New Language':
                self.assertEqual(icon.get('href'), '#lang-code')
            x, y = map(int, rail.get('transform')[10:-1].split())
            self.assertEqual(y, 156 + (i // 2) * 98)
            self.assertLess(y + 71, 658)
        footer = root.findall('s:text', ns)[-1]
        self.assertEqual(footer.text, 'UPDATED 11 OCT 2026 06:01 UTC')
        self.assertEqual(footer.get('y'), '658')
        self.assertFalse(root.findall('.//s:image', ns))
        for use in root.findall('.//s:use', ns):
            self.assertTrue(use.get('href').startswith('#'))

    def test_polygon_points_are_coordinates_and_animation_preserves_layout(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        root = ET.fromstring(models.telemetry_3d_svg(data))
        ns = {'s': 'http://www.w3.org/2000/svg'}
        polygons = root.findall('.//s:polygon', ns)
        self.assertGreaterEqual(len(polygons), 3 * len(data['languages']))
        coordinate = r'-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?'
        for polygon in polygons:
            self.assertRegex(polygon.get('points'), '^' + coordinate + '(?: ' + coordinate + '){2,}$')
        parents = {child: parent for parent in root.iter() for child in parent}
        for node in root.findall('.//s:g[@class="rail-body"]', ns):
            self.assertNotIn('transform', node.attrib)
            self.assertTrue(parents[node].get('transform', '').startswith('translate('))

        # Every material reference resolves locally.
        ids = {node.get('id') for node in root.iter() if node.get('id')}
        for use in root.findall('.//s:use', ns):
            self.assertIn(use.get('href')[1:], ids)

    def test_language_mix_omits_workspace_activity_and_streak_models(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        svg = models.telemetry_3d_svg(data)
        root = ET.fromstring(svg)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        self.assertNotIn('ENGINEERING ACTIVITY', svg)
        self.assertNotIn('Public GitHub metrics', svg)
        for old_id in ('activity-package', 'act-die-clip', 'model-flame', 'model-trophy', 'contribution-blocks', 'model-commits'):
            self.assertIsNone(root.find(f'.//*[@id="{old_id}"]'))
        for model in ('model-workstation', 'laptop', 'terminal-panel', 'browser-panel'):
            self.assertIsNone(root.find(f'.//*[@id="{model}"]'))
        for resource in ('laptop-frame', 'keyboard-deck', 'editor-material', 'terminal-material', 'browser-material', 'editor-clip'):
            self.assertIsNone(root.find(f'.//*[@id="{resource}"]'))
        self.assertNotIn('workspace', svg.lower())
        self.assertNotIn('laptop', svg.lower())
        for label in ('CONTRIBUTION STREAKS', 'Total contributions', 'COMMITS', 'STARS', 'PULL REQUESTS', 'ISSUES', 'CONTRIBUTED REPOS', 'LAST YEAR'):
            self.assertNotIn(label, svg)
        self.assertFalse(root.findall('.//s:animateMotion', ns))
        self.assertFalse(root.findall('.//s:text/s:animate', ns))

    def test_language_rails_preserve_percentages_and_separate_label_rows(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        for percentages in (None, [100, 0, 0, 0, 0, 0]):
            if percentages:
                for lang, percent in zip(data['languages'], percentages):
                    lang['percent'] = percent
            root = ET.fromstring(models.telemetry_3d_svg(data))
            ns = {'s': 'http://www.w3.org/2000/svg'}
            positions = []
            for i, lang in enumerate(data['languages']):
                rail = root.find(f'.//s:g[@id="rail-{i}"]', ns)
                track = float(rail.get('data-track-width'))
                active = float(rail.get('data-active-width'))
                self.assertAlmostEqual(active / track * 100, lang['percent'], places=4)
                x, y = map(int, rail.get('transform')[10:-1].split())
                positions.append((x, y))
                labels = rail.findall('s:text', ns)
                self.assertTrue(all(float(label.get('font-size')) >= 26 for label in labels))
                self.assertEqual([label.text for label in labels], [lang['name'], f"{lang['percent']:.2f}%"])
                body = rail.find('.//s:g[@class="rail-body"]', ns)
                polygons = body.findall('s:polygon', ns)
                self.assertEqual(len(polygons), 6 if lang['percent'] else 3)
                clip = body.find(f's:clipPath[@id="rail-clip-{i}"]/s:polygon', ns)
                if lang['percent']:
                    self.assertIsNotNone(clip)
                    clip_x = [float(p.split(',')[0]) for p in clip.get('points').split()]
                    self.assertAlmostEqual(max(clip_x), active + 27, places=4)
                else:
                    self.assertIsNone(clip)
            self.assertEqual(len(set(positions)), len(positions))
            for x, y in positions:
                for other_x, other_y in positions:
                    if x == other_x and y != other_y:
                        self.assertGreaterEqual(abs(y - other_y), 98)


    def test_writer_generates_only_used_asset_with_matching_byte_hash(self):
        data = json.loads(models.SNAPSHOT.read_text(encoding='utf-8'))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'assets').mkdir()
            (root / 'docs').mkdir()
            for rel in ('README.md', 'docs/telemetry-layout.html'):
                (root / rel).write_text('assets/telemetry-3d.svg?v=old', encoding='utf-8')
            with patch.object(models, 'ROOT', root):
                models.write_assets(data)
            files = list((root / 'assets').iterdir())
            self.assertEqual([p.name for p in files], ['telemetry-3d.svg'])
            raw = files[0].read_bytes()
            self.assertNotIn(b'\r', raw)
            digest = hashlib.sha256(raw).hexdigest()[:12]
            for rel in ('README.md', 'docs/telemetry-layout.html'):
                self.assertIn('?v=' + digest, (root / rel).read_text(encoding='utf-8'))



if __name__ == '__main__':
    unittest.main()
