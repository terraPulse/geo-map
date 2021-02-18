'''
File: generate_map_list.py
Author: Min Feng
Version: 0.1
Create: 2019-09-03 01:39:15
Description:
'''

def _list_maps(d, ds):
    import os
    import re
    import logging
    
    if not os.path.exists(d):
        return

    for _d in os.listdir(d):
        logging.info('checking %s' % os.path.join(d, _d))
        
        if not os.path.isdir(os.path.join(d, _d)):
            continue

        # if re.match('^\d+$', _d):
        #     continue

        if _d.startswith('.') or _d.startswith('_'):
            continue

        _f = os.path.join(d, _d, 'setting.ini')
        if os.path.exists(_f):
            ds.append(os.path.join(d, _d))
            continue

        _f = os.path.join(d, _d, 'tiles')
        if os.path.exists(_f) and os.path.isdir(_f):
            continue
        
        _f = os.path.join(d, _d, 'tasks.txt')
        if os.path.exists(_f):
            continue
        
        _list_maps(os.path.join(d, _d), ds)
        
def _format_dir(d, root):
    import os
    
    _root = root
    if not _root.endswith(os.path.sep):
        _root = _root + os.path.sep
    
    return d[len(_root): ]
            
def main(opts):
    from gio import config
    from gio import file_mag
    import os
    import logging
    
    _d_out = config.get('conf', 'output')
    if not _d_out.startswith('s3://'):
        _d_out = os.path.abspath(_d_out)

    _ms = []
    
    _list_maps(_d_out, _ms)
    _ms = [_format_dir(_m, _d_out) for _m in _ms]
    
    _f_out = os.path.join(_d_out, 'list.txt')
    
    print('found %s maps' % len(_ms))
    print('save map list to %s' % _f_out)
    
    logging.info('found %s maps' % len(_ms))
    logging.info('save map list to %s' % _f_out)
    
    from gio import file_unzip
    with file_unzip.zip() as _zip:
        _zip.save('\n'.join(_ms), _f_out)

def usage():
    _p = environ_mag.usage(False)

    _p.add_argument('-o', '--output', dest='output')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
