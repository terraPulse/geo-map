'''Synthetic FIXTURE pyramid. Not a production layer and not a public dataset.'''

import os

from serve import TILE_PX, block_window

LAYER_ID = 'fixture/demo-pyramid'
ORIGIN = (0, 0)
LEVEL = 2
MERGE = 2

# File-index (x, y) -> RGBA. y=0 is the south edge of the block.
QUADRANTS = {
    (0, 0): (220, 20, 20, 255),
    (1, 0): (20, 180, 40, 255),
    (0, 1): (30, 60, 220, 255),
    (1, 1): (230, 200, 20, 255),
}


def registry_document():
    return {
        'adapter': 'geomap.png_pyramid',
        'adapter_version': '1.0.0',
        'layers': [
            {
                'id': LAYER_ID,
                'title': 'FIXTURE synthetic pyramid, not a production layer',
                'fixture': True,
                'storage': 'package',
                'key_prefix': LAYER_ID,
                'version': 2,
                'tile_size': TILE_PX,
                'tile_merge': MERGE,
                'processed_levels': [LEVEL],
                'max_zoom': 6,
            }
        ],
    }


def write_fixture(root):
    '''Write the one stored 512px block under root. Returns the PNG path.'''
    from PIL import Image
    image = Image.new('RGBA', (TILE_PX * MERGE, TILE_PX * MERGE), (0, 0, 0, 0))
    pixels = image.load()
    for dy in range(MERGE):
        for dx in range(MERGE):
            fx = ORIGIN[0] + dx
            fy = ORIGIN[1] + dy
            _bx, _by, box = block_window(LEVEL, fx, fy, MERGE)
            color = QUADRANTS[(fx, fy)]
            for py in range(box[1], box[3]):
                for px in range(box[0], box[2]):
                    pixels[px, py] = color
    directory = os.path.join(root, LAYER_ID, 'tiles', str(LEVEL), str(ORIGIN[0]))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, '%s.png' % ORIGIN[1])
    image.save(path, format='PNG')
    return path
