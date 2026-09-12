# coding: utf-8
"""Download verified report photos and prepare publishing copies without cropping."""
import hashlib, json, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
date = sys.argv[1]
report = json.loads((ROOT / 'data/reports' / (date + '.json')).read_text())
out = ROOT / 'outputs/daily' / date
originals, inserts = out / '原尺寸图片', out / '排版插图'
originals.mkdir(parents=True, exist_ok=True)
inserts.mkdir(parents=True, exist_ok=True)
records, failures = [], []
for media in report.get('media', []):
    try:
        name = media['fileName']
        if Path(name).name != name:
            raise ValueError('Image filename must not contain a directory')
        path = originals / name
        if not path.exists():
            parts = urlsplit(media['originalURL'])
            if parts.scheme != 'https':
                raise ValueError('HTTPS image URL required')
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
            with urlopen(Request(url, headers={'User-Agent': 'TerroirAtlas/1.0 (editorial photo archive)'}), timeout=40) as response:
                raw = response.read(40 * 1024 * 1024 + 1)
            if len(raw) > 40 * 1024 * 1024:
                raise ValueError('Source image exceeds the 40 MB download limit')
            temporary = path.with_suffix('.download')
            temporary.write_bytes(raw)
            with Image.open(temporary) as check:
                check.verify()
            temporary.replace(path)
        with Image.open(path) as original:
            # Honor camera orientation; keep the downloaded original bytes intact.
            picture = ImageOps.exif_transpose(original).convert('RGB')
            dimensions = picture.size
            if dimensions != (media['width'], media['height']):
                raise ValueError('Source dimensions differ from verified metadata: ' + str(dimensions))
            picture.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            picture.save(inserts / name, quality=93, optimize=True)
        records.append({**media, 'originalFile': '原尺寸图片/' + name, 'insertFile': '排版插图/' + name,
                        'originalBytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'insertWidth': picture.width, 'insertHeight': picture.height})
        print(media['id'], dimensions, 'ready', flush=True)
    except Exception as error:
        failures.append(media['id'] + ': ' + str(error))
        print('Source unavailable:', failures[-1], flush=True)
if failures:
    raise SystemExit('Media preparation incomplete. Keep these sources pending; do not render missing images.\n' + '\n'.join(failures))
(out / '图片清单.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print('Prepared', len(records), 'original photos and proportional insert copies.')
