
function show_tile(loc){
	$('#dlg_tile').dialog('open');

	call('/_tile', {x: loc.lon, y: loc.lat}, function(data){
		alert_dlg(data.join(', '));
	});
}

OpenLayers.Control.TileClick = OpenLayers.Class(OpenLayers.Control, {                
	defaultHandlerOptions: {
		'single': true,
		'double': false,
		'pixelTolerance': 0,
		'stopSingle': false,
		'stopDouble': false
	},

	initialize: function(options) {
		this.handlerOptions = OpenLayers.Util.extend(
			{}, this.defaultHandlerOptions
		);
		OpenLayers.Control.prototype.initialize.apply(
			this, arguments
		); 
		this.handler = new OpenLayers.Handler.Click(
			this, {
				'click': this.trigger
			}, this.handlerOptions
		);
	}, 

	trigger: function(e) {
		var _loc = map.getLonLatFromPixel(e.xy);
		_loc.transform(map.projection, map.displayProjection);

		show_tile(_loc);
		// var _url = 'http://glcfdev04.umd.edu:18080/_ndvi?y=' + _loc.lat + '&x=' + _loc.lon;
		// window.open(_url, '_blank')
	}

});

function show_pixel(loc){
	// $('#dlg_tile').dialog('open');

	// call('/_pixel', {x: loc.lon, y: loc.lat}, function(data){
	// 	alert_dlg(data);
	// });
	//
	// alert_win('Coordiniate: ' + loc.lon.toFixed(4) + ', ' + loc.lat.toFixed(4));
	//
	var _x = loc.lon.toFixed(5);
	var _y = loc.lat.toFixed(5);

	$('#val_goto_location_x').val(_x);
	$('#val_goto_location_y').val(_y);

	map.put_point(_x, _y);
	$('#dlg_goto_location').dialog('open');
}

OpenLayers.Control.PixelClick = OpenLayers.Class(OpenLayers.Control, {
	defaultHandlerOptions: {
		'single': true,
		'double': false,
		'pixelTolerance': 0,
		'stopSingle': false,
		'stopDouble': false
	},

	initialize: function(options) {
		this.handlerOptions = OpenLayers.Util.extend(
			{}, this.defaultHandlerOptions
		);
		OpenLayers.Control.prototype.initialize.apply(
			this, arguments
		); 
		this.handler = new OpenLayers.Handler.Click(
			this, {
				'click': this.trigger
			}, this.handlerOptions
		);
	}, 

	trigger: function(e) {
		var _loc = map.getLonLatFromPixel(e.xy);
		_loc.transform(map.projection, map.displayProjection);

		show_pixel(_loc);
	}

});
function show_ndvi(loc){
	$('#dlg_ndvi').dialog('open');

	var _url = 'http://glcfdev04.umd.edu:18080/_ndvi?y=' + loc.lat + '&x=' + loc.lon;
	load_image($('#img_ndvi'), _url);
}

OpenLayers.Control.NDVIClick = OpenLayers.Class(OpenLayers.Control, {                
	defaultHandlerOptions: {
		'single': true,
		'double': false,
		'pixelTolerance': 0,
		'stopSingle': false,
		'stopDouble': false
	},

	initialize: function(options) {
		this.handlerOptions = OpenLayers.Util.extend(
			{}, this.defaultHandlerOptions
		);
		OpenLayers.Control.prototype.initialize.apply(
			this, arguments
		); 
		this.handler = new OpenLayers.Handler.Click(
			this, {
				'click': this.trigger
			}, this.handlerOptions
		);
	}, 

	trigger: function(e) {
		var _loc = map.getLonLatFromPixel(e.xy);
		_loc.transform(map.projection, map.displayProjection);

		show_ndvi(_loc);
		// var _url = 'http://glcfdev04.umd.edu:18080/_ndvi?y=' + _loc.lat + '&x=' + _loc.lon;
		// window.open(_url, '_blank')
	}

});

