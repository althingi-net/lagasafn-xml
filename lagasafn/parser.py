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
from lagasafn.contenthandlers import separate_sentences
from lagasafn.contenthandlers import check_chapter
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
        self.chapter = None
        self.subchapter = None
        self.art = None
        self.art_chapter = None
        self.subart = None
        self.numart = None
        self.ambiguous_section = None
        self.footnotes = None

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
        if len(self.parse_path) < 1:
            print("ERROR: Trying to leave a path that doesn't exist.")
            return

        if self.verbosity > 0:
            print("%s<< Leaving %s at line %d" % ("  " * (len(self.parse_path)-1), self.parse_path[-1], self.lines.current_line_number))

        if guard is not None:
            if self.parse_path[-1] != guard:
                self.error("Trying to leave a path that doesn't match the guard (%s)." % guard)
                return
        self.parse_path.pop()

    def leave_if_last(self, path):
        if len(self.parse_path) > 0 and self.parse_path[-1] == path:
            self.leave()

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
        self.collection.append(string.strip())

    def uncollect(self):
        result = " ".join(self.collection).strip()
        self.collection = []
        return result

    def collect_until(self, end_string):
        # Will collect lines until the given string is found, and then return the
        # collected lines.
        done = False
        while not done:
            try:
                line = next(self.lines).strip()
            except StopIteration:
                raise Exception("ERROR: Unexpected end of file on line %d while collecting until '%s'. \nLine: '%s'" % (self.lines.current_line_number, end_string, self.line))
            if self.matcher.check(line, end_string):
                done = True
                continue
            self.collect(line)

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
        self.lines.index = current_line + 1

    def dump_state(self):
        print("Current parser state: ")
        print(" parse_path: '%s'" % ("->".join(self.parse_path)))
        print(" line: '%s'" % (self.line))
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
        if parse_chapter(parser):
            continue
        if parse_article(parser):
            continue

        # If we didn't parse a chapter or an article, we're done.
        break

    parse_end_of_law(parser)


def parse_intro(parser):
    parser.enter("intro")

    parser.scroll_until("<h2>")    # Nothing before the opening <hr/> is meaningful.

    # Parse elements in the intro.
    parse_law_title(parser)
    parse_law_number_and_date(parser)

    # We always get a <hr/> after the law number and date.    
    parser.consume("<hr/>")

    parse_procedural_links(parser)

    if parser.line == "<i>":
        # Footnotes to the law name should come inside <i> tags.
        parser.consume("<i>")
        parse_footnotes(parser)      # This will eat any footnotes associated with the title.
        parser.consume("</i>")

    parser.maybe_consume_many("<br/>")
    parse_minister_clause_footnotes(parser)
    parse_procedural_links(parser)
    parse_minister_clause_footnotes(parser)

    parser.trail_milestone("intro-finished")
    parser.leave("intro")


def parse_end_of_law(parser):
    if parser.line != "</body>":
        parser.note("Trying to parse end of file without having reached the end of the file.")
        return

    parser.enter("end-of-file")
    # Do we want to do anything here?
    parser.scroll_until("</html>")
    parser.next()
    parser.leave("end-of-file")


def parse_procedural_links(parser):
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

    if parser.line.startswith("<a href=\"https://www.althingi.is/thingstorf/thingmalalistar-eftir-thingum/ferill/"):
        parser.scroll_until("</a>")
        parser.next() # Consume </a>

    if parser.line.startswith("<a href=\"https://www.althingi.is/altext/"):
        parser.scroll_until("</a>")
        parser.next()

    parser.maybe_consume_many("<br/>")


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

    parser.leave()


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
        return

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

    # FIXME: Separating the sentences like this incorrectly parses
    # what should be a `nr-title` as a `sen.`
    parser.ambiguous_section = E("ambiguous-section")
    add_sentences(parser.ambiguous_section, separate_sentences(ambiguous_content))

    if parser.chapter is not None:
        parser.chapter.append(parser.ambiguous_section)
    else:
        parser.law.append(parser.ambiguous_section)

    parser.trail_push(parser.ambiguous_section)

    parser.leave()


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
            minister_clause = parser.collect_until("<hr/>")
            if len(minister_clause):
                parser.law.append(E("minister-clause", minister_clause))

        parser.consume("<hr/>")
        parser.maybe_consume_many("<br/>")
        parser.leave("minister-clause-footnotes")


def parse_presidential_decree_preamble(parser):
    if (
        parser.line == "<br/>"
        and parser.peek(-1).strip() == "<hr/>"
        and parser.peek(-2).strip() == "</small>"
        and parser.trail_reached("intro-finished")
        and parser.law.attrib["law-type"] == "speaker-verdict"
        and parser.peek(1).find("<img") == -1
    ):
        parser.enter("presidential-decree-preamble")
        # Sometimes, in presidential decrees ("speaker-verdict", erroneously),
        # the minister clause is followed by a preamble, which we will parse
        # into a "sen".
        # The only example of this that this guard currently catches is 7/2022.
        distance = parser.occurrence_distance(parser.lines, "<br/>")
        if distance is not None and begins_with_regular_content(parser.lines.peek()):
            preamble = parser.collect_until("<br/>")
            parser.law.append(E("sen", preamble))

        parser.leave()


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

    name_or_nr_title = parser.collect_until("</b>")

    if parser.lines.peeks() == "<b>":
        chapter_nr_title = name_or_nr_title

        # Let's see if we can figure out the number of this chapter.
        # We're going to assume the format "II. kafli" for the second
        # chapter, and "II. kafli B." for the second chapter B, and in
        # those examples, nr-titles will be "2" and "2b" respectively.
        t = strip_markers(chapter_nr_title).strip()
        maybe_nr = t[0 : t.index(".")]
        try:
            nr = str(roman.fromRoman(maybe_nr))
            roman_nr = maybe_nr
            nr_type = "roman"
        except roman.InvalidRomanNumeralError:
            nr = int(maybe_nr)
            roman_nr = None
            nr_type = "arabic"

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
        for chapter_word_check in ["kafli", "hluti", "bók"]:
            if chapter_word_check in t:
                alpha = t[t.index(chapter_word_check) + 6 :].strip(".")
                if alpha:
                    nr += alpha.lower()
        del t

        parser.scroll_until("<b>")
        chapter_name = parser.collect_until("</b>")

        parser.chapter = E.chapter(
            {"nr": str(nr), "nr-type": nr_type},
            E("nr-title", chapter_nr_title),
            E("name", chapter_name),
        )

        # Record the original Roman numeral if applicable.
        if roman_nr is not None:
            parser.chapter.attrib["roman-nr"] = roman_nr

    else:
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
        parser.leave()

    parser.law.append(parser.chapter)

    parser.trail_push(parser.chapter)

    parser.subchapter = None
    parser.consume("</b>")
    parser.maybe_consume_many("<br/>")

    while True:
        if parse_article(parser):
            continue
        #if parse_subchapter(parser):
        #    continue
        break

    parser.maybe_consume_many("<br/>")

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
    if check_chapter(parser.lines, parser.law) in ["appendix"] and parser.trail_reached(
        "intro-finished"
    ):
        # Accompanying documents vary in origin and format, and are not a
        # part of the formal legal text itself, even though legal text may
        # reference them. Parsing them is beyond the scope of this tool.
        # They always show up at the end, so at this point, our work is
        # done. We'll escape the loop and go for post-processing.
        return True
    return False


def parse_subchapter(parser):
    # Parse a subchapter.
    if check_chapter(parser.lines, parser.law) == "subchapter" and parser.trail_reached(
        "intro-finished"
    ):
        parser.enter("subchapter")

        subchapter_goo = parser.collect_until("</b>")

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

        del subchapter_goo
        del subchapter_nr
        del subchapter_name


def parse_article_chapter(parser):
    if check_chapter(
        parser.lines, parser.law
    ) == "art-chapter" and parser.trail_reached("intro-finished"):
        parser.enter("art-chapter")

        # Parse an article chapter.
        art_chapter_goo = parser.collect_until("</b>")

        # Check if there's a name to the article chapter.
        try:
            art_chapter_nr, art_chapter_name = art_chapter_goo.strip(".").split(".")
            art_chapter_name = art_chapter_name.strip()
        except:
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
        if parser.art.find("art-chapter") is not None:
            parser.art.find("art-chapter").getparent().append(parser.art_chapter)
        elif parser.subart is not None:
            parser.subart.append(parser.art_chapter)
        elif parser.art is not None:
            parser.art.append(parser.art_chapter)

        # Check if the `art-chapter` contains text content which is not
        # contained in a `subart` or `numart` below the `art-chapter`.
        # This is only known to occur in 7. gr. laga nr. 90/2003.
        #
        # NOTE: We only check for one "paragraph", since we are currently
        # not aware of there being a case where there are more. The
        # children of `art-chapter`s are almost always `numart`s and when
        # we find text like this, it is presumably just one paragraph or a
        # short preface to a list of `numart` that follow.
        if begins_with_regular_content(parser.peek(2)):
            # Scroll over the break the belongs to the `art-chapter`.
            parser.scroll_until("<br/>")
            content = parser.collect_until("<br/>")

            sens = separate_sentences(strip_links(content))
            add_sentences(parser.art_chapter, sens)

        parser.trail_push(parser.art_chapter)

        parser.leave()


def parse_ambiguous_chapter(parser):
    if check_chapter(parser.lines, parser.law) == "ambiguous" and parser.trail_reached(
        "intro-finished"
    ):
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

        if parser.subart is not None:
            parser.subart.append(ambiguous_bold_text)
        elif parser.art is not None:
            parser.art.append(ambiguous_bold_text)
        elif parser.chapter is not None:
            parser.chapter.append(ambiguous_bold_text)
        else:
            parser.law.append(ambiguous_bold_text)

        parser.trail_push(ambiguous_bold_text)

        parser.leave()


def parse_sentence_with_title(parser):
    if (
        parser.peeks(0) == "<i>"
        and parser.peeks(2) == "</i>"
        and parser.trail_reached("intro-finished")
    ):
        parser.enter("sen-with-title")
        # Parse a sentence with a title. These are rare, but occur in 3.
        # gr. laga nr. 55/2009. Usually they are numbered, parsed as
        # numarts instead, but not here.

        # In 3. gr. laga nr. 55/2009, sentences with titles have the
        # opening marks located right before the <i> tag, meaning that we
        # have no proper place to put it in. We'll place it in the
        # beginning of the sen-title instead. There can be more than one,
        # so we'll append continuously until we run out of opening marks.

        sen_title_text = ""
        back_peek = parser.peeks(-1)
        while len(back_peek) > 0 and back_peek[-1] == "[":
            sen_title_text += "["
            back_peek = back_peek[0:-1]

        sen_title_text += parser.collect_until("</i>")
        content = parser.collect_until("<br/>")
        if parser.subart is not None:
            sen_title = E("sen-title", sen_title_text)
            parser.subart.append(sen_title)

            add_sentences(parser.subart, separate_sentences(content))

            parser.trail_push(sen_title)

        parser.leave()


def parse_article(parser):
    # Articles have navigation spans on them with "G???" IDs with their number.
    # We'll skip over them, as long as we are sure that after them we have the 
    # begining of an article.
    if parser.line.startswith("<span id=\"G") and parser.matcher.check(parser.peeks(2), r'<img .+ src=".*sk.jpg" .+\/>'):
        parser.next()   # Consume <span id="G???">
        parser.next()   # Consume </span>
    else:
        return False

    # Is this redundant?
    if not parser.matcher.check(parser.peeks(0), r'<img .+ src=".*sk.jpg" .+\/>'):
        return False

    parser.enter("art")

    # Parse an article.
    parser.scroll_until("<b>")
    art_nr_title = parser.collect_until("</b>")

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
    if parser.peeks().find("<a ") == 0 and parser.peeks(3) == "</a>":
        art_title_link = parser.collect_until("</a>")
        art_nr_title = "%s %s </a>" % (art_nr_title, art_title_link)

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
    else:
        parser.law.append(parser.art)

    # Check if the next line is an <em>, because if so, then the
    # article has a name title and we need to grab it. Note that not
    # all articles have names.
    if parser.peeks() == "<em>":
        parser.scroll_until("<em>")
        art_name = parser.collect_until("</em>")
        parser.consume("</em>")
        parser.art.append(E("name", strip_links(art_name)))

    # Another way to denote an article's name is by immediately
    # following it with bold text. This is very rare but does occur.
    elif parser.peeks() == "<b>" and parser.peeks(2) != "Ákvæði til bráðabirgða.":
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

        parser.art.append(
            E("name", strip_links(art_name), {"original-ui-style": "bold"})
        )

    # Check if the article is empty aside from markers that need to be
    # included in the article <nr-title> or <name> (depending on
    # whether <name> exists at all).
    while parser.peeks() in ["…", "]"]:
        marker = parser.collect_until("</sup>")
        parser.art.getchildren()[-1].text += " " + marker + " </sup>"

    parser.trail_push(parser.art)

    # There can be no current subarticle or article chapter if we've
    # just discovered a new article.
    parser.subart = None
    parser.art_chapter = None

    parser.maybe_consume_many("<br/>")

    while True:
        if parse_numerical_article(parser):
            continue
        if parse_subarticle(parser):
            continue
        break

    parser.leave()

    return False


def parse_subarticle(parser):
    if not parser.matcher.check(
        parser.line, r'<img .+ id="[GB](\d+)[A-Z]?M(\d+)" src=".*hk.jpg" .+\/>'
    ):
        return False

    # Parse a subart.
    parser.enter("subart")

    art_nr, subart_nr = parser.matcher.result()

    # Check how far we are from the typical subart end.
    linecount_to_br = parser.occurrence_distance(parser.lines, r"<br/>")

    # Check if there's a table inside the subarticle.
    linecount_to_table = parser.occurrence_distance(
        parser.lines, r"<\/table>", linecount_to_br
    )

    subart_name = ""
    # If a table is found inside the subarticle, we'll want to end the
    # subarticle when the table ends.
    if linecount_to_table is not None:
        # We must append the string '</table>' because it gets left
        # behind by the collet_until function.
        content = parser.collect_until("</table>") + "</table>"
    else:
        # Everything is normal.
        content = parser.collect_until("<br/>")

    parser.subart = E("subart", {"nr": subart_nr})

    if parser.matcher.check(content, "^<b>(.*)</b>(.*)<i>(.*)</i>"):
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

    elif parser.matcher.check(content, r"^((\[\s)?<i>(.*)</i>)"):
        # Check for definitions in subarts. (Example: 153c, 7/1998)

        raw_definition, before, definition = parser.matcher.result()

        # Fix data so that we know how to treat it.
        definition = definition.strip()
        if before is None:
            before = ""

        # Clear out the HTML content describing the definition.
        content = content.replace(raw_definition, before + definition.strip())

        sens = separate_sentences(strip_links(content))
        add_sentences(parser.subart, sens)

        added_sens = parser.subart.findall("sen")

        # Something strange is going on if these are different, so we'll throw
        # an error, just in case.
        if len(sens) != len(added_sens):
            raise Exception("Lists `sens` and `added_sens` should be same length.")

        # It is also unexpected to see a definition being applied when there
        # already is one.
        if "definition" in parser.subart.attrib:
            raise Exception("Unexpectedly existing definition in `subart`.")

        # Add the definition to the subart.
        parser.subart.attrib["definition"] = definition

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
    elif parser.chapter is not None:
        parser.chapter.append(parser.subart)
    else:
        # An occasional text, mostly advertisements, declarations,
        # edicts and at least one really ancient law, contain only
        # subarticles. Possibly in a chapter, and possibly not.
        parser.law.append(parser.subart)

    parser.maybe_consume_many("<br/>")

    parser.trail_push(parser.subart)
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
        parser.matcher.check(parser.line, r'<span id="[BG](\d+)([0-9A-Z]*)L(\d+)">')
        or (parser.matcher.check(parser.line, "<span>") and parser.peeks() != "</span>")
    ):
        return

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

    # Support for numart ranges, which are only known to occur when
    # many numarts have been removed. This occurs for example in 145.
    # gr. laga nr. 108/2007.
    if parser.matcher.check(numart_nr, r"(\d+)\.–(\d+)"):
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
            if numart_nr.lower() in ["a", "i", "—", "–"] or (
                numart_nr.isdigit() and int(numart_nr) == 1
            ):
                # A new list has started within the one we were
                # already processing, which we can tell because there
                # was a `numart` before this one, but this `numart`
                # says it's at the beginning, being either 'a' or 1.
                # In this case, we'll choose the previous `numart` as
                # the parent, so that this new list will be inside the
                # previous one.
                parent = prev_numart
            else:
                # A different list is being handled now, but it's not
                # starting at the beginning (is neither 'a' nor 1).
                # This means that we've been dealing with a sub-list
                # which has now finished, so we want to continue
                # appending this `numart` to the parent of the parent
                # of the list we've been working on recently, which is
                # the same parent as the nodes that came before we
                # started the sub-list.
                parent = prev_numart.getparent().getparent()

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
        elif parser.subart is not None:
            parent = parser.subart
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
    if numart_nr[0].isdigit():
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
            if prev_numart is None or prev_numart.attrib["nr"] != "h" or special_roman:
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
    numart_nr_title = parser.collect_until("</span>")

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

    if parser.peeks() == "<i>":
        # Looks like this numerical article has a name.
        parser.scroll_until("<i>")

        # Note that this gets inserted **after** we add the sentences
        # with `add_sentences` below.
        numart_name = parser.collect_until("</i>")

        # This is only known to happen in 37. tölul. 1. mgr. 5. gr. laga nr. 70/2022.
        # The name of a numerical article is contained in two "<i>"
        # tags separated with an "og".
        if parser.lines.peeks() == "og" and parser.lines.peeks(2) == "<i>":
            addendum = parser.collect_until("</i>").replace("<i> ", "")
            numart_name += " " + addendum
    else:
        numart_name = None

    # Read in the remainder of the content.
    content = parser.collect_until("<br/>")

    # Split the content into sentences.
    sens = separate_sentences(strip_links(content))

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

        # Add the title info to the `numart`.
        parser.numart.insert(0, E("nr-title", numart_nr_title))
        if numart_name is not None:
            # Inserted immediately after the `nr-title`, so 1.
            parser.numart.insert(1, E("name", numart_name))

        # Handle extra paragraphs that we don't know where to place.
        while begins_with_regular_content(parser.lines.peek()):
            # When regular (text) content immediately follows a
            # numart, and not a new location like an article,
            # subarticle or another numart, we must determine its
            # nature. We'll start by finding the content.
            extra_content = parser.collect_until("<br/>")

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

    parser.trail_push(parser.numart)
    parser.leave()


def parse_table(parser):
    if not parser.matcher.check(parser.line, "<table"):
        return

    parser.enter("table")
    # Parse a stray table, that we haven't run across inside a
    # subarticle. We'll append it to previously parsed thing. The
    # table width is only for consistency with the typical input.

    content = (
        '<table width="100%">'
        + parser.collect_until("</table>")
        + "</table>"
    )
    sen = separate_sentences(content).pop()

    if parser.subart is not None:
        add_sentences(parser.subart, [sen])
    elif parser.art is not None:
        add_sentences(parser.art, [sen])

    parser.leave()


def postprocess_law(parser):
    parser.enter("postprocess")
    # Turn HTML tables, currently encoded into HTML characters, into properly
    # structured and clean XML tables with properly presented content.
    #
    # We have no reason to create a table structure different from the HTML
    # structure. We'll just make sure that the data is sanitized properly and
    # that there is no useless information, by recreating the table in XML.
    # This way, it'll be quite easy for a layout engine in a browser to render
    # it correctly.
    for sen in parser.law.xpath("//sen"):
        if sen.text.find("<table ") == 0:
            # The XML table that we are going to produce.
            table = E("table")

            # The HTML table from which we're fetching information.
            html_table = etree.HTML(sen.text).find("body/table/tbody")

            # Find the rows and headers inside the HTML.
            rows = super_iter(html_table)

            # If the table has a header, it will typically be the top row
            # (exception explained below). We'll check the first column of the
            # top row to check whether the headers are designated via <b> tags
            # or <i> tags. If no such tags are found, we are forced to
            # conclude that there is no header. This is also not always true
            # (also explained below).
            #
            # TODO: In temporary clause XII in law nr. 29/1993, tables are
            # found with three rows of headers. These are currently not
            # supported and result in missing data.
            #
            # TODO: In 5. mgr. 19. gr. laga nr. 87/2004, headers are not
            # stylized at all, thereby making them virtually indistinguishable
            # from headers. These are currently unsupported at the moment,
            # meaning they will be interpreted as if they were data cells.
            #
            # TODO: In 96. gr. laga nr. 55/1991, bold and italic items seem to
            # be skipped altogether. This must be the code's fault, somehow.

            toprow = next(rows)
            if toprow[0].find("b") is not None:
                header_style = "b"
            elif toprow[0].find("i") is not None:
                header_style = "i"
            else:
                header_style = ""

            # If we've determined that the table has a header at all...
            if header_style:
                thead = E("thead", E("tr"))
                table.append(thead)

                # Add headers to the XML table.
                for col in toprow:
                    header = col.find(header_style).text.strip()
                    if header_style != "b":
                        # Headers are normally bold, but there are exceptions.
                        # We'll only designate a header style when we run into
                        # an exception to the rule.
                        thead.find("tr").append(
                            E("th", header, {"header-style": header_style})
                        )
                    else:
                        thead.find("tr").append(E("th", header))
            else:
                # Roll one back because we've decided that the first row is
                # not a header after all.
                rows.prev()

            tbody = E("tbody")
            table.append(tbody)

            # Add rows.
            for row in rows:
                tr = E("tr")
                tbody.append(tr)
                for col in row:
                    tr.append(E("td", col.text.strip()))

            # Replace HTML-encoded text with XML table.
            sen.text = None
            sen.append(table)

    parser.leave()
