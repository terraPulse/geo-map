
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
        
    if tag == 'forest_loss':
        return forest_loss(v)
        
    if tag == 'forest_gain':
        return forest_gain(v)
        
    if tag == 'forest_esta':
        return forest_esta(v)
        
    if tag == 'tcc':
        return tcc(v)
        
    if tag == 'cdl':
        return cdl(v)
        
    if tag == 'ndvi':
        return ndvi(v)
        
    return v
    
def parse_tag(t, tag, f):
    if tag:
        return tag.lower().strip()
        
    _t = t.lower().strip()
    
    if 'forest_loss' in t:
        return 'forest_loss'
        
    if 'forest_gain' in t:
        return 'forest_gain'
        
    if 'forest_esta' in t:
        return 'forest_esta'
        
    if 'tcc' in t:
        return 'tcc'
        
    if 'cdl' in t:
        return 'cdl'
        
    if 'ndvi' in t or 'ndsi' in t or 'ndwi' in t:
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
            
        
    