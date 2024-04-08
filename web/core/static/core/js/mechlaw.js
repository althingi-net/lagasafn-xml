var quick_see = function(content, $anchor) {
    var $dialog = $('.quick-dialog');

    // Set the dialog content. Must happen before position is set.
    $dialog.find('div.quick-dialog-content').html(content);

    // Calculate positioning. The dialog's surface should always be contained
    // within the container.
    var $container = $anchor.closest('law');
    var min_left = $container.offset().left;
    var max_left = $container.width() + min_left - $dialog.width();
    var max_top = document.documentElement.scrollHeight - $dialog.height();

    var dialog_left = $anchor.offset().left + ($anchor.width() / 2) - ($dialog.width() / 2);
    var dialog_top = $anchor.offset().top;

    if (dialog_left < min_left) {
        dialog_left = min_left;
    }
    if (dialog_left > max_left) {
        dialog_left = max_left;
    }
    if (dialog_top > max_top) {
        dialog_top = max_top;
    }

    // Set the dialog's location.
    $dialog.css('left', String(dialog_left) + 'px');
    $dialog.css('top', String(dialog_top) + 'px');

    // Show the dialog.
    $dialog.show();

    // Activate refer-events on content in dialog.
    $dialog.find('refer').on('mouseenter', follow_refer);
}

// Functions for scrolling up/down by only one pixel. Used from console.
var down = function() {
    $(window).scrollTop($(window).scrollTop()+1);
}
var up = function() {
    $(window).scrollTop($(window).scrollTop()-1);
}

$(document).ready(function() {
    $('.quick-dialog').on('mouseleave', function() { $(this).hide(); });
});

