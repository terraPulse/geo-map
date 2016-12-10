import numpy as np
cimport numpy as np
cimport cython

@cython.boundscheck(False)
@cython.wraparound(False)

def update(dat, idx, ref):
	if dat.dtype == np.uint8:
		return update_uint8(dat, idx, ref)

	if dat.dtype == np.float32:
		return update_float(dat, idx, ref)

	if dat.dtype == np.int16:
		return update_int16(dat, idx, ref)

	raise Exception('unsupported data type')

def update_uint8(np.ndarray[np.uint8_t, ndim=2] dat, np.ndarray[np.uint8_t, ndim=2, cast=True] idx, \
		np.ndarray[np.uint8_t, ndim=2] ref):
	cdef int _rows = dat.shape[0]
	cdef int _cols = dat.shape[1]
	cdef int _row, _col, _i
	cdef int _v, _r

	for _row in xrange(_rows):
		for _col in xrange(_cols):
			_i = idx[_row, _col]

			if _i > 0:
				dat[_row, _col] = ref[_row, _col]

def update_float(np.ndarray[np.float32_t, ndim=2] dat, np.ndarray[np.uint8_t, ndim=2, cast=True] idx, \
		np.ndarray[np.float32_t, ndim=2] ref):
	cdef int _rows = dat.shape[0]
	cdef int _cols = dat.shape[1]
	cdef int _row, _col, _i
	cdef float _v, _r

	for _row in xrange(_rows):
		for _col in xrange(_cols):
			_i = idx[_row, _col]

			if _i > 0:
				dat[_row, _col] = ref[_row, _col]

def update_int16(np.ndarray[np.int16_t, ndim=2] dat, np.ndarray[np.uint8_t, ndim=2, cast=True] idx, \
		np.ndarray[np.int16_t, ndim=2] ref):
	cdef int _rows = dat.shape[0]
	cdef int _cols = dat.shape[1]
	cdef int _row, _col, _i
	cdef int _v, _r

	for _row in xrange(_rows):
		for _col in xrange(_cols):
			_i = idx[_row, _col]

			if _i > 0:
				dat[_row, _col] = ref[_row, _col]

