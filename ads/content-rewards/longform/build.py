# Inlines fonts + logo images into a single self-contained HTML (content-rewards-longform.html).
import base64, json, re, pathlib
here = pathlib.Path(__file__).parent
b64 = lambda p: base64.b64encode(pathlib.Path(p).read_bytes()).decode()
F = '/usr/share/fonts/opentype/inter/InterDisplay-{}.otf'
fonts = ''.join(f"@font-face{{font-family:'CR';font-weight:{w};src:url(data:font/otf;base64,{b64(F.format(n))}) format('opentype');}}\n"
                for w, n in [(400,'Regular'),(500,'Medium'),(600,'SemiBold'),(700,'Bold'),(800,'ExtraBold')])
html = (here/'src.html').read_text().replace('/*FONTS*/', fonts)
stars = json.loads((here/'assets/stars.json').read_text())
for s in stars['stars']: s['f'] = 'data:image/png;base64,' + b64(here/'assets'/s['f'])
html = html.replace('/*STARS*/null', json.dumps(stars))
html = re.sub(r'assets/([\w-]+\.png)', lambda m: 'data:image/png;base64,' + b64(here/'assets'/m.group(1)), html)
(here/'content-rewards-longform.html').write_text(html)
print('built', len(html)//1024, 'KB')
