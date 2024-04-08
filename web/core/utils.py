from core.exceptions import ReferenceParsingException


def fetch_nr(word):
    """
    Utility function to return the number or letter of a reference part.
    Examples:
        "3. gr." should return "3"
        "B-lið" should return "B"
    """
    if word[-4:] == "-lið":
        nr = word[: word.find("-")]
    else:
        nr = word.strip(".")

    return nr


def make_xpath(input_words: str):

    # We'll be butchering this so better make a copy.
    words = input_words.copy()

    def peek(some_list):
        """
        Utility function so that we can do this inline.
        """
        return some_list[0] if len(some_list) else ''

    xpath = ""

    translations = {
        "gr": "art",
        "tölul": "numart",
        "mgr": "subart",
    }

    while len(words):

        # Initialize.
        ent_type = ''
        ent_numbers = []

        word = words.pop(0)

        # NOTE: Don't forget to implement support for things like "3. gr. a".
        # These are not implemented yet, but should be done here.

        if word[-4:] == "-lið":
            ent_type = "*[self::numart or self::art-chapter]"
            ent_numbers.append(word[:word.find('-lið')])
        elif word in translations.keys():
            ent_type = translations[word]
            ent_numbers.append(words.pop(0))

            if peek(words) == "eða":
                words.pop(0)
                ent_numbers.append(words.pop(0))
        else:
            # Oh no! We don't know what to do!
            raise ReferenceParsingException(word)

        # Assuming something came of this...
        if len(ent_type):
            # ... construct the XPath bit and add it to the result!
            xpath += "//%s[%s]" % (
                ent_type,
                " or ".join(["@nr='%s'" % n for n in ent_numbers])
            )

    return xpath
