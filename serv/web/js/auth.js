

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

function user_login(data){
	$.cookie('user_name', data.user_name);
	window.location.href = 'index.html';
}

$(document).ready(function(){
	$('#btn_user_login').click(function(){
			var _ps = {
				'user_name': $('#val_login_user_name').val(),
				'password': $('#val_login_password').val()
				};

			call('/_user/login', _ps, function(data){
					user_login(data);
				});
		});
}); 
