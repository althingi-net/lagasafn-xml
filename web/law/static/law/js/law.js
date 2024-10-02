
// We have the choice between hard-coding these paths or leaving them in a
// template decoupled from this file. We'll hard-code, for now at least.
var IMG_BOX_WHITE = '/static/law/img/box-white.png';
var IMG_BOX_BLACK = '/static/law/img/box-black.png';

function lowercase_tagname(element) {
    if (element.prop('tagName') == undefined) {
        return '';
    }
    return element.prop('tagName').toLowerCase();
}

// FIXME: Seems like a stale debug thing. Remove or utilize and comment.
//function location_to_string($location) {
//    var location_string = '';
//    $location.children().each(function() {
//        var $child = $(this);
//        location_string += lowercase_tagname($child) + ' ' + $child.text() + ' ';
//    });
//    return location_string.trim();
//}

// Encapsulating function for making XPath queries less messy.
function getElementByXPath(xpath, contextNode = document) {
    return document.evaluate(xpath, contextNode, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
}

function attr_or_emptystring(element, attribute) {
    if (!element) {
        return '';
    }
    if (element.attr(attribute) == undefined) {
        return '';
    }
    return element.attr(attribute);
}

// Entry function for references, merely for code organizational reasons.
var follow_refer = function() {
    var $refer = $(this);

    var refer_type = $refer.attr('type');
    if (!refer_type) {
        refer_type = 'legal-clause';
    }

    if (refer_type == 'legal-clause') {
        process_refer_legal_clause($refer);
    }
    else if (refer_type == 'legal-clause-from-text') {
        process_refer_legal_clause_from_text($refer.text(), $refer);
    }
    else if (refer_type == 'law') {
        // Temporarily using process_refer_external, as opposed to its own
        // process_refer_law function. Processing will almost certainly been
        // done differently between these types, but for the timebeing they
        // are identical. It makes sense to make a semantic distinction
        // between them, though.
        process_refer_external($refer);
    }
    else if (refer_type == 'external') {
        process_refer_external($refer);
    }
}

var process_refer_legal_clause_from_text = function(text, $refer) {
    // Construct URL.
    let url = "/api/law/parse-reference/";
    url += "?reference=" + encodeURI(text);

    // Get data.
    fetch(url).then((response) => {
        return response.json();
    }).then((data) => {
        if (data.segment) {

            let $content = "";
            data.segment.xml_result.map((clause) => {
                $content += clause;
            });

            quick_see($content, $refer);
            return;
        }

        // Something went wrong at this point.
        let error_msg = "Unknown error";  // Default.
        if (data.detail) {
            // Yay! We might know what's wrong!
            error_msg = data.detail;
        }

        // Log error for developer.
        console.error("Remote error:", error_msg);

        // Display error to user.
        let $error = $('<p class="alert alert-danger">' + error_msg + '</p>');
        quick_see($error, $refer);

    }).catch((error) => {
        console.error(error);
    });
}

// Process a reference that refers to a legal clause in Icelandic law.
var process_refer_legal_clause = function($refer) {

    var supported_tags = ['art', 'subart', 'numart'];

    // Construct search string as CSS selector.
    var search_string = '';
    for (i in supported_tags) {
        var tag = supported_tags[i]
        var value = $refer.attr(tag);

        if (value) {
            // If the value contains "-", then we're looking for a range, like
            // "1-4". For example, if we're looking for subarticles 1-3 in
            // article 7, we need to expand the search string such that it
            // becomes:
            //     art[nr="7"] subart[nr="1"],art[nr="7"] subart[nr="2"]
            //
            // It is assumed that this only occurs at the deepest level of the
            // search. We cannot find subarticle 5 in articles 1-3, but we can
            // find subarticle 1-3 within article 5. It is currently assumed
            // that all legal text is compatible with this restriction.
            var minus_index = value.indexOf('-');
            if (minus_index > -1) {
                var first_value = parseInt(value.substring(0, minus_index));
                var last_value = parseInt(value.substring(minus_index + 1));

                // Keep a base of the search string compiled so far.
                var current_search_string = search_string;

                // Start with a clean slate for the total search string. What
                // has already been gathered is kept in current_search_string.
                // This variable can be thought of as the "result" variable,
                // eventually containing a comma-separated list of search
                // strings that will be used to find the content we need.
                search_string = '';

                // Compile a new search string for every value that we want to
                // find, and add to the total search string.
                for (var value = first_value; value <= last_value; value++) {
                    search_string += ',' + current_search_string + ' ' + tag + '[nr="' + value + '"]';
                }

                // Trim the comma from the first iteration, since commas
                // should only be between the things we want to find.
                search_string = search_string.replace(/^,/, '');
            }
            else {
                search_string += ' ' + tag + '[nr="' + value + '"]';
            }
        }
    }
    search_string = search_string.trim();

    // Construct URL.
    let url = "/api/law/segment/";
    url += "?law_nr=" + $refer.attr("law-nr");
    url += "&law_year=" + $refer.attr("law-year");
    url += "&css_selector=" + encodeURI(search_string);

    // Get data.
    fetch(url).then((response) => {
        return response.json();
    }).then((data) => {
        if (data.segment) {

            let $content = "";
            data.segment.xml_result.map((clause) => {
                $content += clause;
            });

            quick_see($content, $refer);
            return;
        }

        // Something went wrong at this point.
        let error_msg = "Unknown error";  // Default.
        if (data.detail) {
            // Yay! We might know what's wrong!
            error_msg = data.detail;
        }

        // Log error for developer.
        console.error("Remote error:", error_msg);

        // Display error to user.
        let $error = $('<p class="alert alert-danger">' + error_msg + '</p>');
        quick_see($error, $refer);

    }).catch((error) => {
        console.error(error);
    });
}


// Process a reference to an external location of some sort.
var process_refer_external = function($refer) {
    var href = $refer.attr('href');
    var name = $refer.attr('name');
    if (!name) {
        name = href;
    }
    quick_see('<a target="_blank" href="' + href + '">' + name + '</a>', $refer);
}


var process_footnote = function() {

    var $footnote = $(this);

    var footnote_nr = $footnote.attr('nr');

    // Go through footnotes and place opening/closing markers where text has
    // been updated.
    $footnote.find('location[type="range"]').each(function() {
        var $location = $(this);

        // Start with the entire law and narrow it down later. The variables
        // $start_mark and $end_mark denote the highlight's start point and
        // end point, respectively. In the beginning, they are both set to the
        // entire legal document's XML, but then narrowed down afterwards.
        // This means that each node in <location> narrows it down by one
        // step, until eventually we have the final node, which is the one
        // where the highlighting (or marking) should take place.
        //
        // Usually, the $start_mark and $end_mark end up being the same thing.
        // They are only different when the highlight covers a range of
        // entities.
        //
        // Marks are the same thing except they're not a range, but a single
        // point in the text. In those cases, the $end_mark is used, because
        // the mark should come after the located text.
        var $start_mark = $location.parent().parent().closest('law');
        var $end_mark = $location.parent().parent().closest('law');

        if ($location.attr("xpath") === undefined) {
            // TODO: Instead of setting the `location_node` here, we should just
            //       set whatever variables we need, which currently are `words`
            //       and `repeat`.
            var $location_start = $location.find("start");
            var $location_end = $location.find("end");
            $start_mark = $(getElementByXPath("//" + $location_start.attr("xpath")));
            $start_mark.location_node = $location_start;
            $end_mark = $(getElementByXPath("//" + $location_end.attr("xpath")));
            $end_mark.location_node = $location_end;
        }
        else {
            $start_mark = $(getElementByXPath("//" + $location.attr("xpath")));
            $start_mark.location_node = $location;
            $end_mark = $start_mark;
        }

        // Let's be nice to XML writers and tell them what's wrong.
        if (!$start_mark.prop('tagName')) {
            var art_nr = $location.closest('art').attr('nr');
            console.error('Invalid location in footnote nr. ' + footnote_nr + ' in article nr. ' + art_nr);
            return;
        }

        /***********************************************/
        /* Add markers to denote the highlighted area. */
        /***********************************************/

        // Short-hands.
        var end_tag_name = lowercase_tagname($end_mark);
        var end_tag_parent_name = lowercase_tagname($end_mark.parent());
        var location_type = $location.attr('type');

        // If the end mark ontains a table, we'll actually want to append the
        // closing marker to the very last cell in the last row of the table.
        // This is a design choice from the official website which we imitate
        // without concerning ourselves with the reasoning behind it. At any
        // rate, we will simply designate that last cell as the $end_mark.
        //
        // NOTE: This does not support the "words"-mechanism and is assumed to
        // be mutually exclusive with it. If specificity is needed in the
        // table structure, support for specifying table cells in the XML
        // should be added.
        if ($end_mark.find('table').length) {
            $end_mark = $end_mark.find('table').find('tbody > tr').last().find('td').last();
        }

        // Adjust spaces immediately before and after the closing marker
        // according to design choices. (We don't know the logic behind those
        // design choices, we just imitate them from the official website.)
        var pre_close_space = '';
        if (end_tag_name == 'nr-title' && end_tag_parent_name == 'numart') {
            pre_close_space = ' ';
        }
        var post_deletion_space = ' ';
        if (
            end_tag_name == 'name'
            || (end_tag_name == 'nr-title' && end_tag_parent_name == 'art')
            || lowercase_tagname($end_mark) == 'td'
        ) {
            post_deletion_space = '';
        }

        if ($start_mark.location_node.attr('words')) {
            // If specific words are specified, we can just replace the
            // existing text with itself plus the relevant symbols for
            // denoting ranges.
            //
            // Note though, that we actually perform two replacements, one for
            // the start marker and another for the end marker. In the
            // overwhelming majority of cases, the seek_text will be the same
            // so the same string is being replaced, but every once in a
            // while, a replacement should occur over the span of more than
            // one sentence. In thos cases, the seek texts will differ and the
            // start marker will be placed before the value of the "words"
            // attribute in the start location, and after the value of the
            // "words" attribute in the end location.

            var seek_text_start = attr_or_emptystring($start_mark.location_node, 'words');
            var seek_text_end = attr_or_emptystring($end_mark.location_node, 'words');
            var replace_text_start = null;
            var replace_text_end = null;

            if (location_type == 'range') {
                replace_text_start = '[' + seek_text_start;
                replace_text_end = seek_text_end + pre_close_space + ']' + post_deletion_space + '<sup>' + footnote_nr + ')</sup>';
            }

            // If the XML indicates that this is a change that happens
            // repeatedly in the text, then we need to replace all instances
            // of the words.
            if ($start_mark.location_node.attr('repeat') == 'true') {
                $start_mark.html(replaceAll(
                    $start_mark.html(),
                    seek_text_start,
                    replace_text_start
                ));
                $end_mark.html(replaceAll(
                    $end_mark.html(),
                    seek_text_end,
                    replace_text_end
                ));
            }
            else {
                if ($start_mark.html() !== undefined) {
                    $start_mark.html($start_mark.html().replace(
                        seek_text_start,
                        replace_text_start
                    ));
                }
                if ($end_mark.html() !== undefined) {
                    $end_mark.html($end_mark.html().replace(
                        seek_text_end,
                        replace_text_end
                    ));
                }
            }

            // When a change is marked immediately before certain symbols such
            // as a period or a comma, the symbol should appear between the
            // closing marker and the footnote number. For example, it should
            // be "[some text]. 2)" instead of "[some text] 2).".
            end_symbols = [',', '.', ':'];
            for (i in end_symbols) {
                end_symbol = end_symbols[i];
                if ($end_mark.html() !== undefined) {
                    $end_mark.html($end_mark.html().replace(
                        ' <sup>' + footnote_nr + ')</sup>' + end_symbol,
                        end_symbol + ' <sup>' + footnote_nr + ')</sup>'
                    ));
                }
            }
        }
        else {
            // If there is a <nr-title> tag, we'll want to skip that, so
            // that the opening bracket is placed right after it.
            var $nr_title = $start_mark.children('nr-title');
            if ($nr_title.length > 0) {
                $start_mark.children('nr-title').next().first().prepend('[');
            }
            else {
                $start_mark.prepend('[');
            }

            if ($start_mark.html().match(/<\/sup>\.$/)) {
                $start_mark.html($start_mark.html().replace(/\.$/, ''));
            }

            // Figure out what the closing marker should look like, depending
            // on things we've figured out before.
            append_closing_text = pre_close_space + ']' + post_deletion_space + '<sup>' + footnote_nr + ')</sup>';

            // Actually append the closing marker.
            $end_mark.append(append_closing_text);
        }
    });

    // Go through footnotes and place deletion markers where text has been
    // removed from law.
    //
    // This section approaches things very similarly to how type="range"
    // locations are dealt with above. Please see the comments for the section
    // above for a thorough understanding of what's going on here.
    $footnote.find('location[type="deletion"]').each(function() {
        var $location = $(this);
        var $mark = $(getElementByXPath('//law/' + $location.attr('xpath')));

        // If the mark is not a valid tag any more, we'll just skip it.
        if (!$mark || !$mark.prop('tagName')) {
            console.warn('Invalid deletion location in footnote nr. ' + footnote_nr);
            return;
        }


        // Get the regular expressions for how the text should look before and
        // after the deletion mark. These regular expressions match the text
        // with and without other deletion or replacement markers.
        var before_mark_content = '';
        var after_mark_content = '';
        if ($location.attr('before-mark')) {
            var before_mark_re = new RegExp($location.attr('before-mark').trim());
            var items = before_mark_re.exec($mark.html());
            if (items && items.length > 0) {
                before_mark_content = items[0];
            }
        }
        if ($location.attr('after-mark')) {
            var after_mark_re = new RegExp($location.attr('after-mark').trim());
            var items = after_mark_re.exec($mark.html());
            if (items && items.length > 0) {
                after_mark_content = items[0];
            }
        }

        // Get the tag names of the mark and its parent, so that we can figure
        // out the context that we're dealing with when determining how to
        // present the deletion symbol.
        var tag_name = lowercase_tagname($mark);
        var tag_parent_name = lowercase_tagname($mark.parent());

        // Whether there is a space before or after the deletion symbol is
        // determined by various factors according to the design choices of
        // the official documents online. We are unaware of the reasoning
        // behind these design choices, we just imitate them.
        var pre_deletion_space = ' ';
        var post_deletion_space = ' ';
        var post_sup_space = ' ';
        if (tag_name == 'name' && tag_parent_name == 'chapter') {
            post_deletion_space = '';
        }
        if ($mark.html() == '[' || $mark.html() == '') {
            pre_deletion_space = '';
        }
        var after_mark_char = after_mark_content.substring(0, 1);
        if (after_mark_content == '' || after_mark_char == ']' || after_mark_char == '.') {
            post_sup_space = '';
        }

        // Sometimes the XML will indicate that some punctuation should be
        // immediately following the deletion symbol but before the
        // superscript. Example: "bla bla …, 2) yada yada" instead of "bla
        // bla, … 2)". For these purposes, we will check if such a punctuation
        // mark is defined in the XML and add it accordingly.
        var middle_punctuation = '';
        if ($location.attr('middle-punctuation')) {
            middle_punctuation = $location.attr('middle-punctuation');
        }

        var closing_marker = '';
        // We need to find the condition in which there's a "]" that we want to keep.
        // TODO: This condition is probaly too specific and should be generalized. It leads to
        //       an improvement on law 8/1962, but not much else.
        if ($mark.html().match(/\]/) && before_mark_content === "" && after_mark_content === "") {
            closing_marker = ']';
        }

        // Configure the deletion symbol that we'll drop into the content.
        var deletion_symbol = pre_deletion_space
                + '…'
                + middle_punctuation
                + closing_marker
                + post_deletion_space
                + '<sup>'
                + footnote_nr
                + ')</sup>'
                + post_sup_space;
        if (tag_name == 'nr-title' && tag_parent_name == 'art' && after_mark_content == '') {
            // When a deletion symbol appears at the end of an article's
            // nr-title segment, it means that the article's content in its
            // entirety has been deleted. The official design is for the
            // symbol and superscript to have normal weight (i.e. be non-bold)
            // instead of being bold weight.
            deletion_symbol = '<span class="art-deletion">' + deletion_symbol + '</span>';
        }

        // Replace the content with what was found before the deletion mark,
        // then the deletion mark itself and finally whatever came after the
        // deletion mark.
        $mark.html(before_mark_content + deletion_symbol + after_mark_content);
    });

    // Go through the pointers and place them in the text. Pointers are really
    // just superscripted numbers corresponding to footnotes which do not
    // indicate a modification to the text.
    //
    // This section is very similar to the type="deletion" section above, but
    // simpler, because it only needs to add one bit of superscripted text.
    $footnote.find('location[type="pointer"]').each(function() {
        var $location = $(this);
        var $mark = $(getElementByXPath('//law/' + $location.attr('xpath')));

        // If the mark is not a valid tag any more, we'll just skip it.
        if (!$mark || !$mark.prop('tagName')) {
            console.warn('Invalid deletion location in footnote nr. ' + footnote_nr);
            return;
        }

        // FIXME: This seems to be some stale debug.
        //console.log(location_to_string($location), "Mark: " + $mark.html());

        // Get the regular expressions for how the text should look before and
        // after the pointer. These regular expressions match the text with
        // and without other deletion or replacement markers.
        var before_mark_content = '';
        var after_mark_content = '';
        if ($location.attr('before-mark')) {
            var before_mark_re = new RegExp($location.attr('before-mark').trim());
            var contents = before_mark_re.exec($mark.html());
            if (contents && contents.length > 0) {
                before_mark_content = contents[0];
            }
        }
        if ($location.attr('after-mark')) {
            var after_mark_re = new RegExp($location.attr('after-mark').trim());
            var contents = after_mark_re.exec($mark.html());
            if (contents && contents.length > 0) {
                after_mark_content = contents[0];
            }
            if (after_mark_content == '.' && before_mark_content.match(/\.$/)) {
                after_mark_content = '';
            }
        }

        pointer_symbol = ' <sup>' + footnote_nr + ')</sup> ';

        // If we're pointing to a delelted section, and there's no content,
        // we want to add a deletion symbol instead of a pointer.
        if (before_mark_content == '' && after_mark_content == '') {
            // TODO: There are a lot of edge cases here:
            // Law 37/1992 wants us to add a deletion symbol and the pointer symbol instead of returning.
            
            return;
        }

        // Replace the content with what was found before the deletion mark,
        // then the deletion mark itself and finally whatever came after the
        // deletion mark.
        $mark.html(before_mark_content + pointer_symbol + after_mark_content);
    });

    // Note that there may be more than one sentence.
    var $footnote_sen = $footnote.find('footnote-sen');

    // Add the superscripted iterator to the first footnote sentence.
    $footnote_sen.first().before('<sup>' + footnote_nr + ')</sup>');

    // Activate internal HTML inside the footnote, which is escaped for XML
    // compatibility reasons. It's not possible to use <![CDATA[]]> in HTML,
    // and we don't want HTML inside XML elements, because then validators
    // would understand it as a part of the XML's structure, when in fact it's
    // just content intended for a browser.
    $footnote_sen.each(function() {
        $(this).html($(this).html().replace(/\&lt\;/g, '<').replace(/\&gt\;/g, '>'));
    });

    // Turn the displayed label of the first footnote into a link, if one is
    // specified in the 'href' attribute.
    var href = $footnote.attr('href');
    if (href) {
        $footnote_sen.first().html('<a href="' + href + '" target="_blank">' + $footnote_sen.first().html() + '</a>');
    }

}


var process_law = function() {
    var $law = $(this);

    // Turn encoded links into HTML. We only de-encode links because other
    // tags, such as "<i>" indicates a problem that warrants fixing.
    $law.html($law.html().replace(/&lt;a(.*?)&gt;(.*?)&lt;\/a&gt;/g, '<a$1>$2</a>'));
}


var process_art = function() {
    $(this).prepend($('<img class="box" src="' + IMG_BOX_BLACK + '" />'));
}


var process_subart = function() {
    $(this).prepend($('<img class="box" src="' + IMG_BOX_WHITE + '" />'));
}


var process_definitions = function() {
    var $subart = $(this);
    var definition = $subart.attr("definition");

    $subart.find("sen").each(function() {
        var $sen = $(this);
        var new_html = $sen.html().replace(
            new RegExp(definition, 'g'),
            "<i>" + definition + "</i>"
        );
        $sen.html(new_html);
    });
}


var process_sentence = function() {
    var $sen = $(this);

    // Style fractions in text.
    $sen.html($sen.html().replace(
        /(^([0-9])\d{1,3})\/(\d{1,2})[^0-9]/g,
        '<sup class="fraction-numerator">$1</sup>/ <span class="fraction-denominator">$2</span> '
    ));

    // Style "CO2".
    $sen.html($sen.html().replace(
        /CO2/g,
        'CO<small><sub>2</sub></small>'
    ));

    // Style "m2", "km2", "m3" and such.
    $sen.html($sen.html().replace(
        / (k)?m([23])/g,
        ' $1m<small><sup>$2</sup></small>'
    ));
}


/*
 * The order in which we process footnotes matters. Opening/closing markers
 * that are inside other opening/closing markers should be processed after the
 * outer ones. This is because the content between the outer ones will change
 * when the inner ones are processed, thereby making replacement of text
 * impossible since it all of a sudden contains markers that don't match the
 * text that should be replaced. Markers that specify a region instead of
 * specific words (via the "words" attribute in the XML) should be processed
 * first because they are always the most outermost. In short; the wider the
 * marked text, the earlier it should be put in.
 *
 * The way we go about ensuring that opening/closing markers outside others
 * get processed first, is by first processing the words-clauses that are the
 * longest. By necessity, a marked clause inside another one will be shorter.
 */
var get_ordered_footnotes = function() {
    // The resulting, ordered list of footnotes.
    var $footnotes = [];

    $('footnotes > footnote').each(function() {
        var $footnote = $(this);
        var $words = $footnote.find('[words]');
        if ($words.length == 0) {
            // This is essentially an arbitrarily high number. It just needs
            // to be higher than the length of any plausibly marked text.
            $footnote.attr('processing-order', '1000000');
        }
        else {
            // The longer the marked text, the earlier it should be processed.
            $footnote.attr('processing-order', $words.attr('words').length);
        }
        $footnotes.push($footnote);
    });

    // Sort the footnotes according to the 'processing-order' attribute that
    // we filled earlier. A higher number means higher priority.
    $footnotes.sort(function($a, $b) {
        return parseInt($b.attr('processing-order')) - parseInt($a.attr('processing-order'));
    });

    return $footnotes;
}


var make_togglable = function() {
    var $chapter = $(this);

    // Find a handle to control toggling. If chapter has no name, try nr-title.
    var $toggle_button = $chapter.children('name');
    if ($toggle_button.length == 0) {
        $toggle_button = $chapter.children('nr-title');
    }

    $toggle_button.addClass('toggle-button');
    $toggle_button.attr('data-state', "open");
    $toggle_button.attr('data-chapter-nr', $chapter.attr('nr'));
    $toggle_button.on('click', function() {
        var $subject = $(this).parent();

        if ($toggle_button.attr('data-state') == "closed") {
            $subject.children().removeClass('toggle-hidden');
        }
        else {
            $subject.children().addClass('toggle-hidden');
        }

        // But show nr-titles and names.
        $subject.children('.toggle-button,img,nr-title,name').show();

        $toggle_button.attr('data-state', $toggle_button.attr('data-state') == "closed" ? "open" : "closed");
    });
}


$(document).ready(function() {

    $('footnotes').show();

    $.each(get_ordered_footnotes(), process_footnote);

    $('law').each(process_law);
    $('law art').each(process_art);
    $('law art > subart').each(process_subart);
    $('law art > subart[definition]').each(process_definitions);
    $('law art sen').each(process_sentence);

    // The minister-clause is included in the XML only as HTML, but displayed
    // as text by default. Here we read it, and write it again, forcing the
    // HTML to be rendered.
    let $minister_clause = $('law > minister-clause');
    let new_text = $minister_clause.text();
    $minister_clause.html(new_text);
    $minister_clause.show();

    // Make references show what they're referring to on mouse-over.
    $('refer').on('mouseenter', follow_refer);

    // Make chapters togglable and close them all;
    $('law chapter').each(make_togglable);
    $('law art').each(make_togglable);
    //$('.toggle-button').click();

    $('sen').each(function() { 
        if ($(this).attr("expiry-symbol-offset")) {
            var offset = $(this).attr("expiry-symbol-offset");
            var $expiry_symbol = $('<span class="expiry-symbol">…</span>');
            if ($(this).text().indexOf("…") === -1) {
                var left = $(this).text().substring(0, offset);
                var right = $(this).text().substring(offset);
                $(this).html(left + $expiry_symbol[0].outerHTML + right);
            } else {
                $(this).html($(this).text().replace("…", $expiry_symbol[0].outerHTML));
            }
        }
    });

    // Hook up open-all and close-all buttons for togglables.
    $("#btn-close-all").click(function() {
        $(".toggle-button[data-state='open']").click();
    });
    $("#btn-open-all").click(function() {
        $(".toggle-button[data-state='closed']").click();
    });

    // Hook up the showing and hiding of subart numbers.
    $("#btn-show-subart-nrs").click(function() {
        $("subart").each(function() {
            let $this = $(this);
            let $target = $this.find("sen").first();
            if ($target.find("span.mgr").length == 0) {
                $target.prepend('<span class="mgr">' + $this.attr("nr") + '. mgr.</span> ');
            }
        });
    });
    $("#btn-hide-subart-nrs").click(function() {
        $("subart .mgr").remove();
    });

    $('law').on('mouseup', function(event) {
        let selectedText = window.getSelection().toString();

        // We should see at least one of these in the string to bother looking it up.
        known_parts = [
            " gr.",
            " mgr.",
            " tölul.",
            "-lið",
        ]
        let possibly_legit = false;
        known_parts.map((part) => {
            if (selectedText.indexOf(part) > -1) {
                possibly_legit = true;
            }
        });

        if (possibly_legit) {

            // An incomplete experiment that needs finishing before it's safe to use.
            // It adds the law identifier to the selected text if it's missing.
            // The dangerous thing about it is that it assumes that the
            // reference refers to the open law, and not some other. The user
            // may make a mistake by not including the law identifier, or the
            // identifier may not in fact be available, like in "3. gr. sömu
            // laga", referring to some other law that was mentioned previously.
            /*
            const pattern = /^\d{1,3}\/\d{4}$/;
            const contains_law = pattern.test(selectedText);
            if (!contains_law) {
                selectedText += " laga nr. " + LAW_IDENTIFIER;
            }
            */

            const $anchor = $(document.elementFromPoint(event.clientX, event.clientY));
            process_refer_legal_clause_from_text(selectedText, $anchor);
        }
    });

    // Browser-tests can check for this to see if something failed in this process.
    $('body').prepend($('<span class="hidden" id="law-javascript-success" />'));
});
