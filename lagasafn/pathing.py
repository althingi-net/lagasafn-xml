from lagasafn.exceptions import ReferenceParsingException


def make_xpath_from_node(node):
    """
    Generates a distinct XPath location for a given node, including the node's
    names and attributes.

    IMPORTANT: This function must never return a string with double quotes,
    because it will be stored in XML attributes which will themselves be using
    double quotes as value delimiters.
    """

    # Initialize a list to store parts of the XPath as we build it.
    xpath_parts = []

    while node is not None and node.getparent() is not None:
        # Extract and format the current node's attributes into XPath syntax.
        attrib_parts = []
        for wanted_attrib in ["nr", "ultimate-nr", "sub-paragraph-nr"]:
            if wanted_attrib in node.attrib:
                # IMPORTANT: Single quotes for values, not double quotes.
                attrib_parts.append(
                    "@%s='%s'" % (wanted_attrib, node.attrib[wanted_attrib])
                )

        attributes_xpath = " and ".join(attrib_parts)

        # Construct XPath part for current node, with attributes if any.
        if attributes_xpath:
            xpath_part = f"{node.tag}[{attributes_xpath}]"
        else:
            xpath_part = node.tag

        # Insert the constructed XPath part at the beginning of the list.
        xpath_parts.insert(0, xpath_part)

        # Move to the parent node for the next iteration.
        node = node.getparent()

    # Join all parts of the XPath with slashes to form the final XPath string.
    return "/".join(xpath_parts)


def make_xpath_from_reference(input_words: str):

    # We'll be butchering this so better make a copy.
    words = input_words.copy()

    def peek(some_list):
        """
        Utility function so that we can do this inline.
        """
        return some_list[0] if len(some_list) else ""

    xpath = ""

    translations = {
        "gr": "art",
        "tölul": "numart",
        "mgr": "subart",
    }

    while len(words):

        # Initialize.
        ent_type = ""
        ent_numbers = []

        word = words.pop(0)

        # NOTE: Don't forget to implement support for things like "3. gr. a".
        # These are not implemented yet, but should be done here.

        if word[-4:] == "-lið":
            ent_type = "*[self::numart or self::art-chapter]"
            ent_numbers.append(word[: word.find("-lið")])
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
                " or ".join(["@nr='%s'" % n for n in ent_numbers]),
            )

    return xpath
