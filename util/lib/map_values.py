
def change_prob(v):
    if v is None:
        return None
        
    return round(v, 1)
    
def ndvi(v):
    if v is None:
        return None
        
    if v < -1000:
        return None
        
    return v / 1000.0

def forest_loss(v):
    if v is None:
        return None
        
    if v >= 100:
        return None
    
    return 1970 + v
    
def forest_gain(v):
    if v is None:
        return None
        
    if v >= 100:
        return None
    
    return 1970 + v
    
def forest_esta(v):
    if v is None:
        return None
        
    if v == 100:
        return 'non-forest' 
        
    if v == 0:
        return 1970
    
    return 1970 + v
    
def forest_age(v):
    if v is None:
        return None
        
    if v >= 100:
        return None
        
    if v == 50:
        return '>=50' 
        
    return v
    
def naip_lc(v):
    if v == 1:
        return 'shadow'
    if v == 2:
        return 'water'
    if v == 3:
        return 'bare'
    if v == 4:
        return 'herbaceous'
    if v == 5:
        return 'tree'
    if v == 6:
        return 'paved'
    if v == 7:
        return 'building'
    return None
    
def tcc(v):
    if v <= 100:
        return v
    
    if v == 200:
        return 'water'
        
    if v == 210:
        return 'cloud'
        
    if v == 211:
        return 'shadow'
        
    return None
    
def cdl(v):
    if not v:
        return v
        
    from gio import file_mag
    import pandas
    
    _r = pandas.read_csv(file_mag.get('s3://geo-dataset/cdl/cld2019_values.csv').get())
    _s = _r.loc[_r['VALUE'] == v, 'CLASS_NAME']
    
    if len(_s) == 0:
        return None

    return _s.iloc[0]

def map_value(tag, v):
    if not tag:
        return v
        
    if tag == 'change_prob':
        return change_prob(v)
        
    if tag == 'forest_loss':
        return forest_loss(v)
        
    if tag == 'forest_gain':
        return forest_gain(v)
        
    if tag == 'forest_esta':
        return forest_esta(v)
        
    if tag == 'forest_age':
        return forest_age(v)
        
    if tag == 'tcc':
        return tcc(v)
        
    if tag == 'cdl':
        return cdl(v)
        
    if tag == 'ndvi':
        return ndvi(v)
        
    if tag == 'naip/lc':
        return naip_lc(v)
        
    return v
    
def parse_tag(t, tag, f):
    if tag:
        return tag.lower().strip()
        
    _t = t.lower().strip()
    
    if 'forest_' in _t and '_prob' in _t:
        return 'change_prob'
        
    if 'forest_loss' in _t:
        return 'forest_loss'
        
    if 'forest_gain' in _t:
        return 'forest_gain'
        
    if 'forest_esta' in _t:
        return 'forest_esta'
        
    if 'forest_age' in _t:
        return 'forest_age'
        
    if 'naip/lc' in _t:
        return 'naip/lc'
        
    if 'tcc' in _t:
        return 'tcc'
        
    if 'cdl' in _t:
        return 'cdl'
        
    if 'idx' not in _t and ('ndvi' in _t or 'ndsi' in _t or 'ndwi' in _t):
        return 'ndvi'
        
    return None
    
def text(t, tag, f, v):
    _v = map_value(parse_tag(t, tag, f), v)
    
    if _v is None:
        return '-'
        
    return _v

def categories(t, tag, f, cs):
    if cs is None:
        return None
        
    _tag = parse_tag(t, tag, f)
    
    if _tag == 'tcc':
        _cs = {}
        for _v in range(101):
            _cs[_v] = cs.get(_v, 0)
        return _cs
    
    return cs
            
        
    