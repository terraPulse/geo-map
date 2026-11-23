'''Build the isolated test Lambda zip for python3.12 x86_64.

Does not call AWS. Pillow is the only third-party package. gio, GDAL, and
Cython are not compiled and are not included.
'''

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

PILLOW_VERSION = '12.2.0'
PYTHON_TAG = 'cp312'
PLATFORM = 'manylinux2014_x86_64'
RUNTIME = 'python3.12'
HANDLER = 'handler.lambda_handler'

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, '..', '..'))
RUNTIME_FILES = ('handler.py', 'serve.py', 'registry.py', 'reader.py')


def build(zip_path):
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)), exist_ok=True)
    work = tempfile.mkdtemp(prefix='geomap-tile-pyramid-')
    try:
        wheel = _download_pillow(os.path.join(work, 'wheels'))
        target = os.path.join(work, 'task')
        os.makedirs(target)
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-compile',
             '--target', target, wheel],
        )
        for name in RUNTIME_FILES:
            shutil.copy(os.path.join(ROOT, name), os.path.join(target, name))
        shutil.copy(
            os.path.join(REPO, 'util', 'lib', 'tile_runtime.py'),
            os.path.join(target, 'tile_runtime.py'),
        )
        _write_fixture(target)
        _strip(target)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        _zip_dir(target, zip_path)
        digest = _sha256(zip_path)
        wheel_digest = _sha256(wheel)
        manifest = {
            'artifact': os.path.basename(zip_path),
            'sha256': digest,
            'bytes': os.path.getsize(zip_path),
            'runtime': RUNTIME,
            'architecture': 'x86_64',
            'handler': HANDLER,
            'pillow': {
                'version': PILLOW_VERSION,
                'wheel': os.path.basename(wheel),
                'sha256': wheel_digest,
                'platform': PLATFORM,
                'python': PYTHON_TAG,
            },
            'boto3': 'provided by the Lambda python3.12 runtime; not vendored',
            'excluded': ['gio', 'gdal', 'cython', 'lambda/handler.py'],
            'adapter': 'geomap.png_pyramid',
            'adapter_version': '1.0.0',
        }
        manifest_path = zip_path + '.manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2)
            handle.write('\n')
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _download_pillow(dest):
    os.makedirs(dest, exist_ok=True)
    subprocess.check_call([
        sys.executable, '-m', 'pip', 'download',
        'pillow==%s' % PILLOW_VERSION,
        '--only-binary=:all:',
        '--python-version', '312',
        '--implementation', 'cp',
        '--abi', PYTHON_TAG,
        '--platform', PLATFORM,
        '--dest', dest,
    ])
    wheels = [name for name in os.listdir(dest) if name.endswith('.whl')]
    if len(wheels) != 1:
        raise RuntimeError('expected one Pillow wheel, found %s' % wheels)
    return os.path.join(dest, wheels[0])


def _write_fixture(target):
    sys.path.insert(0, target)
    try:
        from fixture_data import registry_document, write_fixture
    except ImportError:
        shutil.copy(os.path.join(ROOT, 'fixture_data.py'), os.path.join(target, 'fixture_data.py'))
        from fixture_data import registry_document, write_fixture
    fixture_root = os.path.join(target, 'fixtures')
    write_fixture(fixture_root)
    with open(os.path.join(target, 'registry.json'), 'w', encoding='utf-8') as handle:
        json.dump(registry_document(), handle, indent=2)
        handle.write('\n')
    leftover = os.path.join(target, 'fixture_data.py')
    if os.path.exists(leftover):
        os.remove(leftover)
    if target in sys.path:
        sys.path.remove(target)
    for name in list(sys.modules):
        if name in ('fixture_data', 'serve', 'tile_runtime'):
            sys.modules.pop(name, None)


def _strip(target):
    for dirpath, dirnames, filenames in os.walk(target):
        for name in list(dirnames):
            if name == '__pycache__' or name.endswith('.dist-info') and False:
                shutil.rmtree(os.path.join(dirpath, name))
        for name in filenames:
            if name.endswith('.pyc') or name.endswith('.pyo'):
                os.remove(os.path.join(dirpath, name))
            if name in ('direct_url.json', 'RECORD') and dirpath.endswith('.dist-info'):
                os.remove(os.path.join(dirpath, name))
    for dirpath, dirnames, _filenames in os.walk(target, topdown=False):
        for name in dirnames:
            if name == '__pycache__':
                shutil.rmtree(os.path.join(dirpath, name), ignore_errors=True)


def _zip_dir(target, zip_path):
    files = []
    for dirpath, _dirnames, filenames in os.walk(target):
        for name in filenames:
            full = os.path.join(dirpath, name)
            arc = os.path.relpath(full, target).replace(os.sep, '/')
            if arc.startswith('..'):
                continue
            files.append((arc, full))
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for arc, full in sorted(files):
            info = zipfile.ZipInfo(arc)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            if arc.endswith('.so'):
                mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
            else:
                mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            info.external_attr = mode << 16
            with open(full, 'rb') as handle:
                archive.writestr(info, handle.read())


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    dest = os.environ.get('TILE_PYRAMID_ZIP')
    if not dest:
        dest = os.path.join(REPO, 'build', 'geomap-tile-pyramid-test-py312-x86_64.zip')
    manifest = build(dest)
    print(json.dumps(manifest, indent=2))
    print(dest)


if __name__ == '__main__':
    main()
