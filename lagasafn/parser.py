import os
import re
import roman
from formencode.doctest_xml_compare import xml_compare
from lagasafn.settings import DATA_DIR
from lagasafn import settings
from lxml import etree
from lxml.builder import E
from lagasafn.contenthandlers import get_nr_and_name
from lagasafn.contenthandlers import strip_markers
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import begins_with_regular_content
from lagasafn.contenthandlers import is_numart_address
from lagasafn.contenthandlers import separate_sentences
from lagasafn.contenthandlers import check_chapter
from lagasafn.contenthandlers import word_to_nr
from lagasafn.utils import ask_user_about_location
from lagasafn.utils import is_roman
from lagasafn.utils import numart_next_nrs
from lagasafn.utils import determine_month
from lagasafn.utils import strip_links
from lagasafn.utils import super_iter
from lagasafn.utils import Trail
from lagasafn.utils import Matcher

from .parse_footnotes import parse_footnotes

LAW_FILENAME = os.path.join(
    DATA_DIR, "original", settings.CURRENT_PARLIAMENT_VERSION, "%d%s.html"
)  # % (law_year, law_num)
CLEAN_FILENAME = os.path.join(
    DATA_DIR, "cleaned", "%d-%d.html"
)  # % (law_year, law_num)
PATCHED_FILENAME = os.path.join(
    DATA_DIR, "patched", "%d-%d.html"
)  # % (law_year, law_num)
PATCH_FILENAME = os.path.join(
    DATA_DIR, "patches", settings.CURRENT_PARLIAMENT_VERSION, "%d-%d.html.patch"
)  # % (law_year, law_num)
XML_FILENAME = os.path.join(DATA_DIR, "xml", "%d.%s.xml")  # % (law_year, law_num)
XML_INDEX_FILENAME = os.path.join(DATA_DIR, "xml", "index.xml")
XML_REFERENCES_FILENAME = os.path.join(DATA_DIR, "xml", "references.xml")

ERRORMAP_FILENAME = os.path.join("data", "json-maps", "errormap.json")


class LawParser:
    """
    The goal of this class is to internalize all the commonly used parsing state
    and the methods commonly used to facilitate parsing of the HTML files.
    The idea here is to reduce the amount of complexity in the overall parser.
    """

    def __init__(self, law_num, law_year):
        self.law_num = law_num
        self.law_year = law_year

        self.verbosity = 0

        # Objects that help us figure out the current state of affairs. These
        # variables are used between iterations, meaning that whenever possible,
        # their values should make sense at the end of the processing of a
        # particular line or clause. Never put nonsense into them because it will
        # completely confuse the processing elsewhere.
        self.appendix = None
        self.appendix_part = None
        self.appendix_chapter = None
        self.superchapter = None
        self.chapter = None
        self.subchapter = None
        self.art = None
        self.art_chapter = None
        self.subart = None
        self.numart_chapter = None
        self.numart = None
        self.ambiguous_section = None
        self.table = None
        self.tbody = None
        self.tr = None
        self.td = None
        self.footnotes = None
        self.mark_container = None

        self.parse_path = []

        if not os.path.isdir(os.path.dirname(XML_FILENAME)):
            os.mkdir(os.path.dirname(XML_FILENAME))

        # Check if we have a patched cleaned HTML version of the law.
        if os.path.isfile(PATCHED_FILENAME % (law_year, law_num)):
            with open(PATCHED_FILENAME % (law_year, law_num)) as patched_file:
                self.lines = super_iter(patched_file.readlines())
                patched_file.close()
        else:
            # Open and read the cleaned HTML version of the law.
            with open(CLEAN_FILENAME % (law_year, law_num)) as clean_file:
                self.lines = super_iter(clean_file.readlines())
                clean_file.close()

        # Construct the output XML object.
        self.law = E.law("", {"nr": str(law_num), "year": str(law_year)})

        # Keeps track of the turn of events. We can query this trail to check for
        # example whether the name of the document has been processed, or what the
        # last thing to be processed was. This gives us context when determining
        # what to do next.
        self.trail = Trail()
        self.trail.append(self.law)

        # A matcher:
        self.matcher = Matcher()

        # Set up the collection:
        self.collection = []

    @property
    def line(self):
        if self.lines.current_line is None:
            return None
        return self.lines.current_line.strip()

    def enter(self, path):
        if self.verbosity > 0:
            print("%s>> Entering %s at line %d" % ("  " * len(self.parse_path), path, self.lines.current_line_number))
        self.parse_path.append(path)

    def leave(self, guard=None):
        import inspect

        frame = inspect.currentframe()
        caller_frame = frame.f_back
        filename = caller_frame.f_code.co_filename
        line_number = caller_frame.f_lineno

        if len(self.parse_path) < 1:
            print("ERROR: Trying to leave a path that doesn't exist.")
            return

        if self.verbosity > 0:
            print("%s<< Leaving %s at line %d" % ("  " * (len(self.parse_path)-1), self.parse_path[-1], self.lines.current_line_number))

        if guard is not None:
            if self.parse_path[-1] != guard:
                self.error("At %s:%s: trying to leave a path (%s) that doesn't match the guard (%s)." % (filename, line_number, "->".join(self.parse_path), guard))
                return
        self.parse_path.pop()

    def leave_if_last(self, path):
        if len(self.parse_path) > 0 and self.parse_path[-1] == path:
            self.leave(path)

    def note(self, note):
        if self.verbosity > 0:
            print("%s[ NOTE ][%d] %s" % ("  " * len(self.parse_path), self.lines.current_line_number, note))

    def error(self, error):
        print("%s[ERROR ]: %s" % ("  " * len(self.parse_path), error))

    def peek(self, n=1):
        return self.lines.peek(n)

    def peeks(self, n=1):
        return self.lines.peeks(n)

    def next(self):
        return next(self.lines)
    
    def nexts(self):
        return next(self.lines).strip()

    def next_until(self, end_string):
        return self.lines.next_until(end_string)
    
    def next_untils(self, end_string):
        return self.lines.next_until(end_string).strip()
        
    def consume(self, term):
        if self.line != term:
            if self.verbosity > 0:
                self.dump_remaining(10)
            raise Exception("ERROR: Expected '%s' but got '%s'." % (term, self.line))
        self.next()

    def maybe_consume(self, term):
        if self.line == term:
            self.next()
            return True
        return False
    
    def maybe_consume_many(self, term):
        while self.line == term:
            self.next()
        return True

    def trail_push(self, item):
        self.trail.append(item)

    def trail_last(self):
        return self.trail.last()

    def trail_milestone(self, name):
        return self.trail.set_milestone(name)

    def trail_reached(self, name):
        return self.trail.milestone_reached(name)

    # collect/uncollect functions for collecting heaps of text, then returning it all in one go
    # and resetting the collection for the next time we need to collect a bunch of text.

    def collect(self, string):
        try:
            self.collection.append(string.strip())
        except AttributeError:
            self.dump_state()

    def uncollect(self):
        result = " ".join(self.collection).strip()
        self.collection = []
        return result

    def collect_until(self, end_string, collect_first_line=False):
        # Will collect lines until the given string is found, and then return the
        # collected lines.

        # TODO: The collect_first_line parameter is a bit of a hack. Ideally we should always include the first line,
        #       but because of the way most of the parser is written, this causes a lot of problems. We should refactor
        #       the entire parser to always use collect_first_line=True and then once all of the collect_until() calls
        #       have been replaced, we can remove the parameter entirely.
        #           - Smári, 2024-08-09

        done = False

        if collect_first_line:
            self.collect(self.line)

        while not done:
            try:
                self.next()
            except StopIteration:
                raise Exception("ERROR: Unexpected end of file on line %d while collecting until '%s'. \nLine: '%s'" % (self.lines.current_line_number, end_string, self.line))
            if self.matcher.check(self.line, end_string):
                done = True
                continue
            self.collect(self.line)

        total = self.uncollect().strip()

        return total

    # Scrolls the lines until the given string is found. It works internally
    # the same as the collect_until-function, but is provided here with a
    # different name to provide a semantic distinction in the code below.
    scroll_until = collect_until

    def occurrence_distance(self, lines, regex, limit=None):
        """
        Checks how much iteration is required to hit a line that matches the
        given regex. Optional limit parameter allows limiting search to a
        specific number of lines into the future.
        """

        # We start at +1 to avoid matching the current line.
        i = 1
        line = lines.peek(i)
        while line is not None and (limit is None or i <= limit):
            line = line.strip()
            if self.matcher.check(line, regex):
                return i

            i += 1
            line = lines.peek(i)

        return None

    def dump_remaining(self, max_lines=10):
        current_line = self.lines.current_line_number
        i = current_line
        # We want to include the current line in the output.
        self.lines.index -= 1
        for line in self.lines:
            print("Line %d: %s" % (i, line), end="")
            i += 1
            if i > current_line + max_lines:
                break
        # Reset the iterator to the original place.
        self.lines.index = current_line

    def dump_state(self):
        print("Current parser state: ")
        print(" parse_path: '%s'" % ("->".join(self.parse_path)))
        print(" line: '%s'" % (self.line))
        print(" line number: %d" % (self.lines.current_line_number))
        print(" chapter: '%s'" % (self.chapter))
        print(" subchapter: '%s'" % (self.subchapter))
        print(" art: '%s'" % (self.art))
        print(" art_chapter: '%s'" % (self.art_chapter))
        print(" subart: '%s'" % (self.subart))
        print(" numart: '%s'" % (self.numart))
        print(" ambiguous_section: '%s'" % (self.ambiguous_section))
        print(" footnotes: '%s'" % (self.footnotes))

    def report_location(self):
        print("[DEBUG] Line %d: %s" % (self.lines.current_line_number, self.line))


####### Individual section parser functions below:

def parse_law(parser):
    parse_intro(parser)

    while True:
        parser.maybe_consume("<hr/>")
        parser.maybe_consume_many("<br/>")
        # We continue while we pass any of the checks below, and break (at the end) if we don't.
        if parse_stray_deletion(parser):
            continue
        if parse_ambiguous_chapter(parser):
            continue
        if parse_superchapter(parser):
            continue
        if parse_chapter(parser):
            continue
        if parse_ambiguous_section(parser):
            continue
        if parse_article(parser):
            continue
        if parse_subarticle(parser):
            continue
        if parse_presidential_decree_preamble(parser):
            continue
        if parse_numerical_article(parser):
            continue
        if parse_appendix(parser):
            continue
        if parse_paragraph(parser):
            continue

        # print("ERROR: Couldn't parse anything at line %d." % parser.lines.current_line_number)

        # If we didn't parse a chapter or an article, we're done.
        break

    parse_end_of_law(parser)
    # Return whether we have reached the end of the file.
    return parser.lines.current_line_number, parser.lines.total_lines


def parse_intro(parser):
    parser.enter("intro")

    parser.scroll_until("<h2>")    # Nothing before the opening <hr/> is meaningful.

    # Parse elements in the intro.
    parse_law_title(parser)
    parse_law_number_and_date(parser)

    # We always get a <hr/> after the law number and date.    
    parser.consume("<hr/>")

    # TODO: Parsing procedural links is unimplemented.
    # parse_procedural_links(parser)

    if parser.line == "<i>":
        parse_footnotes(parser)      # This will eat any footnotes associated with the title.

    parser.maybe_consume_many("<br/>")
    parse_minister_clause_footnotes(parser)
    parser.maybe_consume_many("<br/>")

    parser.trail_milestone("intro-finished")
    parser.leave("intro")


def parse_end_of_law(parser):
    if parser.line != "</body>":
        parser.note("Trying to parse end of file without having reached the end of the file.")
        return

    parser.enter("end-of-file")
    # Do we want to do anything here?
    parser.scroll_until("</html>")
    parser.leave("end-of-file")


def parse_procedural_links(parser):
    # TODO: Unimplemented.
    return


def parse_law_title(parser):
    if parser.line != "<h2>":
        return

    parser.enter("law-title")

    # Parse law name.
    law_name = strip_links(parser.collect_until("</h2>"))

    # Remove double spaces.
    law_name = law_name.replace("  ", " ")

    # Some "laws" are not really laws, per say, but presidential
    # verdicts or contracts with external entities voted on by
    # Parliament. The type of law seems only determinable by the name,
    # so that's what we'll try here.
    #
    # For performance reasons, this should be organized so that the
    # most likely test comes first. For this reason, a few things that
    # are laws get tested at the bottom instead of with the most
    # common result at the top.
    law_type = "undetermined"
    name_strip = strip_markers(law_name).strip()
    if name_strip.find("Lög ") == 0 or name_strip[-3:] == "lög":
        law_type = "law"
    elif name_strip.find("Forsetaúrskurður ") == 0:
        law_type = "speaker-verdict"
    elif name_strip.find("Forsetabréf ") == 0:
        law_type = "speaker-letter"
    elif name_strip.find("Auglýsing ") == 0:
        law_type = "advertisement"
    elif name_strip.find("Konungsbréf ") == 0:
        law_type = "royal-letter"
    elif name_strip.find("Tilskipun") == 0:
        law_type = "directive"
    elif name_strip.find("Reglugerð ") == 0:
        law_type = "regulation"
    elif name_strip.find("Samningur ") == 0:
        law_type = "contract"
    elif name_strip.find("Stjórnarskrá ") == 0:
        # Glory, glory!
        law_type = "law"
    elif name_strip.find("Eldri lög ") == 0:
        # For 76/1970: Eldri lög um lax- og silungsveiði
        law_type = "law"
    elif name_strip.find("Hafnarlög ") == 0:
        # For 10/1944: Hafnarlög fyrir Siglufjarðarkaupstað
        law_type = "law"
    elif name_strip.find("Norsku lög ") == 0:
        law_type = "law"

    parser.law.attrib["law-type"] = law_type

    name = E.name(law_name)
    parser.law.append(name)
    parser.trail_push(name)

    parser.leave("law-title")


def parse_law_number_and_date(parser):
    parser.scroll_until("<strong>")
    if parser.line != "<strong>" or parser.trail_last().tag != "name":
        return

    parser.enter("law-number-and-date")

    # Parse the num and date, which appears directly below the law name.
    num_and_date = parser.collect_until("</strong>")
    parser.next()

    # The num-and-date tends to contain excess whitespace.
    num_and_date = num_and_date.replace("  ", " ")

    # Find the law's number, if it is specified, as well as the
    # location of the date section within the string.
    if "nr." in num_and_date:
        # Note: len('1980 nr. ') == 9
        number = num_and_date[9 : num_and_date.find(" ", 9)]

        # Note: len(' ') == 1
        date_start = 9 + len(number) + 1
    else:
        number = None

        # Note: len('1980 ') == 5
        date_start = 5

    # Example: "6. júní"
    human_date = num_and_date[date_start:]

    # Parse the date in its entirety.
    year = int(num_and_date[0:4])
    if human_date.find(".") > -1:
        day = int(human_date[0 : human_date.find(".")])
        month = int(determine_month(human_date[len(str(day)) + 2 :]))
    else:
        # There is at least one case of a the timing of the
        # enacted law only being designated by year and month, but
        # without a day. In these cases, human_date should simply
        # be the name of the month.
        # Example: https://www.althingi.is/lagas/148c/1764000.html
        day = 0
        month = int(determine_month(human_date)) if human_date else 0

    # Produce an ISO-formatted date.
    iso_date = "%04d-%02d-%02d" % (year, month, day)

    # Construct the XML node and add it to the main doc.
    xml_num_and_date = E("num-and-date", E("date", iso_date))
    if number is None:
        # If no law number is specified, then the one defined in
        # the main XML document is actually not a law number, but
        # a concatenation of date elements, for example 61/1847
        # for January 6th, 1847.
        #
        # Here we correct for the mistaken data, so that instead
        # of being wrong, the law number will be "m01d06" where
        # "m" stands for month and "d" stands for day. Note that
        # the output of the script will still say "61/1847"
        # instead of "m01d06/1847" because we can't know this
        # until we've parsed the data this far.
        #
        # We will still retain the wrong legal number as
        # "primitive-nr" for traceability.
        parser.law.attrib["primitive-nr"] = str(parser.law_num)
        parser.law_num = "m%02dd%02d" % (month, day)
        parser.law.attrib["nr"] = parser.law_num
    else:
        # Otherwise, of course, we'll just record the number.
        xml_num_and_date.append(E("num", number))

    xml_num_and_date.append(E("original", num_and_date))

    parser.law.append(xml_num_and_date)

    parser.trail_push(xml_num_and_date)

    parser.consume("</p>")

    parser.leave("law-number-and-date")


def parse_ambiguous_section(parser):
    if not (parser.peeks(0) == "<em>" and parser.trail_reached("intro-finished")):
        return False

    parser.enter("ambiguous-section")

    # Parse a mysterious thing which we will call an "ambiguous
    # section" and is composed of a single italic line. Such a line is
    # sometimes used as a sort of name for an article (45/1987,
    # 113/1990, 57/1990), sometimes as some kind of subchapter
    # (93/1933, 8/1962, 46/1980) and even as some kind of chapter
    # (37/1992, 55/1992). It is practically impossible to figure out
    # what exactly they are supposed to be, even for humans. Even
    # within the same document they may seem like article names in one
    # place but then seem to cover a few in a latter part. Sometimes
    # they are numbered, sometimes they have letters, sometimes
    # neither, and sometimes both in the same document.
    #
    # The most convoluted known use of such ambiguous sections is
    # 31/1993, where they are apparently used as sub-subchapters
    # numbered with an uppercase Latin letter for each article,
    # meaning that they can be seen as either letter-numbered article
    # names or sub-subchapters.
    #
    # At any rate, we're not going to try and figure it out and place
    # them inside articles (like article names) or articles inside
    # them (like chapters), but instead include them as independent
    # <ambiguous-section>s, leaving the same ambiguity in the XML as
    # is apparent in the actual text. They are rarely, if ever, used
    # to specify a change by a bill anyway, and thus are probably not
    # significant for programming bills in the future. Furthermore,
    # when parsing the XML, it is possible to check what the last
    # <ambiguous-section> contained, if at some point a programmer
    # needs to deal with them when using the XML.
    ambiguous_content = parser.collect_until("</em>")
    parser.consume("</em>")

    # FIXME: Separating the sentences like this incorrectly parses
    # what should be a `nr-title` as a `sen.`
    parser.ambiguous_section = E("ambiguous-section")
    add_sentences(parser.ambiguous_section, separate_sentences(ambiguous_content))

    if parser.appendix_chapter is not None:
        parser.appendix_chapter.append(parser.ambiguous_section)
    elif parser.chapter is not None:
        parser.chapter.append(parser.ambiguous_section)
    else:
        parser.law.append(parser.ambiguous_section)

    parser.maybe_consume_many("<br/>")

    parser.trail_push(parser.ambiguous_section)

    parse_footnotes(parser)

    parser.leave("ambiguous-section")

    return True


def parse_minister_clause_footnotes(parser):
    # This condition is a bit of a mess because on occasion, the name of
    # the law has been changed, but the footnotes describing them reside
    # inside what we normally call minister-clause. In other words, we
    # need to parse the contents of the minister-clause for footnotes.
    # Luckily, the footnotes to the name change always come first inside
    # the minister-clause, so what we need to do is to exclude the
    # footnotes-part of the minister-clause. We do this by checking for
    # the conditions of a minister-clause in two separate way, one for the
    # normal circumstance where there are no footnotes inside it, and also
    # in another way which corresponds with how the HTML looks when
    # footnotes are present.
    #
    # First, it checks the normal way, which is for the first <hr/> tag
    # after the law number and date, but **not** starting to read it as
    # the minister-clause **if** the second next tag is a <small>, because
    # that indicates that before the regular minister-clause content comes
    # up, there will be some footnotes that we'll want processed
    # elsewhere. When that happens, we will not process the content as a
    # minister-clause, but will rather pass this time, and let the
    # footnote-processing mechanism pick it up.
    #
    # Second, it checks if we have hit an indication that the previously
    # mentioned footnotes-inside-minister-clause part has indeed been
    # picked up elsewhere is over, and that we should conclude that we've
    # started processing the traditional minister-clause content after
    # such footnote-processing. This is done in a way that is not
    # abundantly clear by just reading the code. It just so happens that
    # under the circumstance that a law's name has changed and a footnote
    # appears inside the minister-clause to describe it, that we'll run
    # into "</small></i><br/>" and this seems consistent. However, that
    # pattern of tags can appear in many other circumstances as well. So
    # what we do, is that we check for that pattern, but only match it if
    # we haven't already processed the minister-clause. The way that this
    # is indicated is if "intro-finished" is in the processing trail. As a
    # result, we check for that pattern, but only match if we haven't yet
    # finished "intro-finished".

    # TODO: Procedural links should be handled by `parse_procedural_links` and
    # be outside of the `minister-clause`. We're cramming it in here so that
    # the output file format doesn't change while the parser is being changed
    # to recursive-descent. As a result, the procedural links are still just
    # retained in their original HTML form inside the XML for now.
    # Example:
    #  <a href="https://www.althingi.is/thingstorf/thingmalalistar-eftir-thingum/ferill/?ltg=150&amp;mnr=666">
    #   <i>
    #    Ferill málsins á Alþingi.
    #   </i>
    #  </a>
    #  <a href="https://www.althingi.is/altext/150/s/1130.html">
    #   <i>
    #    Frumvarp til laga.
    #   </i>
    #  </a>
    minister_clause = ""
    if parser.line.startswith("<a href=\"https://www.althingi.is/thingstorf/thingmalalistar-eftir-thingum/ferill/"):
        minister_clause += parser.collect_until("</a>", collect_first_line=True) + " </a> "
        parser.consume("</a>")

    if parser.line.startswith("<a href=\"https://www.althingi.is/altext/"):
        minister_clause += parser.collect_until("</a>", collect_first_line=True) + " </a> "
        parser.consume("</a>")

    while parser.line == "<br/>":
        minister_clause += "<br/> "
        parser.next()

    if (
        parser.line == "<small>"
        and (parser.peeks(1) in ["<b>", "<em>"] or parser.peeks(1).startswith("Felld"))
        and not parser.trail_reached("intro-finished")
    ):
        parser.enter("minister-clause-footnotes")
        # Parse the whole clause about which minister the law refers to.
        # It contains HTML goo, but we'll just let it float along. It's
        # not even certain that we'll be using it, but there's no harm in
        # keeping it around.

        # If there is no <hr/> clause in the future, it means that there
        # is no minister clause.
        hr_distance = parser.occurrence_distance(parser.lines, "<hr/>")
        if hr_distance is not None and hr_distance > 0:
            minister_clause += parser.collect_until("<hr/>", collect_first_line=True)
            if len(minister_clause):
                parser.law.append(E("minister-clause", minister_clause))

        parser.consume("<hr/>")
        parser.maybe_consume_many("<br/>")
        parser.leave("minister-clause-footnotes")


def parse_presidential_decree_preamble(parser):
    """
    Parses stray text in presidential decrees.
    """
    # NOTE: This may possibly be either expanded or re-used to create a parsing
    # function for general stray text that pops up in less consistently
    # formatted documents, such as international agreements.

    # FIXME: This currently does not properly handle paragraphs, i.e. when
    # stray text is followed by other stray text in a new paragraph. See
    # `contenthandlers.add_sentences`. It should be used here.

    if not (
        len(parser.parse_path) == 0
        and begins_with_regular_content(parser.line)
        and parser.law.attrib["law-type"] == "speaker-verdict"
    ):
        return False

    parser.enter("presidential-decree-preamble")

    stray_text = parser.collect_until("<br/>", collect_first_line=True)
    parser.consume("<br/>")
    parser.law.append(E("sen", stray_text))

    parser.leave("presidential-decree-preamble")

    return True


def parse_superchapter(parser):
    if not check_chapter(parser.lines, parser.law) == "superchapter":
        return False

    parser.enter("superchapter")
    parser.superchapter = E("superchapter")

    nr_title = parser.collect_until("</b>")
    parser.consume("</b>")

    name = ""
    if parser.line == "<b>":
        name = parser.collect_until("</b>")
        parser.consume("</b>")

    raw_nr = nr_title[:nr_title.find(" þáttur")].strip(".")

    # Turn "8. og 9" into "8-9", in 115/2021.
    raw_nr = raw_nr.replace(". og", "-")

    # Deal with numbers literally written out.
    # They currently don't exist beyond the fourth.
    raw_nr = word_to_nr(raw_nr)

    parser.superchapter.attrib["nr"] = raw_nr
    parser.superchapter.append(E("nr-title", nr_title))
    if len(name) > 0:
        parser.superchapter.append(E("name", name))

    parser.law.append(parser.superchapter)

    while True:
        parser.maybe_consume("<br/>")
        if parse_chapter(parser):
            continue
        if parse_article(parser):
            continue
        break

    parser.superchapter = None
    parser.leave("superchapter")

    return True

def parse_chapter(parser):
    # Chapters are found by finding a <b> tag that comes right after a
    # <br/> tag that occurs after the ministerial clause is done. We use a
    # special function for this because we also need to examine a bit of
    # the content which makes the check more than a one-liner.
    if not (
        check_chapter(parser.lines, parser.law) == "chapter"
        and parser.trail_reached("intro-finished")
    ):
        return False

    parser.enter("chapter")
    # Parse what we will believe to be a chapter.

    # Chapter names are a bit tricky. They may be divided into two <b>
    # clauses, in which case the former one is what we call a nr-title
    # (I. kafli, II. kafli etc.), and then a name describing its
    # content (Almenn ákvæði, Tilgangur og markmið etc.).
    #
    # Sometimes however, there is only one <b> and not two. In these
    # cases, there is no nr-title and only a name.
    #
    # To solve this, we first collect the content between the first
    # <b> and </b> and store that in a variable called
    # `name_or_nr_title` because we still don't know whether it's a
    # chapter name or a chapter nr-title. If however, a <b> is found
    # immediately following it, we conclude that what we've gathered
    # is the chapter nr-title and that the content in the next <b>
    # clause will be the chapter name.

    chapter_type = ""

    name_or_nr_title = parser.collect_until("</b>")
    parser.consume("</b>")

    nr = None
    if name_or_nr_title.find("kapítuli.") > -1:
        chapter_type = "kapítuli"

        # This ancient way of denoting a chapter is always represented by
        # cardinal numbers, but their `nr-title`s and `name`s are also not in
        # separate `<b>` clauses.
        t = strip_markers(name_or_nr_title).strip()
        first_word = t[:t.find(" ")]
        nr = word_to_nr(first_word)

        chapter_nr_title = name_or_nr_title[:name_or_nr_title.find("kapítuli") + 9]
        chapter_name = ""
        if name_or_nr_title.find("kapítuli. ") > -1:
            chapter_name = name_or_nr_title[name_or_nr_title.find("kapítuli.") + 10:]

        parser.chapter = E.chapter(
            {"nr": nr, "nr-type": "cardinal" },
            E("nr-title", chapter_nr_title),
        )

        if len(chapter_name):
            parser.chapter.append(E("name", chapter_name))

    elif parser.line == "<b>":
        parser.enter("chapter-nr-title")
        chapter_nr_title = name_or_nr_title

        # Let's see if we can figure out the number of this chapter.
        # We're going to assume the format "II. kafli" for the second
        # chapter, and "II. kafli B." for the second chapter B, and in
        # those examples, nr-titles will be "2" and "2b" respectively.
        t = strip_markers(chapter_nr_title).strip()
        maybe_nr = t[0 : t.index(".")]
        if is_roman(maybe_nr):
            nr = str(roman.fromRoman(maybe_nr))
            nr_type = "roman"

            extra_match = re.match(r"\.([A-Z])\.", t[len(maybe_nr):])
            if extra_match is not None:
                # A special case in lög nr. 41/1979 where a chapter has been
                # added between "I" and "II", called "I.A".
                nr += extra_match.groups()[0].lower()
            del extra_match

            roman_nr = maybe_nr
        else:
            nr = str(int(maybe_nr))
            nr_type = "arabic"
            roman_nr = None

        # We assume that a chapter nr-title with an alphabetical
        # character (like "II. kafli B" or "2b") can only occur in
        # chapters that contain the word "kafli". This is by
        # necessity, because we need to be able to parse chapter names
        # like "II. Nefndir." which contain a Roman numeral and name.
        # A chapter name like "II B. Nefndir" looks pretty outlandish
        # though, so this should be safe. Instead, the legislature
        # would surely name the chapter to "II. kafli B. Nefndir".
        #
        # We check for both "kafli" and other words known to also
        # designate some kind of chapter, because those are logically
        # equivalent, but should never appear both in the same chapter
        # line.
        #
        # We also record the word as `chapter_type` so that we can distinguish
        # between things like "1. kafli" and "1. hluti", which may appear in
        # the same law.
        chapter_type = ""
        for chapter_word_check in ["kafli", "hluti", "bók", "kap"]:
            if chapter_word_check in t:
                chapter_type = chapter_word_check
                alpha = t[t.index(chapter_word_check) + 6 :].strip(".")
                if alpha:
                    nr += alpha.lower()
        del t

        chapter_name = parser.collect_until("</b>")
        parser.consume("</b>")

        parser.chapter = E.chapter(
            {"nr": nr, "nr-type": nr_type},
            E("nr-title", chapter_nr_title),
            E("name", chapter_name),
        )

        # The `chapter-type` explains whether this chapter is shown as "kafli",
        # "hluti" or whatever else, so that we can distinguish between two
        # chapters in the same law, where one is named "1. hluti" and the other
        # "1. kafli'.
        # FIXME: In reality, "hluti"-chapters should contain other chapters as
        # opposed to being their siblings, but to implement that, we'll need to
        # make `chapter`s capable of recursivity. As "hluti"-chapters are not
        # referenced to our knowledge, we need not concern ourselves with this
        # at the moment. But we will, some day.
        if len(chapter_type):
            parser.chapter.attrib["chapter-type"] = chapter_type

        # Record the original Roman numeral if applicable.
        if roman_nr is not None:
            parser.chapter.attrib["roman-nr"] = roman_nr

        parser.leave("chapter-nr-title")

    else:
        parser.enter("chapter-name-only")
        chapter_name = name_or_nr_title
        # When the chapter doesn't have both a nr-title and a name,
        # what we see may be either a name or a Roman numeral. If it's
        # a Roman numeral, we'll want to do two things; 1) Include the
        # number in the "nr" attribute (in Arabic) and 2) Use the
        # "nr-title" tag instead of the "name" tag. If it's not a
        # Roman numeral, we'll just set a name.
        #
        # Chapters with no name but a Roman numeral may be marked
        # either with the Roman numeral alone, like "IX.", or they may
        # include the word "kafli", looking like "IX. kafli.". We
        # remove the string ". kafli" in the nr-title so that we're
        # always just dealing with the Roman numeral itself when
        # looking for a nr-title.
        try:
            maybe_roman_nr = (
                strip_markers(chapter_name)
                .replace(". kafli", "")
                .replace(". hluti", "")
                .replace(". bók", "")
                .strip()
                .strip(".")
            )

            # check for possible roman number range numbering which are seen when multiple
            # articles have been removed and are thus collectively empty
            has_ranged_roman = False
            if "–" in maybe_roman_nr:
                maybe_roman_nr_a, maybe_roman_nr_b = maybe_roman_nr.split("–")
                maybe_roman_nr_a = maybe_roman_nr_a.strip(".")
                if is_roman(maybe_roman_nr_a) and is_roman(maybe_roman_nr_b):
                    nr_a = roman.fromRoman(maybe_roman_nr_a)
                    nr_b = roman.fromRoman(maybe_roman_nr_b)
                    nr = "%s-%s" % (nr_a, nr_b)
                    roman_nr = "%s-%s" % (
                        roman.toRoman(nr_a),
                        roman.toRoman(nr_b),
                    )
                    parser.chapter = E.chapter(
                        {
                            "nr": nr,
                            "nr-type": "roman",
                            "roman-nr": maybe_roman_nr,
                        },
                        E("nr-title", chapter_name),
                    )
                    has_ranged_roman = True
            if has_ranged_roman is False:
                nr = str(roman.fromRoman(maybe_roman_nr))
                parser.chapter = E.chapter(
                    {"nr": nr, "nr-type": "roman", "roman-nr": maybe_roman_nr},
                    E("nr-title", chapter_name),
                )
        except roman.InvalidRomanNumeralError:
            # Nope! It's a name.
            nr = None
            parser.chapter = E.chapter({"nr-type": "name"}, E("name", chapter_name))

        parser.leave("chapter-name-only")

    # Must happen before the parsing of temporary clauses because iteration of
    # parents to 'law' happens when parsing articles inside them.
    if parser.appendix_chapter is not None:
        # FIXME: This `chapter` is inside an `appendix_chapter`, and may get
        # confused with normal chapters. This would properly be implemented as
        # `appendix-chapter`s inside `appendix-chapter`s but that requires
        # generalizing a bunch of functionality inside `parse_chapter`.
        # This occurs in viðauka laga nr. 61/2017.
        parser.appendix_chapter.append(parser.chapter)
    elif parser.superchapter is not None:
        parser.superchapter.append(parser.chapter)
    else:
        parser.law.append(parser.chapter)

    # Some laws have a chapter for temporary clauses, which may be
    # named something like "Bráðabirgðaákvæði", "Ákvæði til
    # bráðabirgða" and probably something else as well. We will assume
    # that a chapter name that includes that string "bráðabirgð" is a
    # chapter for temporary clauses. We also make a number of other
    # tests on the chapter name to account for various special cases
    # as pointed out in comments below.
    cn = chapter_name.lower()
    if (
        "bráðabirgð" in cn
        and "úrræði" not in cn
        and (
            # Various places where something has been removed and
            # commented in content with an a-node.
            "úrelt ákvæði til bráðabirgða" not in cn
            or
            # Special case in 87/1992 where text is before a-node
            cn.find("ákvæði til bráðabirgða.") == 0
        )
        and
        # Special case in law 90/1989
        "brottfallin lög" not in cn
        and
        # Special case in law 80/2007
        "bráðabirgðaafnot" not in cn
    ):
        parser.enter("temporary-clauses")
        if nr is None:
            parser.chapter.attrib["nr"] = "t"
        parser.chapter.attrib["nr-type"] = "temporary-clauses"
        parser.next()
        parser.maybe_consume_many("<br/>")

        parser.trail_push(parser.chapter)

        while True:
            if parse_article(parser):
                continue
            if parse_footnotes(parser):
                continue
            break

        parser.leave("temporary-clauses")
    else:
        parser.trail_push(parser.chapter)

    parser.enter("chapter-content")
    while True:
        parser.maybe_consume_many("<br/>")
        if parse_subchapter(parser):
            continue
        if parse_ambiguous_section(parser):
            continue
        if parse_ambiguous_chapter(parser):
            continue
        if parse_stray_deletion(parser):
            continue
        if parse_article(parser):
            continue
        if parse_subarticle(parser):
            continue
        if parse_footnotes(parser):
            continue

        #if parse_subchapter(parser):
        #    continue
        break

    parser.leave("chapter-content")

    parser.maybe_consume_many("<br/>")

    parser.chapter = None

    parser.leave("chapter")
    return True


# The following two functions are kind of identical but are separated for future reference
# and semantic distinction.
def parse_extra_docs(parser):
    if check_chapter(parser.lines, parser.law) in [
        "extra-docs",
    ] and parser.trail_reached("intro-finished"):
        # Accompanying documents vary in origin and format, and are not a
        # part of the formal legal text itself, even though legal text may
        # reference them. Parsing them is beyond the scope of this tool.
        # They always show up at the end, so at this point, our work is
        # done. We'll escape the loop and go for post-processing.
        return True
    return False


def parse_appendix(parser):
    if not (
        check_chapter(parser.lines, parser.law) == "appendix"
        and parser.trail_reached("intro-finished")
    ):
        return False

    parser.enter("appendix")

    nr_title = parser.collect_until("</b>")
    parser.consume("</b>")

    nr_title = strip_links(nr_title, strip_hellip_link=True).strip()

    parser.appendix = E("appendix", E("nr-title", nr_title))

    # Get the appendix number, if there is one.
    nr_title_stripped = strip_links(
        strip_markers(nr_title, strip_hellip_link=True)
    ).strip()
    nr = ""
    nr_type = ""
    roman_nr = ""
    if nr_title_stripped.strip(".").lower() == "viðauki":
        # A single, non-numbered appendix.
        pass
    else:
        if nr_title_stripped.strip(".").lower().endswith(" viðauki"):
            maybe_nr = nr_title_stripped.split(" ")[0].strip(".")
        elif nr_title_stripped.lower().startswith("viðauki "):
            maybe_nr = nr_title_stripped.split(" ")[1].strip(".")
        else:
            raise Exception("Unsupported appendix.")

        if is_roman(maybe_nr):
            nr = maybe_nr
            nr_type = "roman"
            roman_nr = str(roman.fromRoman(maybe_nr))
        else:
            nr = str(int(maybe_nr))
            nr_type = "arabic"

    # Adjust the number settings if appropriate.
    if len(nr) and len(nr_type):
        parser.appendix.attrib["nr"] = nr
        parser.appendix.attrib["nr-type"] = nr_type
        if nr_type == "roman":
            parser.appendix.attrib["roman-nr"] = roman_nr

    # See if the appendix has a name.
    if parser.line == "<b>":
        name = parser.collect_until("</b>")
        parser.appendix.append(E("name", name))
        parser.consume("</b>")

    parser.consume("<br/>")

    parser.law.append(parser.appendix)

    parser.chapter = None
    parser.art = None
    parser.subart = None
    parser.numart = None

    while True:
        parser.maybe_consume_many("<br/>")
        if parse_appendix_part(parser):
            continue
        if parse_appendix_chapter(parser):
            continue
        if parse_subarticle(parser):
            continue
        if parse_appendix_draft(parser):
            continue
        if parse_numart_chapter(parser):
            continue
        if parse_numerical_article(parser):
            continue
        if parse_paragraph(parser):
            continue
        if parse_stray_deletion(parser):
            continue
        if parse_table(parser):
            continue
        if parse_article_chapter(parser):
            continue
        break

    # FIXME: Presumably this should be `parser.appendix = None`. Not fixing now
    # because we're in the middle of something rather complicated and don't
    # want to risk breaking something.
    parser.appendix_part = None

    parser.trail_push(parser.appendix)
    parse_footnotes(parser)
    parser.leave("appendix")
    return True


def parse_appendix_chapter(parser):
    if not check_chapter(parser.lines, parser.law) == "appendix-chapter":
        return False

    parser.enter("appendix-chapter")

    parser.appendix_chapter = E("appendix-chapter")

    parser.appendix.append(parser.appendix_chapter)

    # Parse the name.
    name = parser.collect_until("</b>")
    parser.consume("</b>")
    parser.consume("<br/>")

    name = strip_links(name, strip_hellip_link=True)

    parser.appendix_chapter.append(E("name", name))

    while True:
        if parse_numerical_article(parser):
            continue
        if parse_subarticle(parser):
            continue
        if parse_chapter(parser):
            continue
        if parse_ambiguous_section(parser):
            continue
        break

    parser.appendix_chapter = None

    parser.leave("appendix-chapter")

    return True


def parse_numart_chapter(parser):
    """
    Only known to occur in appendices so far, specifically lög nr. 7/1998 (153c).
    """
    if not check_chapter(parser.lines, parser.law) == "numart-chapter":
        return False

    # Needed for `numart`s to properly locate themselves inside a
    # `numart-chapter`.
    parser.numart = None

    parser.enter("numart-chapter")
    parser.numart_chapter = E("numart-chapter")

    nr_and_name = parser.collect_until("</b>")
    parser.consume("</b>")

    nr = nr_and_name.split(".")[0]
    name = nr_and_name[len(nr) + 2:]

    parser.numart_chapter.attrib["nr"] = nr
    parser.numart_chapter.append(E("nr-title", nr + "."))
    parser.numart_chapter.append(E("name",  name))

    if parser.appendix is not None:
        parser.appendix.append(parser.numart_chapter)

    while True:
        parser.maybe_consume("<br/>")
        if parse_numerical_article(parser):
            continue
        break

    parser.numart_chapter = None
    parser.leave("numart-chapter")

    return True


def parse_paragraph(parser):
    if not (
        begins_with_regular_content(parser.line)
        # In 58/1998 (153c) definitions are presented in bold.
        or (
            parser.line == "<b>"
            and parser.peeks()[-1] == ":"
        )
    ):
        return False

    parser.enter("paragraph")

    parser.paragraph = E("paragraph")

    content = parser.collect_until("<br/>", collect_first_line=True)
    parser.consume("<br/>")

    sens = separate_sentences(content)

    add_sentences(parser.paragraph, sens)

    # NOTE: This is being done here and there in the code, most notably in
    # `parse_subart`. In time, this `parse_paragraph` function should be used
    # instead, in which case more node support should be added where once this
    # functionality has been removed from their respective `parse_` functions.
    parent = None
    if parser.art_chapter is not None:
        parent = parser.art_chapter
    elif parser.appendix_part is not None:
        parent = parser.appendix_part
    elif parser.appendix is not None:
        parent = parser.appendix
    elif parser.subart is not None:
        parent = parser.subart
    elif parser.art is not None:
        parent = parser.art
    else:
        parent = parser.law

    if parent is not None:
        paragraph_nr = str(len(parent.findall("paragraph")) + 1)
        parser.paragraph.attrib["nr"] = paragraph_nr
        parent.append(parser.paragraph)
    else:
        raise Exception("Could not find parent for paragraph.")

    parser.paragraph = None

    parser.leave("paragraph")

    return True


def parse_appendix_draft(parser):
    # Draft is a misnomer. The Icelandic word is "uppdráttur" which we have no
    # idea how to translate, so this is as good as any.
    #
    # This phenomenon is currently only known to exist in the appendix of lög
    # nr. 88/2018 and lög nr. 38/2002. The original bill contained images in its
    # PDF version, but nothing in the HTML version.
    if not parser.line.startswith("Uppdráttur"):
        return False

    parser.enter("appendix-draft")

    parser.appendix_draft = E("draft")

    content = parser.collect_until("<br/>", collect_first_line=True)
    parser.consume("<br/>")

    sens = separate_sentences(strip_links(content))

    # The name is just the first sentence.
    # Example:
    # "Uppdráttur I. Strandsvæðisskipulag á Vestfjörðum..."
    nr_title = sens[0]
    sens = sens[1:]

    # Figure out the number.
    roman_nr = nr_title.split(" ")[1].strip(".")
    nr = roman.fromRoman(roman_nr)

    parser.appendix_draft.attrib["nr"] = roman_nr
    parser.appendix_draft.attrib["roman-nr"] = str(nr)
    parser.appendix_draft.attrib["number-type"] = "roman"

    parser.appendix_draft.append(E("nr-title", nr_title))

    add_sentences(parser.appendix_draft, sens)

    parser.appendix.append(parser.appendix_draft)

    parser.appendix_draft = None

    parser.leave("appendix-draft")

    return True


def parse_appendix_part(parser):
    # Occurs in lög nr. 98/2019 (153c).
    if not (
        (
            parser.line == "<i>"
            and "-hluti" in parser.peeks()
        )
        or re.match(r'.*-hluti\.$', parser.line)
    ):
        return False

    parser.enter("appendix-part")

    style = "n"
    if parser.line == "<i>":
        style = "i"
        parser.consume("<i>")
        content = parser.collect_until("</i>", collect_first_line=True)
        parser.consume("</i>")
    else:
        content = parser.collect_until("<br/>", collect_first_line=True)

    parser.appendix_part = E("appendix-part", { "appendix-style": style })

    if ":" in content:
        nr_title, name = content.split(":")
        nr_title = nr_title.strip() + ":"
        name = name.strip()
        parser.appendix_part.append(E("nr-title", nr_title))
    else:
        name = content

    parser.appendix_part.append(E("name", name))

    if parser.subart is not None:
        parser.subart.append(parser.appendix_part)
    else:
        parser.appendix.append(parser.appendix_part)

    while True:
        parser.maybe_consume_many("<br/>")
        if parse_subarticle(parser):
            continue
        if parse_numerical_article(parser):
            continue
        if parse_paragraph(parser):
            continue

        break

    parser.appendix_part = None

    parser.leave("appendix-part")

    return True


def parse_stray_deletion(parser):
    """
    FIXME/TODO: This needs proper locating.
    """
    removed_anchor = r"<a href=\"https://www.althingi.is/[^\"]*\" title=\"Hér hefur annaðhvort[^\"]+bráðabirgða\..*\">"

    if not (
        parser.line == "…"
        or re.match(removed_anchor, parser.line)
    ):
        return False

    parser.enter("stray-deletion")

    content = parser.collect_until("<br/>", collect_first_line=True)
    parser.consume("<br/>")

    parser.mark_container = E("mark-container", E("sen", { "expiry-symbol-offset": "0" }, content))

    if parser.numart is not None:
        parser.numart.append(parser.mark_container)
    elif parser.subart is not None:
        parser.subart.append(parser.mark_container)
    elif parser.chapter is not None:
        parser.chapter.append(parser.mark_container)
    else:
        parser.law.append(parser.mark_container)

    while True:
        if parse_footnotes(parser):
            continue

        break

    parser.mark_container = None

    parser.leave("stray-deletion")

    return True


def parse_subchapter(parser):
    # Parse a subchapter.
    if not check_chapter(parser.lines, parser.law) == "subchapter" or not parser.trail_reached(
        "intro-finished"
    ):
        return False

    parser.enter("subchapter")

    subchapter_goo = parser.collect_until("</b>")
    parser.consume("</b>")

    subchapter_nr, subchapter_name = get_nr_and_name(subchapter_goo)

    parser.subchapter = E(
        "subchapter",
        {
            "nr": strip_markers(subchapter_nr),
            "nr-type": "alphabet",
        },
        E("nr-title", "%s." % subchapter_nr),
    )

    if len(subchapter_name):
        parser.subchapter.append(E("name", subchapter_name))

    parser.chapter.append(parser.subchapter)
    parser.trail_push(parser.subchapter)

    while True:
        parser.maybe_consume_many("<br/>")
        if parse_article(parser):
            continue
        if parse_footnotes(parser):
            continue

        break

    del subchapter_goo
    del subchapter_nr
    del subchapter_name

    parser.subchapter = None

    parser.leave("subchapter")

    return True


def parse_article_chapter(parser):
    if not check_chapter(
        parser.lines, parser.law
    ) == "art-chapter" or not parser.trail_reached("intro-finished"):
        return False

    parser.enter("art-chapter")

    # Parse an article chapter.
    art_chapter_goo = parser.collect_until("</b>")
    parser.consume("</b>")

    # Art chapter number and possibly name.
    space_loc = art_chapter_goo.find(" ")
    if space_loc > -1:
        art_chapter_nr = art_chapter_goo[0:space_loc].strip(".")
        art_chapter_name = art_chapter_goo[space_loc+1:]
    else:
        art_chapter_nr = art_chapter_goo.strip(".")
        art_chapter_name = ""

    parser.art_chapter = E(
        "art-chapter",
        {
            "nr": art_chapter_nr,
            "nr-type": "alphabet",
        },
        E("nr-title", "%s." % art_chapter_nr),
    )

    if len(art_chapter_name):
        parser.art_chapter.append(E("name", art_chapter_name))

    # Article chapters may appear in an article, containing
    # sub-articles, or they may in fact appear inside sub-articles.
    # The correct parent is obvious when we first run into an
    # `art-chapter` in an `art`. But when we run into another one, we
    # will have access to both a `subart` and an `art`, not knowing
    # which one to append the `art-chapter` to, at least not by only
    # seeing if a `subart` exists (because it always exists).
    # Instead, we have to check if the `art` already has an
    # `art-chapter`, and if so, append the new `art-chapter` to the
    # parent of the previous one. Otherwise, we can go by the
    # existence of `subart` and `art` like normally.

    # Check if we should append the article chapter to the last
    # sub-article, or the last article.
    if parser.appendix is not None:
        parser.appendix.append(parser.art_chapter)
    elif parser.art.find("art-chapter") is not None:
        parser.art.find("art-chapter").getparent().append(parser.art_chapter)
    elif parser.subart is not None:
        parser.subart.append(parser.art_chapter)
    elif parser.art is not None:
        parser.art.append(parser.art_chapter)

    parser.consume("<br/>")

    while True:
        parser.maybe_consume("<br/>")
        if parse_numerical_article(parser):
            continue
        if parse_paragraph(parser):
            # Only known to occur in 7. gr. laga nr. 90/2003.
            continue
        break

    parser.trail_push(parser.art_chapter)

    parser.leave("art-chapter")

    parser.art_chapter = None

    return True


def parse_ambiguous_chapter(parser):
    if check_chapter(parser.lines, parser.law) != "ambiguous":
        return False

    # Parse a mysterious text that might be a chapter but we're unable
    # to determine it as such. They are bold, they are bad, but they
    # don't really make an awful lot of sense. We'll just splash them
    # in as ambiguous bold text and leave it at that.
    #
    # This occurs before the table in 96. gr. laga nr. 55/1991, in
    # version 151b, although the table was removed in version 151c.
    #
    # It happens quite a bit, and like `ambiguous-section`, should
    # theoretically be replaced by something more formal at some
    # point, should the format of published law ever allow.
    parser.enter("ambiguous-chapter")

    ambiguous_bold_text = E(
        "ambiguous-bold-text", parser.collect_until("</b>")
    )
    parser.consume("</b>")

    italic = re.match(r"<i>\s?(.*)\s?</i>", ambiguous_bold_text.text)
    if italic is not None:
        ambiguous_bold_text.text = italic.groups()[0].strip()
        ambiguous_bold_text.attrib["ambiguous-style"] = "i"

    if parser.subart is not None:
        parser.subart.append(ambiguous_bold_text)
    elif parser.art is not None:
        parser.art.append(ambiguous_bold_text)
    elif parser.chapter is not None:
        parser.chapter.append(ambiguous_bold_text)
    else:
        parser.law.append(ambiguous_bold_text)

    parser.maybe_consume("<br/>")

    parser.trail_push(ambiguous_bold_text)

    parse_footnotes(parser)
    parser.leave("ambiguous-chapter")

    return True


def parse_sentence_with_title(parser):
    if not (
        (
            (
                parser.line in ["[", "[["]
                and parser.peeks(1) == "<i>"
            )
            or parser.line == "<i>"
        )
        and parser.peeks() != "<small>"
    ):
        return False

    # Sentence-titles are not known to occur in appendices as of 2024-09-23. If
    # they begin to occur, we'll need to handle this differently.
    if parser.appendix_part is not None:
        return False

    # Parse a sentence with a title. These are rare, but occur in 3.
    # gr. laga nr. 55/2009. Usually they are numbered, parsed as
    # numarts instead, but not here.

    # In 3. gr. laga nr. 55/2009, sentences with titles have the
    # opening marks located right before the <i> tag, meaning that we
    # have no proper place to put it in. We'll place it in the
    # beginning of the sen-title instead. There can be more than one,
    # so we'll append continuously until we run out of opening marks.

    parser.enter("sen-title")

    parser.numart = None

    sen_title_text = ""

    if parser.line in ["[", "[["]:
        sen_title_text += parser.line
        parser.next()

    sen_title_text += parser.collect_until("</i>")
    content = parser.collect_until("<br/>")
    parser.consume("<br/>")
    if parser.subart is not None:
        paragraph = add_sentences(parser.subart, separate_sentences(content))

        sen_title = E("sen-title", sen_title_text)
        parser.subart.append(sen_title)

        # The sentence title belongs inside the paragraph that
        # `add_sentences` creates, so it is inserted afterwards.
        paragraph.insert(0, sen_title)

        parser.trail_push(sen_title)

    parser.leave("sen-title")

    return True


def parse_article(parser):
    # Articles have navigation spans on them with "G???" IDs with their number.
    # We'll skip over them, as long as we are sure that after them we have the 
    # begining of an article.
    if parser.line.startswith("<span id=\"G") and parser.matcher.check(parser.peeks(2), r'<img .+ src=".*sk.jpg" .+\/>'):
        parser.next()   # Consume <span id="G???">
        parser.next()   # Consume </span>
    else:
        pass

    # This is not redundant because of the format of the above guard, but they could be combined.
    if not parser.matcher.check(parser.peeks(0), r'<img .+ src=".*sk.jpg" .+\/>'):
        return False

    parser.enter("art")

    # Parse an article.
    parser.scroll_until("<b>")
    art_nr_title = parser.collect_until("</b>")
    parser.consume("</b>")

    clean_art_nr_title = strip_markers(art_nr_title)

    # Hopefully this stays None. Not because anything will break
    # otherwise, but because Roman numerals are bad.
    art_roman_nr = None

    # Analyze the displayed article name.
    try:
        # A typical article is called something like "13. gr." or
        # "13. gr. b". The common theme among typical articles is that
        # the string ". gr." will appear in them somewhere. Anything
        # before it is the article number. Anything after it, is an
        # extra thing which is appended to article names when new
        # articles are placed between two existing ones. For example,
        # if there already are articles 13 and 14 but the legislature
        # believes that a new article properly belongs between them,
        # the article will probably be called "13. gr. a". We would
        # want that translated into an sortable `art_nr` f.e. "13a".

        # Find index of common string. If the string does not exist,
        # it's some sort of a special article. A ValueError will be
        # raised and we'll deal with it below.
        gr_index = clean_art_nr_title.index(". gr.")

        # Determine the numeric part of the article's name.
        art_nr = clean_art_nr_title[0:gr_index]

        # Occasionally an article number actually covers a range, so
        # far only seen when multiple articles have been removed and
        # are thus collectively empty. We check for the pattern here
        # and reconstruct it if needed.
        if parser.matcher.check(clean_art_nr_title, r"(\d+)\.–(\d+)"):
            from_art_nr, to_art_nr = parser.matcher.result()
            art_nr = "%s-%s" % (from_art_nr, to_art_nr)

        # Check if there is an extra part to the name which we'll want
        # appended to the `art_nr`., such as in "5. gr. a".
        #
        # Note: len('.gr.') + 1 = 6
        art_nr_extra = clean_art_nr_title[gr_index + 6 :].strip().strip(".")
        if len(art_nr_extra):
            art_nr = "%s%s" % (art_nr, art_nr_extra)

    except ValueError:
        # This means that the article's name is formatted in an
        # unconventional way. Typically this occurs only in temporary
        # clauses that may be denoted by Roman numerals or with the
        # string "Ákvæði til bráðabirgða.".
        art_nr = clean_art_nr_title.strip(".")
        try:
            art_roman_nr = str(roman.fromRoman(art_nr))
        except roman.InvalidRomanNumeralError:
            # So it's not a Roman numeral. Starting to get special.

            if parser.matcher.check(art_nr, r"^\d+\)$"):
                # Another possibility is that it's a really old-school
                # way of denoting articles (early 19th century and
                # before), which looks like "5)" instead of "5. gr.".
                art_nr = art_nr.strip(")")
            elif art_nr == "Ákvæði til bráðabirgða":
                # Yet another possibility is that it is indeed a
                # temporary clause, but instead of being numbered with
                # Roman numerals inside a chapter called "Ákvæði til
                # bráðabirgða" or similar, it is an article by that
                # name instead.
                art_nr = "t"
            else:
                # At this point we've run into some kind of article
                # that we don't know how to deal with yet. We'll just
                # move on.
                #
                # TODO: To investigate what kind of article numbers
                # are still not supported, an exception could be
                # thrown here and the script run with options
                # "-a -e -E":
                #     raise Exception(
                #         "Can't figure out: %s" % clean_art_nr_title
                #     )
                pass

    # Check if there some HTML that we want included in the `nr-title`.
    # This is typically to denote that something has been removed by
    # circumstance, such as a temporary clause that is no longer in
    # effect, or an article that changes other laws (only relevant
    # during the legislative process).
    #
    # Example: (154b) 11. gr. laga nr. 25/2023:
    #     11. gr. …
    #
    # Note that the inclusion of this stuff is automatic when the
    # article has a `name`, which is processed below, so this should
    # practically only run for articles that only have a `nr-title`.
    #
    # Note that in this specific case, we actually want to include the
    # HTML, which we are appending "</a>" at the end. Normally we don't
    # want that, so `parser.collect_until` doesn't include it.
    if parser.line.find("<a ") == 0 and parser.peeks(2) == "</a>":
        art_title_link = parser.collect_until("</a>", collect_first_line=True)
        art_nr_title = "%s %s </a>" % (art_nr_title, art_title_link)
        parser.consume("</a>")

    # Create the tags, configure them and append to the chapter.
    parser.art = E("art", E("nr-title", art_nr_title))
    parser.art.attrib["nr"] = art_nr
    if art_roman_nr is not None:
        parser.art.attrib["roman-nr"] = art_roman_nr
        parser.art.attrib["number-type"] = "roman"

    # Some laws don't have chapters, but some do.
    if parser.subchapter is not None:
        parser.subchapter.append(parser.art)
    elif parser.chapter is not None:
        parser.chapter.append(parser.art)
    elif parser.superchapter is not None:
        parser.superchapter.append(parser.art)
    else:
        parser.law.append(parser.art)

    # Check if the next line is an <em>, because if so, then the
    # article has a name title and we need to grab it. Note that not
    # all articles have names.
    if parser.line == "<em>":
        art_name = parser.collect_until("</em>")
        parser.consume("</em>")
        parser.art.append(E("name", strip_links(art_name)))
    elif parser.line == "<b>":
        # Only known to happen in m00d00/1275 and possibly 94/1996.
        art_name = parser.collect_until("</b>")
        parser.consume("</b>")
        parser.art.append(E("name", {"name-style": "b"}, strip_links(art_name)))

    # Another way to denote an article's name is by immediately
    # following it with bold text. This is very rare but does occur.
    #
    # FIXME: This section was disabled because it caused damage and it doesn't
    # seem to belong here. Somewhere we're doing this. It just looks like it's
    # in the wrong place. Also, we should check if we can handle article names
    # that are bold. It even kind of looks like two different things got mixed
    # up here.
    elif False and parser.peeks() == "<b>" and parser.peeks(2) != "Ákvæði til bráðabirgða.":
        # Exceptional case: 94/1996 contains a very strange temporary
        # clause chapter. It was originally a temporary article (24.
        # gr.) with a name denoted differently than other articles in
        # that bill. It was not a chapter.
        #
        # See: https://www.althingi.is/altext/120/s/0751.html
        #
        # Then the temporary clauses were altered with law that
        # assumed that the temporary clause section was, in fact, a
        # chapter and not an article. This has resulted in an
        # ambiguity, leaving the legal document itself in unparsable
        # limbo. The temporary clauses that are current are not
        # denoted as temporary per se, but rather as strangely
        # numbered articles that appear after article 24, which is
        # still called "Temporary clauses" (in Icelandic) and is
        # technically empty.
        #
        # See: https://www.althingi.is/lagas/150b/1996094.html
        #
        # Before this block of code was written (for supporting
        # article names denoted by <b> tags), we would parse this as a
        # temporary chapter and not as an article, due to the fact
        # that it contains the word "bráðabirgða". Now that we're
        # implementing support for bold-denoted article names, it is
        # parsed as an article name, resulting in the same limbo state
        # that can be found in the official documents.
        #
        # We need to decide whether we wish to imitate the chaotic
        # limbo in the legal code, or to parse the temporary clauses
        # as a chapter and leave article 24 as, in effect, empty.
        #
        # We have decided the latter, for the following reasons:
        #
        # 1. It is clear that Parliament's most recent treatment of
        #    these clauses have assumed that they belonged to a
        #    temporary clause chapter, and not an article. This is
        #    clear from how bills have treated the clauses after the
        #    original bill was passed.
        #
        # 2. The temporary articles are denoted with Roman numerals,
        #    typical of articles in temporary chapters but otherwise
        #    not known to occur to denote temporary clauses.
        #
        # 3. The purpose of this script is to create a logical and
        #    coherent collection of Icelandic law. To imitate the
        #    limbo would go against this goal, whereas interpreting it
        #    as a chapter brings us closer to achieving it.
        #
        # This decision manifests itself in the latter part of the
        # elif-line above, where we peek 2 lines into the future and
        # check if it's the article with that specific name. That
        # latter part only returns true in the very specific case
        # outlined here.

        parser.scroll_until("<b>")
        art_name = parser.collect_until("</b>")
        parser.consume("</b>")

        parser.art.append(
            E("name", strip_links(art_name), {"original-ui-style": "bold"})
        )

    # Check if the article is empty aside from markers that need to be
    # included in the article <nr-title> or <name> (depending on
    # whether <name> exists at all).
    while parser.line in ["…", "]"]:
        marker = parser.collect_until("</sup>", collect_first_line=True)
        parser.art.getchildren()[-1].text += " " + marker + " </sup>"
        parser.consume("</sup>")

    parser.trail_push(parser.art)

    # There can be no current subarticle or article chapter if we've
    # just discovered a new article.
    parser.subart = None
    parser.art_chapter = None

    while True:
        parser.maybe_consume_many("<br/>")
        if parse_article_chapter(parser):
            continue
        if parse_numerical_article(parser):
            continue
        if parse_subarticle(parser):
            continue
        if parse_ambiguous_chapter(parser):
            continue
        if parse_footnotes(parser):
            continue
        if parse_paragraph(parser):
            continue
        break

    parser.maybe_consume_many("<br/>")
    parse_footnotes(parser)

    parser.art = None

    parser.leave("art")
    return True


VISITATIONS = 0

def parse_subarticle(parser):
    if not (
        parser.matcher.check(
            parser.line, r'<img .+ id="F?[GB](\d+)([A-Z][A-Z]?)?M(\d+)" src=".*hk.jpg" .+\/>'
        )
        or parser.line == '<img alt="" height="11" src="hk.jpg" width="11"/>'
    ):
        return False

    # Parse a subart.
    parser.enter("subart")

    parser.numart = None

    if parser.matcher.match is not None:
        subart_nr = parser.matcher.result()[2]
    else:
        # This happens in appendices when subarticles are not numbered
        # properly, notably in 4/1995. We'll have to figure out the correct
        # `subart_nr` without reading from the HTML.
        subart_nr = str(len(parser.appendix.findall("subart")) + 1)

    # Check how far we are from the typical subart end.
    linecount_to_br = parser.occurrence_distance(parser.lines, r"<br/>")

    # Check if there's a table inside the subarticle. 
    linecount_to_table = parser.occurrence_distance(
        parser.lines, r'<table width="100%">', linecount_to_br
    )

    subart_name = ""
    # If a table is found inside the subarticle, we'll want to end the
    # sentence when the table begins.
    if linecount_to_table is not None:
        content = parser.collect_until('<table width="100%">')
    elif parser.peeks() == "<span>":
        # This means that maybe a `numart` is coming up in the beginning.
        # Content will be empty, but caught by `parse_numerical_article`.
        content = ""
        parser.next()
    else:
        # Everything is normal.
        content = parser.collect_until("<br/>")
        parser.maybe_consume_many("<br/>")

    parser.subart = E("subart", {"nr": subart_nr})

    if parser.matcher.check(content, "^<b>(.*)</b>(.*)<i>(.*)</i>"):
        # FIXME: This probably belongs in its own `parse_person` function!

        # Check if the subarticle content contains bold AND italic text, which
        # may indicate a person (bold) is being given a role (italic).

        subart_name, text, role = parser.matcher.result()
        content = content.replace("<b>%s</b>" % subart_name, "")
        # content = content.replace("<i>%s</i>" % role, )
        parser.subart.append(E("name", subart_name))
        # subart.append(E("name", role))

        # Swap out the <i> text for a <name> tag.
        before, after = content.split("<i>")
        name, after = after.split("</i>")

        sens = separate_sentences(before)
        add_sentences(parser.subart, sens)
        parser.subart.append(E("name", name))
        sens = separate_sentences(after)
        add_sentences(parser.subart, sens)

    else:
        sens = separate_sentences(strip_links(content))
        add_sentences(parser.subart, sens)

    if (
        parser.art_chapter is not None
        and parser.art_chapter.getparent().tag != "subart"
    ):
        # When a `subart` is appended directly to an `art-chapter`,
        # its number is reset. Legal content reflects this reality
        # (f.e. 11. mgr. B-liðar 68. gr. laga nr. 90/2003), but the
        # HTML continues the number sequence from the beginning of
        # the article (of which the `art-chapter` is a part).
        #
        # It is non-trivial to fix this in the HTML because the
        # marking convention (see regex at the beginning of
        # `subart`-parsing) does not take `art-chapter`s into
        # account, and thus would become ambiguous.
        #
        # To fix this, we need to figure out the `subart`'s true
        # number here by checking the number of the last numart in
        # the `art-chapter` being appended to.
        previous_subarts = parser.art_chapter.findall("subart")
        if len(previous_subarts) > 0:
            previous_subart_nr = previous_subarts[-1].attrib["nr"]
            new_subart_nr = str(int(previous_subart_nr) + 1)
        else:
            new_subart_nr = "1"
        parser.subart.attrib["nr"] = new_subart_nr
        parser.art_chapter.append(parser.subart)
    elif parser.art is not None:
        parser.art.append(parser.subart)
    elif parser.appendix_chapter is not None:
        parser.appendix_chapter.append(parser.subart)
    elif parser.appendix_part is not None:
        parser.appendix_part.append(parser.subart)
    elif parser.appendix is not None:
        parser.appendix.append(parser.subart)
    elif parser.chapter is not None:
        parser.chapter.append(parser.subart)
    else:
        # An occasional text, mostly advertisements, declarations,
        # edicts and at least one really ancient law, contain only
        # subarticles. Possibly in a chapter, and possibly not.
        parser.law.append(parser.subart)

    while True:
        parser.maybe_consume_many("<br/>")
        if parse_table(parser):
            continue
        if parse_sentence_with_title(parser):
            continue
        if parse_stray_deletion(parser):
            continue
        if parse_numerical_article(parser):
            continue
        if parse_article_chapter(parser):
            continue
        if parser.appendix is not None and parse_appendix_part(parser):
            continue
        if parse_paragraph(parser):
            continue
        if parse_footnotes(parser):
            break

        break

    parser.maybe_consume_many("<br/>")

    parser.trail_push(parser.subart)

    parser.subart = None

    parser.leave("subart")
    return True


def parse_deletion_marker(parser):
    if not (parser.line.strip() == "…" and parser.trail_last().tag == "num-and-date"):
        return

    parser.enter("deletion-marker")
    # Support for a deletion marker before any other content such as
    # an article, subarticle, numart, chapter or anything of the sort.
    # We'll place it in a sentence inside a subart so that the
    # footnotes-functionality responds accordingly.
    #
    # Only known to occur in the following:
    # - m01d13/1736
    # - m07d01/1746
    # - m01d27/1847
    # - 97/1993

    parser.subart = E("subart")
    parser.subart.attrib["nr"] = "1"

    premature_deletion = parser.collect_until("<br/>")
    add_sentences(parser.subart, [premature_deletion])

    parser.law.append(parser.subart)

    parser.trail_push(parser.subart)

    parser.leave("deletion-marker")


def parse_numerical_article(parser):
    if not (
        parser.matcher.check(parser.line, r'<span id="(F\d?)?[BG](\d+)([0-9A-Z]*)L(\d+)">')
        # FIXME: Try matching the following line without a regex check.
        or (parser.matcher.check(parser.line, "<span>") and parser.peeks() != "</span>")
        or is_numart_address(parser.line)
    ):
        return False

    # Sometimes a numart isn't properly defined in the HTML with the `<span>`
    # as described above. This impacts parsing in a few ways. We detect it here
    # and react to it in the code that follows.
    denoted_with_span = True
    if not parser.line.startswith("<span"):
        denoted_with_span = False
        parser.lines.index -= 1

    parser.enter("numart")
    # Parse a numart, or numerical article.

    # The removal of ". " is to turn a human readable numerical
    # article that contains both a numerical component and an
    # alphabetic one, into something easier to work with
    # programmatically. Example: "9. a" becomes "9a" in law nr.
    # 20/2003.
    numart_nr = strip_markers(parser.peeks().strip("(").strip(")").strip(".")).replace(
        ". ", ""
    )

    if parser.matcher.check(numart_nr, r"(\d+)\.–(\d+)"):
        # Support for numart ranges, which are only known to occur when many
        # numarts have been removed. This occurs for example in 145. gr. laga
        # nr. 108/2007.
        from_numart_nr, to_numart_nr = parser.matcher.result()
        numart_nr = "%s-%s" % (from_numart_nr, to_numart_nr)
    elif parser.matcher.check(numart_nr, r"([A-Z])\.[–-]([A-Z])"):
        # Support for alphabetical ranges, which are also only known to occur
        # when many numarts have been removed. This happens in temporary
        # clauses of lög nr. 99/1993.
        from_numart_nr, to_numart_nr = parser.matcher.result()
        numart_nr = "%s-%s" % (from_numart_nr, to_numart_nr)

    # The previous numart gives us context for decision-making for
    # this numart. It is only filled if the last thing we processed
    # was a numart as well (in trail[-1]), for example whether this is
    # actually a sub-numart or a super-numart. Otherwise it will
    # remain None, indicating that this is the first numart being
    # processed this time around.
    if parser.trail_last().tag == "numart":
        # Set the previous numart before current numart gets created.
        prev_numart = parser.numart
    else:
        prev_numart = None

    if numart_nr == "1.1":
        # This happens when a `numart` is detected in a tree-scheme (example in
        # appendix of lög nr. 55/2012). In those cases, the previous `numart`
        # will have been previously detected as numeric, since it begins in the
        # same way, with a "1". We correct that here.
        #
        # But sometimes, this is actually the start of a tree-scheme `numart`
        # list inside something like a `numart-chapter`, in which case we don't
        # need change anything retro-actively.
        # Example: I. viðauki laga nr. 7/1998 (153c).
        if prev_numart is not None and prev_numart.attrib["nr-type"] == "numeric":
            prev_numart.attrib["nr-type"] = "tree"

    # This is only known to happen in 3. gr. laga nr. 160/2010. A
    # numart has been removed and the numbers of its following numarts
    # updated accordingly. We'll just append an empty numart with a
    # special type "removed" and move on, but we need to add it
    # because although it contains no content, it needs to have a
    # container for the deletion marker. That way, the next iteration
    # will make decisions on its context according to this iteration's
    # prev_numart.
    #
    # Its number will be a string, "removed-after-[X]" where "[X]" is
    # the number of the last numart. This is to make them identifiable
    # when rendering software wants to add deletion markers. A "sen"
    # node is also added for the deletion marker to be addable.
    if numart_nr == "":
        content = parser.collect_until("</span>")
        dummy_numart = E(
            "numart",
            {
                "nr": "removed-after-%s" % prev_numart.attrib["nr"],
                "nr-type": "removed",
            },
        )
        add_sentences(dummy_numart, [content])
        prev_numart.getparent().append(dummy_numart)
        parser.scroll_until("<br/>")
        parser.leave("numart")
        return

    # In 6. tölul. 1. gr. laga nr. 119/2018, the removal of previous
    # numarts is communicated differently than above (3. gr. laga nr.
    # 160/2010). In this case, the <span> that normally contains the
    # numart_nr contains nothing, not even the deletion marker
    # (literal string "…"). Instead, the deletion marker comes after
    # the </span> that immediately follows the opening <span>.
    #
    # To deal with it, we will check if the detected numart_nr is
    # "</span>", which makes no sense, check the next line for the
    # deletion marker, and if it's there, we'll respond similarly to
    # how we respond to 3. gr. laga nr. 160/2010 (which was
    # immediately above this comment on 2022-01-23).
    elif numart_nr == "</span>" and parser.peeks(2) == "…":
        parser.scroll_until("</span>")
        content = parser.collect_until("<br/>")
        dummy_numart = E(
            "numart",
            {
                "nr": "removed-after-%s" % prev_numart.attrib["nr"],
                "nr-type": "removed",
            },
        )
        add_sentences(dummy_numart, [content])
        prev_numart.getparent().append(dummy_numart)
        return

    # Dictates where we will place this numart.
    parent = None

    # The variable `special_roman` is true under the almost unique
    # circumstances that an alphabetic numart turns from "h" to a new
    # sub-numart with Roman numeral "i", resulting in a sequence of
    # "...f,g,h,i,ii,iii".
    #
    # The varible is used later to prevent the script mistaking the
    # first "i" in a Roman sub-list for the next item in an
    # alpbahetical list.
    #
    # This is tested by checking if the last numart number was "h" but
    # also if exactly 6 lines later, we run into an "ii.", which then
    # means that we've run into a Roman-numeric "i" that would
    # otherwise be mistaken for the letter following "h".
    #
    # This was previously only known to happen in 50. gr. laga nr.
    # 108/2007, which was removed in March of 2020. However, the same
    # happens in 1. mgr. 21. gr. laga nr. 19/1996, although the
    # symbols are displayed in parentheses.
    try:
        special_roman = prev_numart.attrib["nr"] == "h" and parser.lines.peek(
            6
        ).strip() in ["ii.", "(ii)"]
    except (AttributeError, IndexError):
        # Definitely not the special scenario if this goes wrong.
        special_roman = False

    # Build a list of expected numarts. This will help us determine
    # whether this numart is the first among sub-numarts, or if a list
    # of sub-numarts has ended or what.
    if prev_numart is not None:
        # Create a list of expected numart_nrs, considering the type
        # of the previous numart. If the current numart_nr is
        # unexpected, it means that either a sub-numart listing has
        # started, or ended. Whether it's starting or ending, we'll
        # figure out slightly further below.
        expected_numart_nrs = numart_next_nrs(prev_numart)

        # See comment for `special_roman` above. Under the conditions
        # outlined there, we won't be expecting "i" anymore, even if
        # it comes after an "h", and will therefore construct a new
        # sub-list from the "i" after the "h" instead of just adding
        # another item.
        if special_roman:
            expected_numart_nrs.remove("i")

        # If the numart number contains a range, something like
        # "10-13", we'll need to isolate the first bit and match that
        # with what's expected.
        if "-" in numart_nr:
            first_bit_of_numart = numart_nr[0 : numart_nr.find("-")]
        else:
            # Otherwise, we can treat the entire number as the first
            # bit, to be matched against.
            first_bit_of_numart = numart_nr

        # See if this is the next numart in a predictable succession.
        if first_bit_of_numart in expected_numart_nrs:
            # This `numart` is simply the next one, so we'll want to
            # append it to whatever node that the previous `numart`
            # was appended to.
            parent = prev_numart.getparent()
        else:
            # FIXME: These is no obvious reason for this `if`-block to be
            # inside an `else`-block.
            if numart_nr.lower() in ["a", "i", "—", "–"] or (
                numart_nr.isdigit() and int(numart_nr) == 1
            ):
                # A new list has started within the one we were
                # already processing, which we can tell because there
                # was a `numart` before this one, but this `numart`
                # says it's at the beginning, being either 'a' or 1.
                # In this case, we'll choose the previous `numart` as
                # the parent, so that this new list will be inside the
                # previous one. We append to the last paragraph of
                # that parent.
                if (
                    prev_numart.getparent().getparent() is not None
                    and prev_numart.getparent().getparent().getchildren()[-1].getchildren()[-1].tag != "numart"
                ):
                    # This happens in the rather unfortunate circumstance that
                    # a list of `numart`s is in one `paragraph` and then
                    # another list follows in another `paragraph` (as opposed
                    # to a `subart`).
                    #
                    # In this case, we need to check if the last `paragraph` in
                    # the `subart` is a `numart` or not, to properly judge if
                    # we should be adding to that list, or if it's another list
                    # of `numart`s in another paragraph.
                    #
                    # Only known to happen in 3. gr. laga nr. 78/1993.
                    #
                    # May this never happen again.
                    parent = prev_numart.getparent().getparent().findall("paragraph")[-1]
                else:
                    parent = prev_numart.findall("paragraph")[-1]
            else:
                # A different list is being handled now, but it's not
                # starting at the beginning (is neither 'a' nor 1).
                # This means that we've been dealing with a sub-list
                # which has now finished, so we want to continue
                # appending this `numart` to the parent of the parent
                # of the list we've been working on recently, which is
                # the same parent as the nodes that came before we
                # started the sub-list.
                #
                # Parent is a `paragraph`, grandparent is another
                # `numart`, great-grandparent is the last `paragraph`
                # of the "grandparent numart", which is the one we
                # want to append to.
                #
                # Hey, it's simpler than the British monarchy.
                #
                # We'll need to iterate through ancestors in case there are
                # multiple levels of `numart`s, checking each time if the
                # current `numart_nr` matches the expected next numart number
                # from each ancestor. Once `numart_nr` matches what we
                # expected, we know we've found the right ancestor.
                found_parent = None
                maybe_sibling = prev_numart.getparent()
                while found_parent is None:
                    # We know that the parent is never the first
                    # `maybe_parent`'s parent because that would mean that the
                    # current `numart` is a sibling of the `prev_numart` which
                    # makes no sense in this place in the code, so we can
                    # safely assume that the first possible `found_parent` is
                    # the `prev_numart`'s parent.
                    maybe_sibling = maybe_sibling.getparent()
                    if maybe_sibling.tag == "paragraph":
                        maybe_sibling = maybe_sibling.getchildren()[-1]

                    expected = numart_next_nrs(maybe_sibling)

                    if numart_nr in expected:
                        # Yes! We found the sibling, so we know its parent.
                        found_parent = maybe_sibling.getparent()
                    else:
                        # Doesn't make sense. Let's try the parent.
                        maybe_sibling = maybe_sibling.getparent()

                parent = found_parent

    # A parent may already be set above if `numart` currently being
    # handled is not the first one in its parent article/subarticle.
    # However, if it is indeed the first one, we need to figure out
    # where to place it. It can be placed in a subarticle, an article
    # or, in some cases, into a chapter or even the law itself.
    if parent is None:
        # A `numart` should only be appended to the `art-chapter` if
        # the `art-chapter` is a child of a `subart`. Otherwise, it
        # should be appended to a `subart` that is a child of the
        # `art-chapter` (or `art`). An `art-chapter` can be a child
        # of `art` and parent of many `subart`s, or a child of a
        # `subart` (see lög nr. 90/2003).
        if (
            parser.art_chapter is not None
            and parser.art_chapter.getparent().tag == "subart"
        ):
            parent = parser.art_chapter
        elif parser.numart_chapter is not None:
            parent = parser.numart_chapter
        elif parser.appendix_chapter is not None:
            parent = parser.appendix_chapter
        elif parser.appendix_part is not None:
            parent = parser.appendix_part
        elif parser.appendix is not None:
            parent = parser.appendix
        elif parser.subart is not None:
            # A numart should belong to the same paragraph as a
            # potential sentence explaining what's being listed.
            parent = parser.subart.findall("paragraph")[-1]
        elif parser.art is not None:
            # FIXME: Investigate if this ever actually happens and
            # explain when it does, or remove this clause.
            parent = parser.art
        elif parser.chapter is not None:
            # FIXME: Investigate if this ever actually happens and
            # explain when it does, or remove this clause.
            parent = parser.chapter
        else:
            # FIXME: Investigate if this ever actually happens and
            # explain when it does, or remove this clause.
            parent = parser.law

    # Figure out the numart's type.
    if re.match(r"^\d+\.\d+$", numart_nr) or re.match(r"^\d+\.\d+\.\d+$", numart_nr):
        # NOTE: This has to be checked before the "numeric" detection below,
        # because the first character of these tree-scheme `numart_nr`s is also
        # a digit.
        numart_type = "tree"
    elif numart_nr[0].isdigit():
        numart_type = "numeric"
    elif numart_nr in ["—", "–"]:
        numart_type = "en-dash"
    else:
        # At this point, we're dealing with a numart that is
        # represented with a Latin character, OR a Roman numeral.
        # Because Roman numerals overlap the Latin alphabet, we will
        # need to check the context in which we run into this numart.
        # If it's an "i", we'll need to determine whether it's the
        # alphabetical letter "i" or the Roman numeral "i" for 1, by
        # examining the previous numart. Once we've correctly figured
        # out that difference at the beginning of the list, we can
        # distinguish between Roman numerals and Latin characters by
        # checking the type of the previous numart.

        if numart_nr.lower() == "i":
            # See comment for `special_roman` above.
            if prev_numart is None or prev_numart.attrib["nr"].lower() != "h" or special_roman:
                numart_type = "roman"
            else:
                numart_type = "alphabet"

        elif is_roman(numart_nr.upper()):
            # If we run into something that *can* be a Roman numeral,
            # we'll simply inherit the type of the previous numart. We
            # should never run into these unless there is a previous
            # numart, since "a" is not a Roman numeral and therefore
            # we'll only run into overlapping characters once we're
            # well into the list.
            #
            # Note that "i" will always already have been caught by
            # the previous if-statement before this ever gets the
            # chance to process it.
            #
            # We can't look into the last numart because that may be a
            # sub-numart of the previous numart. But we're confident
            # in this numart being the non-first among its siblings,
            # so we'll know that the parent's last child was the
            # numart before it. So all we need to do is to find the
            # last child of this numart's parent to find the one
            # immediately before it at the same stage in the tree.

            numart_type = parent.getchildren()[-1].attrib["nr-type"]

        else:
            numart_type = "alphabet"

    # Dash-numarts need special treatment because they don't contain
    # information about their numeric position, since they are all
    # simply a dash. We must figure out their number and assign a new
    # `numart_nr`. The `nr-title` will still contain just a dash.
    if numart_type == "en-dash":
        if prev_numart is not None and prev_numart.attrib["nr-type"] == "en-dash":
            numart_nr = str(int(prev_numart.attrib["nr"]) + 1)
        else:
            numart_nr = "1"

    # Create numerical article.
    parser.numart = E("numart", {"nr": numart_nr, "nr-type": numart_type})

    # Add the numerical article to its parent.
    parent.append(parser.numart)

    # NOTE: Gets added after we add the sentences with `add_sentences`.
    if denoted_with_span:
        numart_nr_title = parser.collect_until("</span>")
    else:
        numart_nr_title = parser.peeks()

    # Sometimes the content of a `numart` is in its own separate line instead
    # of immediately following the `name` inline. We must account for it by
    # consuming the `<br/>` tag to continue parsing correctly.
    # Occurs in:
    # - in 1-6. tölul. 7. gr. laga nr. 112/2021.
    #
    # TODO: This styling choice should be communicated in the XML somehow. It
    # has no bearing on the meaning or referencing, but it should in principle
    # be possible to render the file identically to the official version.
    if parser.line == "<br/>":
        parser.consume("<br/>")

    # Check for a closing bracket.
    # Example:
    #     13-19. tölul. 1. mgr. 3. gr. laga nr. 116/2021 (153c).
    if all(
        [
            parser.peeks(1) == "]",
            parser.peeks(2) == '<sup style="font-size:60%">',
            parser.peeks(4) == "</sup>",
        ]
    ):
        numart_nr_title += parser.collect_until("</sup>") + " </sup>"

    numart_name = ""
    if parser.peeks() == "<i>" or (parser.peeks() == "[" and parser.peeks(2) == "<i>"):
        # Looks like this numerical article has a name.
        # Note that an opening marker may come before the name, in which case
        # we'll want to include it in the name, so we collect stuff before the `<i>`.
        numart_name = parser.collect_until("<i>")

        # Note that this gets inserted **after** we add the sentences
        # with `add_sentences` below.
        numart_name += parser.collect_until("</i>")

        # This is only known to happen in 37. tölul. 1. mgr. 5. gr. laga nr. 70/2022.
        # The name of a numerical article is contained in two "<i>"
        # tags separated with an "og".
        if parser.lines.peeks() == "og" and parser.lines.peeks(2) == "<i>":
            addendum = parser.collect_until("</i>").replace("<i> ", "")
            numart_name += " " + addendum

    # Read in the remainder of the content.
    content = parser.collect_until("<br/>")

    # Split the content into sentences.
    sens = separate_sentences(strip_links(content))

    # Add the title info to the `numart`.
    parser.numart.insert(0, E("nr-title", numart_nr_title))
    if len(numart_name) > 0:
        # Inserted immediately after the `nr-title`, so 1.
        parser.numart.insert(1, E("name", numart_name))

    # Check if this numart is actually just a content-less container
    # for a sub-numart, by checking if the beginning of the content is
    # in fact the starting of a new list, numeric or alphabetic.
    possible_nr_title = strip_markers(sens[0]) if len(sens) else ""
    if possible_nr_title in ["a.", "1."]:
        new_numart_nr = possible_nr_title.strip(".")

        # Instead of adding the found sentences to the numart that
        # we've just made above, we'll create an entirely new numart,
        # called new_numart, and add that to the current numart.
        new_numart = E(
            "numart",
            {
                "nr": new_numart_nr,
                # The style-note is to communicate information to a
                # possible layouting mechanism. In the official
                # documents, a sub-numart that appears this way is not
                # shown in a new line as normally, but rather inside
                # its parent as if it were content. It's the layouting
                # mechanism's responsibility to react to this
                # information, if needed.
                "style-note": "inline-with-parent",
            },
        )

        # Mark the new numart as alphabetic, if appropriate.
        if not new_numart_nr.isdigit():
            new_numart.attrib["nr-type"] = "alphabet"

        # Get the `nr-title` from the first `sen`. Note that we go
        # back for the 'sens' list because we'll want to include
        # markers that might be there, but have been removed from
        # `possible_nr_title` for comparison purposes.
        #
        # We then remove it from the rest of the sentences precisely
        # because it is the `nr-title`.
        nr_title = sens.pop(0)

        # Add the sentences to the new numart, creating paragraph.
        add_sentences(new_numart, sens)

        # Insert the `nr-title` in the newly created `numart`.
        new_numart.insert(0, E("nr-title", nr_title))

        # Add the new numart to the current numart.
        parser.numart.append(new_numart)

        # Make sure that future iterations recognize the new numart as
        # the last one processed.
        parser.numart = new_numart

    else:
        # Add the sentences to the numart.
        add_sentences(parser.numart, sens)

    while True:
        parser.maybe_consume("<br/>")
        # Handle extra paragraphs that we don't know where to place.
        if begins_with_regular_content(parser.line):
            # FIXME: Move this stuff to `parse_paragraph` and start using that
            # here instead of this.

            # When regular (text) content immediately follows a
            # numart, and not a new location like an article,
            # subarticle or another numart, we must determine its
            # nature. We'll start by finding the content.
            extra_content = parser.collect_until("<br/>", collect_first_line=True)

            # Process the extra content into extra sentences.
            extra_sens = separate_sentences(strip_links(extra_content))

            #########################################################
            # Consider the following paragraphs below e-stafl.
            # 9. tölul. 1. gr. a laga nr. 161/2002 (151c).
            #
            # "Við mat á atkvæðisrétti og réttindum til að tilnefna
            # eða víkja frá stjórnarmönnum eða stjórnendum skal
            # leggja saman réttindi sem móðurfélag og dótturfélag
            # ráða yfir."
            #
            # and immediately below it:
            #
            # "Við mat á atkvæðisrétti í dótturfélagi skal ekki
            # talinn með atkvæðisréttur sem fylgir eigin hlutum
            # dótturfélagsins eða dótturfélögum þess."
            #
            # These are extra paragraphs to numarts. They are not
            # very common but not exactly rare, either. By far most
            # numarts only contain one paragraph.
            #
            # It is tricky to figure out exactly where they belong,
            # as this can really only be determined by context.
            #
            # In the above example, it could be that the stray
            # paragraphs belonged to 'e-stafl. 9. tölul.', but in
            # reality, they both belong to '9. tölul.' and are thus
            # siblings, and not children, of the numart 'e-stafl.
            # 9. tölul.'.
            #
            # This can only be determined by a human reading the text
            # and explaining the context. We thus ask the user here
            # for input, to locate these stray paragraphs.
            #########################################################

            extra_sens_target = ask_user_about_location(extra_sens, parser.numart)

            # User opted to skip. We'll break the loop.
            if extra_sens_target is None:
                break

            # Add the stray sentences in the location decided by the
            # user.
            add_sentences(extra_sens_target, extra_sens)

            # We'll need to change the remembered numart to the
            # target of the extra sentences, if it happens to be a
            # numart, so that the next numart gets the right parent.
            if extra_sens_target.tag == "numart":
                parser.numart = extra_sens_target
            continue
        if parse_stray_deletion(parser):
            continue
        break

    parser.trail_push(parser.numart)
    parser.leave("numart")
    return True


def parse_table(parser):
    if not (
        re.match("<table", parser.line)
        or (
            parser.line == "<b>"
            and parser.peeks(2) == "</b>"
            and parser.peeks(3) == "<br/>"
            and re.match("<table", parser.peeks(4)) is not None
        )
    ):
        return False

    parser.enter("table")

    # Support for a table name. Only known to occur in 100. gr. laga nr.
    # 55/1991 (153).
    table_name = ""
    if parser.line == "<b>":
        table_name = parser.collect_until("</b>")
        parser.consume("</b>")
        parser.consume("<br/>")

    parser.table = E("table")
    parser.tbody = E("tbody")
    parser.table.append(parser.tbody)

    parser.consume('<table width="100%">')
    parser.consume("<tbody>")

    parent =  None
    if parser.subart is not None:
        parent = parser.subart
    elif parser.art is not None:
        parent = parser.art
    elif parser.appendix is not None:
        parent = parser.appendix

    if table_name:
        parent.append(E("table-name", table_name))
    parent.append(parser.table)

    while True:
        if parse_tr(parser):
            continue

        break

    parser.consume("</tbody>")
    parser.consume("</table>")

    parser.table = None
    parser.tbody = None

    parser.leave("table")
    return True


def parse_tr(parser):
    if not parser.matcher.check(parser.line, "<tr>"):
        return False

    parser.enter("tr")

    parser.tr = E("tr")
    parser.next()

    parser.tbody.append(parser.tr)

    while True:
        if parse_td(parser):
            continue

        break

    parser.consume("</tr>")

    parser.tr = None

    parser.leave("tr")
    return True


def parse_td(parser):
    if not parser.matcher.check(parser.line, r"<td .*>"):
        return False

    # TODO: Support for `colspan="2"` found in 29/1993.

    parser.enter("td")

    parser.td = E("td")
    parser.tr.append(parser.td)

    # Only add content if the `td` is not empty, otherwise it starts adding
    # everything from the next `td`.
    if parser.peeks() == "</td>":
        parser.next()
        parser.consume("</td>")
    else:
        table_nr_title = table_title = ""

        if parser.peeks() == "<b>":
            parser.next()
            parser.consume("<b>")
            table_nr_title, table_title = get_nr_and_name(
                parser.collect_until("</b>", collect_first_line=True)
            )
            parser.td.attrib["header-style"] = "b"
        elif parser.peeks() == "<i>":
            parser.next()
            parser.consume("<i>")
            table_nr_title, table_title = get_nr_and_name(
                parser.collect_until("</i>", collect_first_line=True)
            )
            parser.td.attrib["header-style"] = "i"

        # NOTE: We don't place the `table-nr-title` in an attribute here
        # because it is unclear how it would be useful for referencing. They
        # may show up in the first row or the first column, or even the
        # non-first column of a non-first row.
        #
        # We may need a much more sophisticated way of identifying columns and
        # rows when they are changed by bills or referenced by other laws.
        if len(table_nr_title):
            parser.td.append(E("table-nr-title", "%s." % table_nr_title))

        if len(table_title):

            # Deal with styled chemical names. Happens in ákvæði til
            # bráðabirgða XII laga nr. 29/1993.
            # NOTE: The styling gets re-applied in rendering mechanism.
            if parser.peeks() == "<small>":
                extra_content = parser.collect_until("</small>")
                extra_content = extra_content.replace("<small> <sub> ", "").replace("</sub>", "")
                table_title += extra_content

            parser.td.append(E("table-title", table_title))

        content = parser.collect_until("</td>")
        parser.consume("</td>")

        add_sentences(parser.td, separate_sentences(content))

    parser.td = None

    parser.leave("td")
    return True
