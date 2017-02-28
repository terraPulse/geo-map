
var map;
var mapBounds = new OpenLayers.Bounds(-180.000000, -82.640100, 180.000000, 81.855500);
// var mapBounds = new OpenLayers.Bounds(27.497144, -16.299964, 30.591724, -14.141325);
// var mapBounds = new OpenLayers.Bounds(21.201199, -18.188537, 34.882154, -7.936012);

var mapMinZoom = 6;
var mapMaxZoom = 16;
var emptyTileURL = "http://www.maptiler.org/img/none.png";
OpenLayers.IMAGE_RELOAD_ATTEMPTS = 3;

var map_ctrls = {};

function create_layer(id, title){
	return new OpenLayers.Layer.TMS(title, "",
		{
			serviceVersion: id,
			layername: '.',
			alpha: true,
			type: 'png',
			visibility: false,
			isBaseLayer: false,
			getURL: getURL
		});

}

var style = new OpenLayers.Style({
	// fillColor: "#ffcc6600",
	fillOpacity: 0,
	strokeColor: "#ff9933",
	strokeWidth: 1,
	fontSize: '12px',
	fontColor: "#ff9933",
	fontFamily: "sans-serif",
	// fontWeight: "bold"
}, {
	rules: [
		new OpenLayers.Rule({
			maxScaleDenominator: 1000000,
			symbolizer: {
				label: "${TAG}",
				fontSize: "12px"
			}
		}),
		new OpenLayers.Rule({
			minScaleDenominator: 1000000,
			maxScaleDenominator: 10000000,
			symbolizer: {
				label: ""
			}
		})
	]
});

function create_json_layer(path, title, col, min_res){
	// var vectorLayer = new OpenLayers.layer.Vector({
	// source: new OpenLayers.source.Vector({
	//   url: path,
	//   format: new OpenLayers.format.GeoJSON()
	// }),
	// style: function(feature, resolution) {
	//   style.getText().setText(resolution < min_res ? feature.get(col) : '');
	//   return style;
	// }
	// });

	// return new OpenLayers.Layer.Vector(title, {
	// 	styleMap: new OpenLayers.StyleMap(style),
	// 	projection: map.displayProjection,
	// 	strategies: [new OpenLayers.Strategy.Fixed()],
	// 	protocol: new OpenLayers.Protocol.HTTP({
	// 		url: path,
	// 		format: new OpenLayers.Format.KML({
	// 			extractStyles: true, 
	// 			extractAttributes: true,
	// 			maxDepth: 2
	// 		})
	// 	})
	// });

	return new OpenLayers.Layer.Vector(title, {
		projection: map.displayProjection,
		styleMap: new OpenLayers.StyleMap(style),
		strategies: [new OpenLayers.Strategy.Fixed()],
		protocol: new OpenLayers.Protocol.HTTP({
			url: path,
			format: new OpenLayers.Format.GeoJSON()
		})
	});
}

function init(){
	var options = {
		div: "map",
		controls: [],
		projection: "EPSG:3857",
		displayProjection: new OpenLayers.Projection("EPSG:4326"),
		numZoomLevels: mapMaxZoom
	};
	map = new OpenLayers.Map(options);

	var gsat = new OpenLayers.Layer.Google("Google Satellite",
		{
			type: google.maps.MapTypeId.SATELLITE,
			sphericalMercator: true
		});
	var ghyb = new OpenLayers.Layer.Google("Google Hybrid",
		{
			type: google.maps.MapTypeId.HYBRID,
			sphericalMercator: true
		});
	var gter = new OpenLayers.Layer.Google("Google Terrain",
		{
			type: google.maps.MapTypeId.TERRAIN,
			sphericalMercator: true
		});

	// Create OSM layer
	var osm = new OpenLayers.Layer.OSM("OpenStreetMap");

	// create TMS Overlay layer
	map.addLayers([gsat, ghyb, gter, osm]);

	// map.addLayer(create_layer('/map/zambia_01', 'Zambia 01'));
	// map.addLayer(create_layer('/map/crop03', 'Crop 03'));
	// map.addLayer(create_layer('/map/crop04', 'Crop 04'));
	// map.addLayer(create_layer('/map/crop09', 'Crop 09'));
	// map.addLayer(create_layer('/map/crop10/2014', 'Crop 10 - 2014'));
	// map.addLayer(create_layer('/map/crop10/2015', 'Crop 10 - 2015'));
	// map.addLayer(create_layer('/map/crop10/2016', 'Crop 10 - 2016'));
	// map.addLayer(create_layer('/map/crop20/2014', 'Crop 20 - 2014'));
	// map.addLayer(create_layer('/map/crop20/2015', 'Crop 20 - 2015'));
	// map.addLayer(create_layer('/map/crop20/2016', 'Crop 20 - 2016'));
	//
	// map.addLayer(create_layer('/map/sf_s1', 'Wheat Season'));
	// map.addLayer(create_layer('/map/sf_s2', 'Maize Season'));
	// map.addLayer(create_layer('/map/sf_s1_maize', 'Wheat'));
	// map.addLayer(create_layer('/map/sf_s2_maize', 'Maize'));

	/*
	map.addLayer(create_layer('/map/sf_s1_wheat_flds', 'South Africa Wheat Flds'));
	map.addLayer(create_layer('/map/sf_s2_maize_flds', 'South Africa Maize Flds'));

	map.addLayer(create_layer('/map/sf_s1_wheat_flds2', 'South Africa Wheat Flds (v2)'));
	map.addLayer(create_layer('/map/sf_s2_maize_flds2', 'South Africa Maize Flds (v2)'));

	map.addLayer(create_layer('/map/crop20/2014', 'Zambia Maize 2014 v1.0'));
	map.addLayer(create_layer('/map/crop20/2015', 'Zambia Maize 2015 v1.0'));
	map.addLayer(create_layer('/map/crop20/2016', 'Zambia Maize 2016 v1.0'));
	map.addLayer(create_layer('/map/zambia_s2_maize_v2.01', 'Zambia Maize 2016 v2.01'));
	map.addLayer(create_layer('/map/zambia_s2_maize_v2.26', 'Zambia Maize 2016 v2.26'));
	map.addLayer(create_layer('/map/zambia_s2_maize_v2.50', 'Zambia Maize 2016 v2.50'));
	map.addLayer(create_layer('/map/mozambique_crop02_01', 'mozambique_crop02_01'));

	map.addLayer(create_json_layer('/map/zambia_tiles.json', 'Zambia Tiles'));
	*/

	// map.addLayer(create_layer('/map/hungary_01', 'Hungary v0.01'));
	map.addLayer(create_layer('/map/hungary_02', 'Hungary v0.2'));
	map.addLayer(create_json_layer('/map/tiles_hungary.json', 'Hungary tiles'));

	map.addLayer(create_layer('/map/south_africa_wheat01', 'South Africa v1.0'));
	map.addLayer(create_layer('/map/south_africa_wheat02', 'South Africa v2.0'));
	map.addLayer(create_layer('/map/zimbabwe_s2_crop02', 'Zimbabwi v0.9'));


	var switcherControl = new OpenLayers.Control.LayerSwitcher();
	map.addControl(switcherControl);
	switcherControl.maximizeControl();

	map.zoomToExtent(mapBounds.transform(map.displayProjection, map.projection));

	map.addControls([new OpenLayers.Control.PanZoomBar(),
		new OpenLayers.Control.Navigation(),
		new OpenLayers.Control.MousePosition()]);

	/*
  map.addControls([new OpenLayers.Control.PanZoomBar(),
				   new OpenLayers.Control.Navigation(),
				   new OpenLayers.Control.MousePosition(),
				   new OpenLayers.Control.ArgParser(),
				   new OpenLayers.Control.Attribution()]);

*/

	var _ndvi = new OpenLayers.Control.NDVIClick();
	map.addControl(_ndvi);
	map_ctrls['ndvi'] = _ndvi;

	var _tile = new OpenLayers.Control.TileClick();
	map.addControl(_tile);
	map_ctrls['tile'] = _tile;

	var _pixel = new OpenLayers.Control.PixelClick();
	map.addControl(_pixel);
	map_ctrls['pixel'] = _pixel;
}

function getURL(bounds) {
	bounds = this.adjustBounds(bounds);
	var res = this.getServerResolution();
	var x = Math.round((bounds.left - this.tileOrigin.lon) / (res * this.tileSize.w));
	var y = Math.round((bounds.bottom - this.tileOrigin.lat) / (res * this.tileSize.h));
	var z = this.getServerZoom();
	if (this.map.baseLayer.CLASS_NAME === 'OpenLayers.Layer.Bing') {
		z+=1;
	}
	var path = this.serviceVersion + "/" + this.layername + "/" + z + "/" + x + "/" + y + "." + this.type; 
	var url = this.url;
	if (OpenLayers.Util.isArray(url)) {
		url = this.selectUrl(path, url);
	}
	if (mapBounds.intersectsBounds(bounds) && (z >= mapMinZoom) && (z <= mapMaxZoom)) {
		return url + path;
	} else {
		return emptyTileURL;
	}
} 

function getWindowHeight() {
	if (self.innerHeight) return self.innerHeight;
	if (document.documentElement && document.documentElement.clientHeight)
		return document.documentElement.clientHeight;
	if (document.body) return document.body.clientHeight;
	return 0;
}

function getWindowWidth() {
	if (self.innerWidth) return self.innerWidth;
	if (document.documentElement && document.documentElement.clientWidth)
		return document.documentElement.clientWidth;
	if (document.body) return document.body.clientWidth;
	return 0;
}

function resize() {  
	var map = document.getElementById("map");  
	var header = document.getElementById("header");  
	var subheader = document.getElementById("subheader");  
	map.style.height = (getWindowHeight()-80) + "px";
	map.style.width = (getWindowWidth()-20) + "px";
	header.style.width = (getWindowWidth()-20) + "px";
	subheader.style.width = (getWindowWidth()-20) + "px";
	if (map.updateSize) { map.updateSize(); };
}

onresize=function(){ resize(); };

