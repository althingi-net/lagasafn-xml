import os
from lagasafn.settings import DATA_DIR
from lagasafn import settings
from lxml import etree
from lxml.builder import E
from lagasafn.contenthandlers import strip_markers
from lagasafn.contenthandlers import add_sentences
from lagasafn.contenthandlers import separate_sentences
from lagasafn.utils import determine_month
from lagasafn.utils import strip_links
from lagasafn.utils import super_iter
from lagasafn.utils import Trail
from lagasafn.utils import Matcher

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

        # Objects that help us figure out the current state of affairs. These
        # variables are used between iterations, meaning that whenever possible,
        # their values should make sense at the end of the processing of a
        # particular line or clause. Never put nonsense into them because it will
        # completely confuse the processing elsewhere.
        self.line = None
        self.chapter = None
        self.subchapter = None
        self.art = None
        self.art_chapter = None
        self.subart = None
        self.numart = None
        self.ambiguous_section = None

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

    def peek(self, n=1):
        return self.lines.peek(n)
    
    def peeks(self, n=1):
        return self.lines.peeks(n)

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

    # Will collect lines until the given string is found, and then return the
    # collected lines.
    def collect_until(self, lines, end_string):
        done = False
        while not done:
            line = next(lines).strip()
            if self.matcher.check(line, end_string):
                done = True
                continue
            self.collect(line)

        total = self.uncollect().strip()

        return total
    

    # Checks how much iteration is required to hit a line that matches the
    # given regex. Optional limit parameter allows limiting search to a specific
    # number of lines into the future.
    def occurrence_distance(self, lines, regex, limit=None):
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



####### Individual section parser functions below:

def parse_law_title(parser):
    if parser.line != "<h2>":
        return

    # Parse law name.
    law_name = strip_links(parser.collect_until(parser.lines, "</h2>"))

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


def parse_law_number_and_date(parser):
    if parser.line != "<strong>" or parser.trail_last().tag != "name":
        return

    # Parse the num and date, which appears directly below the law name.
    num_and_date = parser.collect_until(parser.lines, "</strong>")

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


def parse_ambiguous_section(parser):
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
    ambiguous_content = parser.collect_until(parser.lines, "</em>")

    # FIXME: Separating the sentences like this incorrectly parses
    # what should be a `nr-title` as a `sen.`
    parser.ambiguous_section = E("ambiguous-section")
    add_sentences(parser.ambiguous_section, separate_sentences(ambiguous_content))

    if parser.chapter is not None:
        parser.chapter.append(parser.ambiguous_section)
    else:
        parser.law.append(parser.ambiguous_section)

    parser.trail_push(parser.ambiguous_section)


def postprocess_law(parser):
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
