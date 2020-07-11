
def main(opts):
    
    from gio import run_commands
    from gio import file_unzip
    from gio import file_mag
    
    _cmd = 'shp2pgsql -I -s %s %s %s' % (opts.projection, file_mag.get(opts.input).get(), opts.layer)
    print(_cmd)
    _rss = run_commands.run(_cmd)
    
    with file_unzip.zip() as _zip:
        _zip.save(_rss[1], opts.output)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input', required=True)
    _p.add_argument('-p', '--projection', dest='projection', required=True, type=int)
    _p.add_argument('-l', '--layer', dest='layer', required=True)
    _p.add_argument('-o', '--output', dest='output', required=True)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
