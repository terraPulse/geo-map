

var _user_name = $.cookie('user_name');

if(_user_name == null || _user_name == ''){
	window.location = 'login.html';
}

function alert_win(txt){
	$('#dlg_alert').html(txt);
	$('#dlg_alert').dialog({
		modal: true, 
		resizable: false,
		// position: 'center',
		buttons: {
			"OK": function() {
				$(this).dialog("close");
			}
		}});

	return;
}

function alert_dlg(txt){
	$('#dlg_alert').html(txt);
	$('#dlg_alert').dialog({
		modal: false, 
		resizable: false,
		// position: 'center',
		buttons: {
			"OK": function() {
				$(this).dialog("close");
			}
		}});

	return;
}

function call(url, ps, func, context){
	_ps = {url:url, type: 'post', data: ps, dataType: 'json'}
	if(typeof context !== 'undefined'){
		_ps['context'] = context
	}

	$.ajax(_ps).done(function(data){
			func(data);
		}).fail(function(data){
			alert_win('Error: ' + data.responseJSON.error.message);
		});
}

function load_image(img, url){
	// $('#div_ndvi_text').html('');

	img.attr('src', '');
	img.attr('src', 'pic/ndvi_loading.png');

	img.attr('src', '');
	img.attr('src', url);

	// img.load(function(){
	// 		img.show();
	// 	});

	img.error(function(){
		img.attr('src', 'pic/ndvi_error.png');
			// var _txt = $('#div_ndvi_text');
			// _txt.html('No data available at the coordinate');
		});
}


function init_controls(){
	/*
	$('#dlg_ndvi').dialog({
		autoOpen: false,
		width: 750,
		height: 480,
		modal: true, 
		resizable: false,
		buttons: {
			"Close": function() {
				$(this).dialog("close");
			}
		}});

	$("#btn_wrs_tile" ).button().click(function(e){
		if(this.checked){
			map_ctrls['tile'].activate();
		}
		else{
			map_ctrls['tile'].deactivate();
		}
	});

	$("#btn_ndvi" ).button().click(function(e){
		if(this.checked){
			map_ctrls['ndvi'].activate();
		}
		else{
			map_ctrls['ndvi'].deactivate();
		}
	});
	*/

	$("#btn_wrs_pixel" ).button().click(function(e){
		if(this.checked){
			map_ctrls['pixel'].activate();
		}
		else{
			map_ctrls['pixel'].deactivate();
		}
	});

	$('#dlg_goto_location').dialog({
		autoOpen: false,
		width: 350,
		modal: false,
		resizable: false,
		buttons: {
			"Zoom To": function(e) {
				var _x = $('#val_goto_location_x').val();
				var _y = $('#val_goto_location_y').val();

				if(!($.isNumeric(_x) && $.isNumeric(_y))){
					alert_win('Please input numberic values')
					return;
				}

				map.put_point(parseFloat(_x), parseFloat(_y), true);
				$(this).dialog("close");
			},
			"Close": function() {
				$(this).dialog("close");
			}
		}});

	$('#btn_goto_location').click(function(){
		$('#dlg_goto_location').dialog('open');
	});
}

$(document).ready(function(){
	init_controls();
	init_map();
}); 
