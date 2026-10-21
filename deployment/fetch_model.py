"""Build-time download of the two pinned model files; no runtime network access."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import tempfile
import json
from pathlib import Path
import sys
import urllib.request


def download_ranges(entry, destination, chunk_size=8*1024*1024, workers=16):
    """Bounded parallel HTTP ranges; exact ranges and final digest are checked.

    Large public weight downloads otherwise become impractically slow on a
    single throttled connection. Temporary chunks never become trusted models.
    """
    count=(entry['bytes']+chunk_size-1)//chunk_size
    with tempfile.TemporaryDirectory(prefix='model-parts-',dir=destination.parent) as directory:
        root=Path(directory)
        def part(index):
            start=index*chunk_size;end=min(entry['bytes'],start+chunk_size)-1
            request=urllib.request.Request(entry['url'],headers={'Range':f'bytes={start}-{end}'})
            with urllib.request.urlopen(request,timeout=120) as response:
                if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{entry["bytes"]}':
                    raise ValueError('model server did not honor the exact byte range')
                remaining=end-start+1
                with (root/str(index)).open('wb') as output:
                    while remaining:
                        data=response.read(min(1024*1024,remaining))
                        if not data:raise ValueError('incomplete model byte range')
                        output.write(data);remaining-=len(data)
            return index
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for done,_ in enumerate(pool.map(part,range(count)),1):
                if done%16==0 or done==count:print(entry['name'],f'{done}/{count} chunks',flush=True)
        with destination.open('wb') as output:
            for index in range(count):
                with (root/str(index)).open('rb') as stream:
                    while data:=stream.read(1024*1024):output.write(data)


def fetch(manifest, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for entry in manifest['files']:
        name = entry['name']
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('model filename must be a basename')
        final = destination/name
        def matches(path):
            if not path.is_file() or path.stat().st_size != entry['bytes']:
                return False
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']
        if matches(final):
            continue
        partial = destination/(name+'.partial')
        try:
            if entry['bytes']>32*1024*1024:
                download_ranges(entry,partial)
            else:
                with urllib.request.urlopen(entry['url'], timeout=120) as response, partial.open('wb') as out:
                    while chunk := response.read(1024*1024):
                        out.write(chunk)
            if not matches(partial):
                raise ValueError('model hash or size mismatch: '+name)
            partial.replace(final)
        finally:
            partial.unlink(missing_ok=True)
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    fetch(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
