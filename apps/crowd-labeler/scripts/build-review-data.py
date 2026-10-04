"""Build the local review catalog from canonical extraction, without network access."""
import csv
import io
import json
import struct
from pathlib import Path
from PIL import Image

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
def rows(p):
    with (ROOT / p).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def number(v):
    try: return float(v) if v != '' else None
    except (ValueError, TypeError): return None

inventory = json.loads((ROOT/'data/manifests/faf_modsmaps_canonical_inventory_no_neroxis.json').read_text())
audit = {r['map_dir']: r for r in rows('data/audit/v1_current/dataset_audit_maps.csv')}
metadata = {r['map_dir']: r for r in rows('data/interim/faf_modsmaps_canonical_metadata.csv')}
assets = APP/'public/maps'
assets.mkdir(parents=True, exist_ok=True)
catalog = []
errors = []
for item in inventory['maps']:
    folder = item['top_level_dir']
    a = audit.get(folder, {})
    m = metadata.get(folder, {})
    map_id = a.get('map_id') or folder
    preview = assets/f'{map_id}.webp'
    if not preview.exists():
        try:
            source = Path(inventory['maps_root'])/item['files']['scmap'][0]['path']
            with source.open('rb') as f:
                header = f.read(34)
                size = struct.unpack_from('<i', header, 30)[0]
                if not 128 <= size <= 16_000_000: raise ValueError('Invalid preview size')
                image = Image.open(io.BytesIO(f.read(size))).convert('RGB')
                image.thumbnail((512,512))
                image.save(preview, 'WEBP', quality=85)
        except Exception as e:
            errors.append({'map':folder, 'error':str(e)})
    structural = ROOT/'data/interim/structural_previews'/f'{folder}.terrain.png'
    structural_url = None
    if structural.exists():
        target = assets/f'{map_id}-terrain.webp'
        if not target.exists(): Image.open(structural).convert('RGB').save(target,'WEBP')
        structural_url = f'/maps/{target.name}'
    catalog.append({
        'id':map_id, 'mapDir':folder,
        'canonicalName':m.get('scenario_name') if m.get('scenario_name') not in ('', 'FFA', None) else folder.rsplit('.v',1)[0].replace('_',' ').title(),
        'version':m.get('map_version',''), 'sizeX':number(m.get('scenario_size_x')), 'sizeZ':number(m.get('scenario_size_z')),
        'playerCount':number(m.get('player_slots')), 'previewUrl':f'/maps/{preview.name}' if preview.exists() else None,
        'structuralPreviewUrl':structural_url, 'hasPreview':preview.exists(), 'inventorySource':'canonical_no_neroxis',
        'priority': 'adaptive' in folder.lower() and a.get('audit_status') == 'ready',
        'waterPercent':number(a.get('water_percent')), 'buildablePercent':number(a.get('buildable_percent')),
        'mexCount':number(a.get('mex_count')), 'hydroCount':number(a.get('hydro_count')),
        'reclaimMass':number(m.get('reclaim_mass')), 'texturePack':a.get('texture_pack',''),
        'auditStatus':a.get('audit_status','unknown'), 'teamSuggestion':a.get('predicted_team_setting','unknown')
    })
(APP/'src/data/review-maps.json').write_text(json.dumps(catalog),encoding='utf-8')
(APP/'src/data/preview-report.json').write_text(json.dumps({'maps':len(catalog),'missing':errors}),encoding='utf-8')
print(json.dumps({'maps':len(catalog),'priority':sum(m['priority'] for m in catalog),'previews':sum(m['hasPreview'] for m in catalog),'missing':len(errors)}))
