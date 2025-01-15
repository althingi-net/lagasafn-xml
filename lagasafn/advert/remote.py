import re
import requests
from bs4 import BeautifulSoup
from bs4 import Comment
from datetime import datetime
from lagasafn.utils import write_xml
from lxml import etree
from os.path import isfile

ADVERT_LIST_URL = "https://www.stjornartidindi.is/AdvertList.aspx?advertTypeName=A%%20deild&load=true&posStart=%d"
ADVERT_URL = "https://www.stjornartidindi.is/Advert.aspx?RecordID=%s"


class AdvertRow:
    record_id: str
    nr: int
    year: int
    name: str
    date: datetime | None

    def __init__(self):
        self.record_id = ""
        self.nr = 0
        self.year = 0
        self.name = ""
        self.date = None


def get_advert_rows(from_date, to_date):
    """
    Retrieves advert rows from remote XML filtered by `from_date` and
    `to_date`, taking care of paging and massaging of data.
    """

    advert_rows = []
    done = False
    start_pos = 0

    print("Looking up advert list...", end="", flush=True)

    while not done:
        response = requests.get(ADVERT_LIST_URL % start_pos)
        xml_advert_list = etree.fromstring(response.content)

        remote_rows = xml_advert_list.xpath("/rows/row")
        for remote_row in remote_rows:
            cells = remote_row.findall("cell")

            # Get the info as it appears in the remote XML.
            record_id = remote_row.attrib["recordId"]
            law_id = cells[1].text
            name = cells[2].text
            date = cells[3].text

            # Massage the info for our purposes as needed.
            nr, year = re.findall(r">(\d{1,3})\/(\d{4})<", law_id)[0]
            nr = int(nr)
            year = int(year)
            date = datetime.strptime(date, "%d.%m.%Y")

            if date > to_date:
                continue
            elif date < from_date:
                done = True
                break

            advert_row = AdvertRow()
            advert_row.record_id = record_id
            advert_row.nr = nr
            advert_row.year = year
            advert_row.name = name
            advert_row.date = date

            advert_rows.append(advert_row)

        if len(remote_rows) == 0:
            done = True

        start_pos += len(remote_rows)

        print(".", end="", flush=True)

    print(" done")

    return advert_rows


def save_advert_originals(advert_rows):
    """
    Gets the relevant HTML from the given advert rows and saves them to disk if
    they don't already exist.
    """
    for advert_row in advert_rows:

        filename = "%d.%d.remote.xml" % (advert_row.year, advert_row.nr)
        fullpath = "data/adverts/remote/" + filename

        if isfile(fullpath):
            continue

        print(
            "Downloading advert %d/%d..." % (advert_row.nr, advert_row.year),
            end="",
            flush=True,
        )
        response = requests.get(ADVERT_URL % advert_row.record_id)
        content = response.content.decode("utf-8")
        print(" done")

        soup_advert = BeautifulSoup(content, "html5lib").find("html")

        # Find and remove all comments.
        # NOTE: These comments only happen in a few files and originate in
        # WordPerfect. They might be useful one day if used consistently by the
        # producers of the adverts.
        for comment in soup_advert.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        xml_doc = etree.HTML(soup_advert.__str__())

        orig_advert = xml_doc.xpath("//div[@type='STJT']")[0]

        write_xml(orig_advert, fullpath)


def update_local_adverts(from_date, to_date):
    """
    Gets adverts from the remote path and stores the original HTML content
    locally. Goes through the remote web site and stops only when it reaches a
    file that already exists locally.
    """

    advert_rows = get_advert_rows(from_date, to_date)

    save_advert_originals(advert_rows)
