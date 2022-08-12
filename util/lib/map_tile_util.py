
import logging

def add_item_to_list(l, d_out):
    from gio import file_mag
    import os
    
    _f_idx = file_mag.get(os.path.join(d_out, 'list.txt'))
    
    _ls = []
    if _f_idx.exists():
        if str(_f_idx).startswith('s3://'):
            os.remove(_f_idx.get())
    
        with open(_f_idx.get()) as _fi:
            _ls = _fi.read().strip().splitlines()
            
    if l in _ls:
        return False
    
    _ls.append(l)
    logging.info('add %s to %s (%s)' % (l, _f_idx, len(_ls)))
    
    from gio import file_unzip as fz
    with fz.zip() as _zip:
        _zip.save('\n'.join(_ls), str(_f_idx))
        
    return True
    