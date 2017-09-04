'''
File: create_legend.py
Author: Min Feng
Version: 0.1
Create: 2017-09-03 01:31:44
Description:
'''

def main(opts):
	import PIL

	_img = PIL.Image.new('RGBA', (50, 100))


def usage():
	_p = environ_mag.usage(False)

	# _p.add_argument('-i', '--input', dest='input', required=True)
	# _p.add_argument('-o', '--output', dest='output', required=True)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

