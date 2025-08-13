import re
import requests
from bs4 import BeautifulSoup
from bs4 import Comment
from datetime import datetime
from lagasafn.island_is import island_is_query
from lagasafn.utils import write_xml
from lxml import etree
from os.path import isfile

ADVERT_URL = "https://island.is/stjornartidindi/nr/%s"


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


def get_advert_rows(from_date: datetime, to_date: datetime):
    """
    Retrieves advert rows from remote XML filtered by `from_date` and
    `to_date`, taking care of paging and massaging of data.
    """

    def get_journal(from_date: datetime, to_date: datetime, page: int):
        return island_is_query(
            "Adverts",
            {
                "department": ["a-deild"],
                "category": [""],
                "involvedParty": [""],
                "type": [""],
                "search": "",
                "dateFrom": from_date.isoformat(),
                "dateTo": to_date.isoformat(),
                "page": page,
            }
        )["officialJournalOfIcelandAdverts"]

    advert_rows = []
    done = False
    page = 1

    # Starts at 1, because there's always a minimum of 1 page. Gets updated
    # upon learning that there are more.
    total_pages = 1

    print("Looking up advert list...", end="", flush=True)

    # I was here. Need to modify this so that it uses `island_is_query` which can be found in `graphqltest.py`.
    # Should be easy to convert so that it uses the GraphQL-ish data instead.
    # Then I need to modify `save_advert_originals` below and see just how
    # much updating of parsing code is needed.

    # Temp for testing.
    from_date = datetime(2024, 1, 1)

    while page <= total_pages:
        journal = get_journal(from_date, to_date, page)
        total_pages = journal["paging"]["totalPages"]
        for remote_row in journal["adverts"]:
            record_id = remote_row["id"]
            law_id = remote_row["publicationNumber"]["full"]
            name = remote_row["title"]
            date = datetime.fromisoformat(remote_row["publicationDate"])

            # Massage the info for our purposes as needed.
            nr, year = law_id.split("/")
            nr = int(nr)
            year = int(year)

            advert_row = AdvertRow()
            advert_row.record_id = record_id
            advert_row.nr = nr
            advert_row.year = year
            advert_row.name = name
            advert_row.date = date

            advert_rows.append(advert_row)

            # Turn to the next page.
            page += 1

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
        for comment in soup_advert.find_all(
            string=lambda text: isinstance(text, Comment)
        ):
            comment.extract()

        xml_doc = etree.HTML(soup_advert.__str__())

        # I was here. The content seems to have completely changed. Not sure how, when, or even if to proceed.
        import ipdb; ipdb.set_trace()
        orig_advert = xml_doc.xpath("//div[@type='STJT']")[0]
        orig_advert.attrib["record-id"] = advert_row.record_id

        write_xml(orig_advert, fullpath, skip_strip=True)


def update_local_adverts(from_date, to_date):
    """
    Gets adverts from the remote path and stores the original HTML content
    locally. Goes through the remote web site and stops only when it reaches a
    file that already exists locally.
    """

    advert_rows = get_advert_rows(from_date, to_date)

    save_advert_originals(advert_rows)
