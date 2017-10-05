
import logging
import webapp2

class service_base:
	def __init__(self, request):
		self.request = request

	def pp(self, tag, d=None):
		if tag not in self.request.values:
			raise Exception('not found parameter %s' % tag)

		_t = self.request.values[tag]
		return _t.strip() if (_t != None and _t.strip()) else d

	def pf(self, tag, d=None):
		_t = self.pp(tag)
		return d if _t == None else float(_t)

	def get(self, *arg):
		return self.__task(*arg)

	def post(self, *arg):
		return self.__task(*arg)

	def __task(self, *arg):
		return self.task(*arg)

	def task(self, *arg):
		raise NotImplementedError()

	def output_html(self, txt):
		from flask import make_response
		_resp = make_response(txt)
		_resp.headers['Content-Type'] = 'text/html; charset=utf-8'

		return _resp

	def output_json(self, obj):
		import json
		import model_data

		from flask import make_response
		_text = json.dumps(obj, default=model_data.convert_to_builtin_type,
				indent=2, ensure_ascii=False, sort_keys=True)
		_resp = make_response(_text)
		_resp.headers['Content-Type'] = 'text/html; charset=utf-8'

		return _resp

	def output_file(self, f, attachment=False):
		import flask
		return flask.send_file(f, as_attachment=attachment)

	def output_byte(self, f, b, attachment=False):
		from flask import make_response
		import mimetypes
		import os

		_resp = make_response(b)

		_context = mimetypes.guess_type(f)[0]
		if _context is None:
			_context = 'application/octet-stream'

		_resp.headers['Content-Type'] = _context
		_type = 'inline' if (not attachment) else 'attachment'
		_resp.headers['Content-Disposition'] = '%s; filename=%s' % (_type, os.path.basename(f))

		return _resp

	def handle_exception(self, exception, debug):
		import traceback

		logging.error(traceback.format_exc())
		logging.error(str(exception))
		print '\n\n* Error:', traceback.format_exc()

		_json = {'message': str(exception.message)}
		if isinstance(exception, webapp2.HTTPException):

			_json['code'] = exception.code
		else:
			self.response.set_status(500)
			_json['code'] = 500

		return self.output_json({'error': _json})

