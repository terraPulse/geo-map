'''Read stored PNG bytes from the package fixture tree or one S3 prefix.

The bucket and prefix come from the environment. Callers pass a relative
key that already passed is_safe_relative_path.
'''

import os

from tile_runtime import get_cache, is_safe_relative_path


class ReaderError(Exception):
    pass


class PackageReader:
    def __init__(self, root):
        self.root = root

    def get_bytes(self, relative):
        path = _local_path(self.root, relative)
        if path is None:
            raise ReaderError('rejected key')
        cache = get_cache()

        def load():
            cache.note_stat()
            if not os.path.isfile(path):
                return None
            with open(path, 'rb') as handle:
                data = handle.read()
            cache.note_get(len(data))
            return data

        return 'pkg:' + relative, cache.get_or_load_bytes('pkg:' + relative, load)


class S3Reader:
    '''One boto3 client per process. GetObject only; no ListBucket.'''

    def __init__(self, bucket, key_root, client=None):
        if not bucket or '/' in bucket or bucket.startswith('.'):
            raise ReaderError('TILE_BUCKET is not configured')
        root = (key_root or '').strip('/')
        if root and not _prefix_ok(root):
            raise ReaderError('TILE_KEY_ROOT is not allowed')
        self.bucket = bucket
        self.key_root = root
        self._client = client

    def get_bytes(self, relative):
        key = _s3_key(self.key_root, relative)
        if key is None:
            raise ReaderError('rejected key')
        cache = get_cache()

        def load():
            cache.note_stat()
            try:
                response = self.client().get_object(Bucket=self.bucket, Key=key)
            except Exception as exc:
                code = getattr(exc, 'response', {}).get('Error', {}).get('Code', '')
                if code in ('NoSuchKey', '404', 'NotFound', 'NoSuchBucket'):
                    return None
                raise
            body = response['Body'].read()
            cache.note_get(len(body))
            return body

        cache_key = 's3:' + self.bucket + '/' + key
        return cache_key, cache.get_or_load_bytes(cache_key, load)

    def client(self):
        if self._client is not None:
            return self._client
        import boto3
        from botocore.config import Config
        self._client = boto3.client(
            's3',
            config=Config(
                connect_timeout=2,
                read_timeout=5,
                retries={'max_attempts': 2},
            ),
        )
        return self._client


def _prefix_ok(prefix):
    if prefix.startswith('/') or prefix.startswith('s3:') or '\\' in prefix or '..' in prefix.split('/'):
        return False
    return True


def _s3_key(root, relative):
    if not is_safe_relative_path(relative):
        return None
    if root:
        key = root.rstrip('/') + '/' + relative
        if not key.startswith(root.rstrip('/') + '/'):
            return None
    else:
        key = relative
    if '..' in key.split('/'):
        return None
    return key


def _local_path(root, relative):
    if not is_safe_relative_path(relative):
        return None
    root_abs = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root_abs, relative))
    if path != root_abs and not path.startswith(root_abs + os.sep):
        return None
    return path
