$(document).ready(function() {
	/* re-enable disabled field so that data is passed during save and 
	   and form validation passes */
	$('input[type="submit"]').click(function() {
		$('form').find(':disabled').each(function() {
			$(this).attr("disabled", false);
		});
		remove_empty_rows()
	});
	
	//auto_add_row()
		
});
auto_add_row()

function auto_add_row() {
	/* auto adds a row to a repeating subform when and empty row is not
	   present */
	$('.repeating-subform').each(function() {
		var subform = $(this);
		test_and_add_new_row(subform);
		$(this).find('.subform-row').find(':input').change(function() {
			test_and_add_new_row(subform);
		});
	});
}

function remove_empty_rows() {
	/* auto adds a row to a repeating subform when and empty row is not
	   present */
	$('.repeating-subform').each(function() {
		var subform = $(this);
		test_and_remove_row(subform);
	});
}

function test_and_remove_row(subform) {
	/* function is called at save time to remove empty rows */
	subform.find('.subform-row').each(function () {
		var empty_row = true;
		$(this).find(':input').each(function () {
			if (!($(this).attr("type"))) {
				type = "ok"
			} else {
				type = $(this).attr("type")
			}
			if (($(this).val()) && (type.indexOf("hidden") == -1)) {
				empty_row = false
			};
		});
		// if the row is empty remove it
		if (empty_row) {
			$(this).remove();
		};
	});
}
		
function test_and_add_new_row(subform) {
	/* function is called when a subform field is changed and auto adds 
	   a new row if an empty row is not present */
	var last_row = subform.find('.subform-row').last()
	var empty_last = true
	// see if the last row is empty
	last_row.find(':input').each(function () {
		if (!($(this).attr("type"))) {
			type = "ok"
		} else {
			type = $(this).attr("type")
		}
			
		var y = $(this).val()
		if (($(this).val()) && (type.indexOf("hidden") == -1)) {
			empty_last = false
		};
	});
	// if last_row is not empty add new row
	if (!(empty_last)) {
		clone_field_row(last_row)
	};
}
			
function clone_field_row(row) {
	/* clones a row passed in and adds after it with wtforms naming 
	   convention */
    var new_element = row.clone(true);
    var elem_id = new_element.find(':input')[0].id;
    var elem_num = parseInt(elem_id.replace(/.*-(\d{1,4})-.*/m, '$1')) + 1;
    if (isNaN(elem_num)) {
    	elem_num = parseInt(elem_id.replace(/.*-(\d{1,4})/m, '$1')) + 1;
    }
    new_element.find(':input').each(function() {
    	var input_val = '';
    	if ($(this).attr("id").indexOf("csrf_token") > -1) {
    		var selector = "#" + $(this).attr('id');
    		input_val = $(selector).val();
    	};
        var id = $(this).attr('id').replace('-' + (elem_num - 1) + '-', '-' + elem_num + '-');
        if (id === elem_id) {
        	id = $(this).attr('id').replace('-' + (elem_num - 1), '-' + elem_num);
        }
        $(this).attr({'name': id, 'id': id}).val(input_val).removeAttr('checked');
    });
    new_element.find('label[for]').each(function() {
        var new_for = $(this).attr('for').replace('-' + (elem_num - 1) + '-', '-' + elem_num + '-');
        $(this).attr('for', new_for);
    });
    row.after(new_element);
}

function mozillaBackpackSender(param, el, btn_falseCss, btn_trueCss) {
	var subjectUriEl = $(el).parent().parent().parent().find("input[id*='subjectUri']");
	var subjectUri = subjectUriEl.val()
	var uid = subjectUriEl.val().replace(/^(.*[#/])/g,"");
	var assertionUrl = el.baseURI.match(/^(.*[#/])/g) + 'api/assertion/' + uid + '.json';
	var csrfVal = $(el).parent().parent().parent().find("input[id*='csrf_token']").val()
	var propUri = $(el).attr("kds_propUri")
	var classUri = $(el).attr("kds_classUri")
	var errorPropUri = $(el).attr("kds_errorLogPropUri")
	var dateStr = new Date().toISOString()
	OpenBadges.issue([assertionUrl], function(errors, successes) {
    	if (errors.length > 0) {
    		var apiUrl = el.baseURI.match(/^(.*[#/])/g) + 'api/form_generic_prop/' + classUri + "/" + errorPropUri + "?id=" + subjectUri;
	    	$(el).removeClass(btn_trueCss).addClass(btn_falseCss).text('Resend')
	    	var errorMsg = dateStr +": " + JSON.stringify(errors)
	    	var errorPost = $.post( apiUrl, { id: subjectUri, dataValue: errorMsg, csrf_token: csrfVal }, function(data) {});
	    	$(el).parent().parent().parent().append("<p class='badgeErrorMsg'>"+errorMsg+"</p>");
    	};
    	if (successes.length > 0 ) {
    		var apiUrl = el.baseURI.match(/^(.*[#/])/g) + 'api/form_generic_prop/' + classUri + "/" + propUri + "?id=" + subjectUri;
	    	$(el).removeClass(btn_falseCss).addClass(btn_trueCss).attr('data',Date()).text('Resend')
	    	var badgePost = $.post( apiUrl, { id: subjectUri, dataValue: dateStr, csrf_token: csrfVal }, function(data) {});
	    	$(el).parent().parent().parent().find(".badgeErrorMsg").remove()
    	}; 	
	});
};

function formFieldLookup(el) {
	var subjectUriEl = $(el).parent().parent().parent().find("input[id*='subjectUri']");
	var subjectUri = subjectUriEl.val()
	var uid = subjectUriEl.val().replace(/^(.*[#/])/g,"");
	var assertionUrl = el.baseURI.match(/^(.*[#/])/g) + 'api/assertion/' + uid + '.json';
	var csrfVal = $(el).parent().parent().parent().find("input[id*='csrf_token']").val()
	var propUri = $(el).attr("kds_propUri")
	var classUri = $(el).attr("kds_classUri")
    var apiUrl = '/badges/api/form_lookup/' + classUri + "/" + propUri;
    var lookupGet = $.get( apiUrl, { id: subjectUri }, function(data) {
		  //alert( "success" );
		});
		  /*.done(function() {
		    alert( "second success" );
		  })
		  .fail(function() {
		    alert( "error" );
		  })
		  .always(function() {
		    alert( "finished" );
		}); */   	

};