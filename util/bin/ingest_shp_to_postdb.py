#!/usr/bin/env python
# -*- coding: utf-8 -*-

def shp_to_psql(f_shp, con, tag):
    from gio import config
    from gio import file_mag
    
    _shp = file_mag.get(f_shp).get()
    if not _shp:
        raise Exception('failed to get the input shapefile')
        
    _cmd = ("ogr2ogr -f 'PostgreSQL' '%s' '%s' -lco GEOMETRY_NAME=geom " \
            + "-lco FID=gid -lco PRECISION=no -nlt GEOMETRY -nln %s -overwrite") \
            % (con, _shp, tag)
            
    return _cmd

def main(opts):
    from gio import run_commands
    from gio import file_unzip
    from gio import file_mag
    from gio import config
    
    _con = config.get('conf', 'pg', 'PG:host=tpdb01.cluster-compweaqr5k6.us-east-1.rds.amazonaws.com user=tpgis dbname=tpgisdb password=Tpg!$u$3r')
    _cmd = shp_to_psql(opts.input, _con, opts.tag)
    run_commands.run(_cmd)
    # print(_cmd)
    
    # _cmd = 'shp2pgsql -I -s %s %s %s' % (opts.projection, file_mag.get(opts.input).get(), opts.layer)
    # print(_cmd)
    # _rss = run_commands.run(_cmd)
    
    # with file_unzip.zip() as _zip:
    #     _zip.save(_rss[1], opts.output)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input', required=True)
    # _p.add_argument('-p', '--projection', dest='projection', required=True, type=int)
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-o', '--output', dest='output')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
