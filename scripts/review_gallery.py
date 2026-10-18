"""Static, offline manual-review gallery; never changes selected engine outputs."""
import html
import json
from pathlib import Path
import shutil


def write_gallery(directory, manifest, rows, run_id):
    esc = lambda value: html.escape(str(value),quote=True)
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>Chameleon · Advanced review lab</title><link rel="stylesheet" href="review.css"></head><body>',
             '<header><p class="eyebrow">CHAMELEON / ADVANCED REVIEW LAB</p><h1>See where the layout holds up.</h1>',
             '<p>Actual outputs from the production engine. Inspect at native size before approving a design. '
             'Checks passing does not mean the design is readable or attractive.</p>',
             '<p class="muted">Six authored stress families and the official level-three reference. '
             'Extreme cases probe capacity limits; these are not hidden organizer tests.</p>',
             '<nav><a href="manifest.json">Frozen run manifest</a><a href="results.json">Raw results</a>'
             '<a href="inputs/suite.json">Test specification</a></nav></header>',
             '<section class="toolbar" aria-label="Review controls"><label>Family <select id="family"><option value="all">All families</option>']
    for family in manifest['suite']['families']:
        parts.append('<option value="'+esc(family['name'])+'">'+esc(family['name'])+'</option>')
    parts.append('</select></label><label>Show <select id="filter">'
                 '<option value="all">All cases</option><option value="flagged">Visual warnings</option>'
                 '<option value="failed">Contract / execution failures</option><option value="unreviewed">Not reviewed</option>'
                 '</select></label><button id="export">Export review notes</button>'
                 '<label class="file-button">Import notes<input id="import" type="file" accept="application/json"></label>'
                 '<span id="count" role="status"></span></section>'
                 '<p id="storage-status" role="status" class="storage">Notes stay in this browser. Export a copy to keep them.</p>'
                 '<main>')
    for row in rows:
        case_id = row['id']
        label = {'failed':'Contract / execution failure','review':'Checks passed · visual warnings',
                 'checks-passed':'Checks passed · manual review required'}[row['status']]
        target = row['target']
        minimum = row.get('diagnostics',{}).get('minimum_font_size')
        parts.append('<article class="case" id="'+esc(case_id)+'" data-case="'+esc(case_id)+'" data-family="'+esc(row['family'])+'" data-status="'+esc(row['status'])+'">')
        parts.append('<div class="case-head"><div><p class="eyebrow">'+esc(row['target_name'])+' / '+esc(row['pressure'])+'</p><h2>'+esc(row['family'])+'</h2></div>'
                     '<span class="badge '+esc(row['status'])+'">'+esc(label)+'</span></div>')
        parts.append('<p class="facts">'+str(target['width'])+' × '+str(target['height'])+' px · '+str(row['element_count'])+' elements · '
                     +('minimum type '+esc(round(minimum,2))+'px' if minimum is not None else 'type measurement unavailable')
                     +' · '+str(round(row['execution']['seconds'],1))+'s</p>')
        parts.append('<div class="tags">'+''.join('<span>'+esc(t)+'</span>' for t in row['tags'])+'</div>')
        if row['errors'] or row['flags']:
            parts.append('<ul class="issues">'+''.join('<li>'+esc(x)+'</li>' for x in row['errors']+row['flags'])+'</ul>')
        parts.append('<div class="zoom" aria-label="Output zoom"><button data-zoom="fit" aria-pressed="true">Fit</button>'
                     '<button data-zoom="native" aria-pressed="false">100%</button><button data-zoom="double" aria-pressed="false">200%</button>'
                     '<span>100% = one image pixel per CSS pixel. Scroll inside the frame.</span></div>')
        source = row['source_canvas']
        parts.append('<div class="pair"><figure><figcaption>Original · '+str(source['width'])+' × '+str(source['height'])+'</figcaption><div class="viewport">')
        if row.get('source_error'):
            parts.append('<p class="empty">Source render failed: '+esc(row['source_error'])+'</p>')
        else:
            parts.append('<a href="'+esc(row['source_png'])+'" target="_blank" rel="noopener"><img loading="lazy" src="'+esc(row['source_png'])+'" alt="Original '+esc(row['family'])+'"></a>')
        parts.append('</div></figure>')
        parts.append('<figure class="output" style="--w:'+str(target['width'])+'px"><figcaption>Selected output · '+str(target['width'])+' × '+str(target['height'])+'</figcaption><div class="viewport">')
        if row.get('png'):
            parts.append('<a href="'+esc(row['png'])+'" target="_blank" rel="noopener"><img loading="lazy" src="'+esc(row['png'])+'" alt="Selected output '+esc(row['family'])+'"></a>')
        else:
            parts.append('<p class="empty">No usable PNG. The failed case remains in this report.</p>')
        parts.append('</div></figure></div><div class="review-grid"><div><h3>Look for</h3><ul>'+''.join('<li>'+esc(c)+'</li>' for c in row['review'])
                     +'<li>Read every word at 100%; inspect clipping, overlap, hierarchy and spacing.</li></ul></div><div>')
        parts.append('<label for="rating-'+esc(case_id)+'">Your judgment</label><select class="rating" id="rating-'+esc(case_id)+'">'
                     '<option value="unreviewed">Not reviewed</option><option value="acceptable">Visually acceptable</option>'
                     '<option value="needs-work">Needs improvement</option><option value="unusable">Unusable</option></select>'
                     '<label for="notes-'+esc(case_id)+'">Notes</label><textarea class="notes" id="notes-'+esc(case_id)+'" maxlength="10000" rows="3" placeholder="What fails, where, and what would improve it?"></textarea></div></div>')
        parts.append('<details><summary>Diagnostics and files</summary><p><a href="'+esc(row['log'])+'">Runner log</a>'
                     +(' · <a href="'+esc(row['json'])+'">Output JSON</a>' if row.get('json') else '')+'</p><pre>'
                     +esc(json.dumps(dict(warnings=row['warnings'],diagnostics=row.get('diagnostics',{}),errors=row['errors']),indent=2))+'</pre></details></article>')
    data = dict(run_id=run_id,cases=[dict(id=r['id'],family=r['family'],status=r['status']) for r in rows])
    encoded = json.dumps(data).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    parts.append('</main><script id="review-data" type="application/json">'+encoded+'</script><script src="review.js"></script></body></html>')
    (directory/'index.html').write_text('\n'.join(parts),encoding='utf-8')
    assets = Path(__file__).parent/'review_assets'
    for name in ('review.js','review.css'):
        shutil.copyfile(assets/name,directory/name)
