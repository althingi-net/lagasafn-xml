from copy import deepcopy
from os import makedirs

from colorama import Fore, Style, init
from lxml import etree
from lxml.builder import E
from lagasafn.constants import XML_BASE_DIR
from lagasafn.diff_patch_utils import do_diff_str
from lagasafn.exceptions import AdvertException
from lagasafn.models.law import Law, LawManager
from lagasafn.settings import CURRENT_PARLIAMENT_VERSION
from lagasafn.utils import write_xml

# Initialize colorama for cross-platform color support
init(autoreset=True)


def apply_intents_to_law(
    law_identifier: str,
    intents: list,
    advert_identifier: str,
    codex_version: str = None,
):
    """
    Apply multiple intents to a single law and save once at the end.

    Args:
        law_identifier: Identifier of the law to modify
        intents: List of intent XML elements to apply
        advert_identifier: Identifier of the advert containing these intents
        codex_version: Parliament version to use
        enact_date: Enactment date to set in the law XML

    Returns:
        bool: True if successful, False otherwise
    """
    if codex_version is None:
        codex_version = CURRENT_PARLIAMENT_VERSION

    law = Law(law_identifier, codex_version)
    law_xml = law.xml().getroot()

    for intent in intents:
        action = intent.get("action")
        action_xpath = intent.get("action-xpath")
        print(f"Applying {action} intent to {law_identifier}")
        if action == "add":
            _apply_add_intent(intent, law_xml, action_xpath)
        elif action == "add_text":
            _apply_add_text_intent(intent, law_xml, action_xpath)
        elif action == "append":
            _apply_append_intent(intent, law_xml, action_xpath)
        elif action == "append_text":
            _apply_append_text_intent(intent, law_xml, action_xpath)
        elif action == "prepend_text":
            _apply_prepend_text_intent(intent, law_xml, action_xpath)
        elif action == "edit":
            _apply_edit_intent(intent, law_xml, action_xpath)
        elif action == "delete":
            _apply_delete_intent(intent, law_xml, action_xpath)
        elif action == "delete_text":
            _apply_delete_text_intent(intent, law_xml, action_xpath)
        elif action == "replace":
            _apply_replace_intent(intent, law_xml, action_xpath)
        elif action == "replace_text":
            _apply_replace_text_intent(intent, law_xml, action_xpath, advert_identifier)
        elif action == "repeal":
            _apply_repeal_intent(intent, law_xml, advert_identifier)
        else:
            print(f"Unknown action: {action}")
            continue

        # Diff the article with the next codex version after applying the intent
        _diff_article_with_next_version(
            law_identifier, law_xml, action_xpath, codex_version
        )

    applied_dir = f"{XML_BASE_DIR}/applied/{codex_version}"
    makedirs(applied_dir, exist_ok=True)

    applied_filename = (
        f"{applied_dir}/{law.year}.{law.nr}-{advert_identifier.replace('/', '.')}.xml"
    )

    with open(applied_filename, "w", encoding="utf-8") as f:
        f.write(write_xml(law_xml))

    print(
        f"Applied {len(intents)} intents from advert {advert_identifier} to law {law_identifier}"
    )

    return True


def _apply_add_intent(intent_xml, law_xml, action_xpath):
    """Apply an 'add' intent to the law XML.

    Adds content as children of the target element, inserting in the correct
    position based on the target's XSD schema structure.
    """

    # Find the target location
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the content to add from the intent's <inner> element
    inner_elem = intent_xml.find("inner")
    # Get all child elements from inner
    inner_content = inner_elem.getchildren()

    for target in targets:
        target_tag = target.tag

        # Define which elements should come after the main content for each target type
        # Based on XSD schema structure - elements after choice groups or main content
        elements_after_content = {
            "art": ["footnotes", "unspecified-ranges", "ambiguous-bold-text"],
            "chapter": [],  # chapter's choice group includes footnotes
            "subchapter": ["footnotes"],
            "art-chapter": [],  # just paragraphs and numart
            "subart": ["appendix-part", "footnotes"],
        }

        # Get the list of elements that come after main content for this target type
        after_content = elements_after_content.get(target_tag, ["footnotes"])

        for child in inner_content:
            # Create a deep copy to avoid moving the element
            new_child = deepcopy(child)

            # Find first element that comes after the main content area
            insert_position = None
            for i, existing_child in enumerate(target):
                if existing_child.tag in after_content:
                    insert_position = i
                    break

            if insert_position is not None:
                # Insert before the first "after content" element
                target.insert(insert_position, new_child)
            else:
                # No "after content" elements found, append at the end
                target.append(new_child)


def _apply_add_text_intent(intent_xml, law_xml, action_xpath):
    """Apply an 'add_text' intent to the law XML.

    Always adds text to the last element that can contain text within the target.
    """

    # Find the target location
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to add from the intent
    text_elem = intent_xml.find("text-to")
    if text_elem is not None:
        text_to_add = text_elem.text or ""

        # Elements that can have direct text content according to XSD
        elements_with_text_content = {
            "sen",
            "ambiguous-bold-text",
            "definition",
            "name",
        }

        for target in targets:
            # Always find the last element that can contain text (including target itself)
            text_element = None

            # Check if target itself can have text
            if target.tag in elements_with_text_content:
                text_element = target
            else:
                # Find the last sentence within the target
                sentences = target.findall(".//sen")
                if sentences:
                    text_element = sentences[-1]

            if text_element is not None:
                # Add text to the found element
                if text_element.text:
                    existing_text = text_element.text.rstrip()
                    if existing_text.endswith("."):
                        existing_text = existing_text[:-1]
                    text_element.text = f"{existing_text} {text_to_add}"
                else:
                    text_element.text = text_to_add
    else:
        print("No text element found for add_text intent")


def _apply_prepend_text_intent(intent_xml, law_xml, action_xpath):
    """Apply a 'prepend_text' intent to the law XML.

    Always prepends text to the first element that can contain text within the target.
    """

    # Find the target location
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to prepend from the intent
    text_elem = intent_xml.find("text-to")
    if text_elem is not None:
        text_to_add = text_elem.text or ""

        # Elements that can have direct text content according to XSD
        elements_with_text_content = {
            "sen",
            "ambiguous-bold-text",
            "definition",
            "name",
        }

        for target in targets:
            # Always find the first element that can contain text (including target itself)
            text_element = None

            # Check if target itself can have text
            if target.tag in elements_with_text_content:
                text_element = target
            else:
                # Find the first sentence within the target
                first_sen = target.find(".//sen")
                if first_sen is not None:
                    text_element = first_sen

            if text_element is not None:
                # Prepend text to the found element
                if text_element.text:
                    text_element.text = f"{text_to_add}{text_element.text}"
                else:
                    text_element.text = text_to_add
    else:
        print("No text element found for prepend_text intent")


def _apply_append_text_intent(intent_xml, law_xml, action_xpath):
    """Apply an 'append_text' intent to the law XML.

    Always appends text to the last element that can contain text within the target.
    """

    # Find the target location
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to append from the intent
    text_elem = intent_xml.find("text-to")
    if text_elem is not None:
        text_to_add = text_elem.text or ""

        # Elements that can have direct text content according to XSD
        elements_with_text_content = {
            "sen",
            "ambiguous-bold-text",
            "definition",
            "name",
        }

        for target in targets:
            # Always find the last element that can contain text (including target itself)
            text_element = None

            # Check if target itself can have text
            if target.tag in elements_with_text_content:
                text_element = target
            else:
                # Find the last sentence within the target
                sentences = target.findall(".//sen")
                if sentences:
                    text_element = sentences[-1]

            if text_element is not None:
                # Append text to the found element
                if text_element.text:
                    text_element.text = f"{text_element.text}{text_to_add}"
                else:
                    text_element.text = text_to_add
    else:
        print("No text element found for append_text intent")


def _apply_append_intent(intent_xml, law_xml, action_xpath):
    """Apply an 'append' intent to the law XML."""

    # Find the target location
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the content to append from the intent's <inner> element
    inner_elem = intent_xml.find("inner")
    # Get all child elements from inner
    inner_content = inner_elem.getchildren()

    for target in targets:
        # For each child element in inner, append it after the target
        for child in inner_content:
            # Create a deep copy to avoid moving the element
            new_child = deepcopy(child)

            # Insert the new content after the target element
            parent = target.getparent()

            # Find the index of the target in its parent
            target_index = list(parent).index(target)
            # Insert after the target
            parent.insert(target_index + 1, new_child)


def _apply_repeal_intent(intent_xml, law_xml, advert_identifier=None):
    """Apply a 'repeal' intent to the law XML."""

    # Get the advert article number from the grandparent advert-art element
    advert_art_nr = intent_xml.getparent().getparent().get("nr")

    # Create the repeal text
    repeal_text = f"Felld úr gildi skv. l. {advert_identifier}, {advert_art_nr}. gr."

    # Clear all content except the basic structure
    # Keep only: law, name, num-and-date, and minister-clause
    elements_to_keep = ["name", "num-and-date"]

    # Remove all elements except the ones we want to keep
    for child in list(law_xml):
        if child.tag not in elements_to_keep:
            law_xml.remove(child)

    # Update or create the minister-clause with repeal information
    minister_clause = law_xml.find("minister-clause")
    if minister_clause is not None:
        minister_clause.text = repeal_text
    else:
        # Create minister-clause if it doesn't exist
        minister_clause = E("minister-clause", repeal_text)
        law_xml.append(minister_clause)


def _apply_edit_intent(intent_xml, law_xml, action_xpath):
    """Apply an 'edit' intent to the law XML."""
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the new text from the intent
    text_to_elem = intent_xml.find("text-to")
    if text_to_elem is not None:
        new_text = text_to_elem.text or ""

        for target in targets:
            target.text = new_text


def _apply_delete_intent(intent_xml, law_xml, action_xpath):
    """Apply a 'delete' intent to the law XML."""

    # Use action-xpath if available, otherwise fall back to address xpath
    if not action_xpath:
        print("No action xpath - nothing to delete")
        return

    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Remove the targets
    for target in targets:
        parent = target.getparent()
        if parent is not None:
            parent.remove(target)


def _apply_delete_text_intent(intent_xml, law_xml, action_xpath):
    """Apply a 'delete_text' intent to the law XML.

    Removes specified text from target elements and their children recursively.
    """
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to delete from the intent
    text_from_elem = intent_xml.find("text-from")
    if text_from_elem is None:
        print("No text-from element found for delete_text intent")
        return

    text_to_delete = text_from_elem.text or ""
    if not text_to_delete:
        print("Empty text-to-delete specified for delete_text intent")
        return

    for target in targets:
        # Remove text from the target element
        if target.text and text_to_delete in target.text:
            target.text = target.text.replace(text_to_delete, "")

        # Also remove text from tail if it exists
        if target.tail and text_to_delete in target.tail:
            target.tail = target.tail.replace(text_to_delete, "")

        # Remove text in all child elements recursively
        for child in target.iter():
            if child.text and text_to_delete in child.text:
                child.text = child.text.replace(text_to_delete, "")
            if child.tail and text_to_delete in child.tail:
                child.tail = child.tail.replace(text_to_delete, "")


def _apply_replace_intent(intent_xml, law_xml, action_xpath):
    """Apply a 'replace' intent to the law XML."""
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to replace and the replacement text
    text_from_elem = intent_xml.find("text-from")
    text_to_elem = intent_xml.find("text-to")

    if text_from_elem is not None and text_to_elem is not None:
        old_text = text_from_elem.text or ""
        new_text = text_to_elem.text or ""

        for target in targets:
            if target.text and old_text in target.text:
                target.text = target.text.replace(old_text, new_text)
            elif target.text is None:
                target.text = new_text


def _apply_replace_text_intent(intent_xml, law_xml, action_xpath):
    """Apply a 'replace_text' intent to the law XML."""
    targets = law_xml.xpath(action_xpath)
    if not targets:
        print(f"No targets found for xpath: {action_xpath}")
        return

    # Get the text to replace from and to
    text_from_elem = intent_xml.find("text-from")
    text_to_elem = intent_xml.find("text-to")

    if text_from_elem is not None and text_to_elem is not None:
        old_text = text_from_elem.text or ""
        new_text = text_to_elem.text or ""
        for target in targets:
            # Replace text in the target element
            if target.text and old_text in target.text:
                target.text = target.text.replace(old_text, new_text)
            elif target.text is None:
                target.text = new_text

            # Also replace text in tail if it exists
            if target.tail and old_text in target.tail:
                target.tail = target.tail.replace(old_text, new_text)

            # Replace text in all child elements recursively
            for child in target.iter():
                if child.text and old_text in child.text:
                    child.text = child.text.replace(old_text, new_text)
                if child.tail and old_text in child.tail:
                    child.tail = child.tail.replace(old_text, new_text)
    else:
        print("No text-from or text-to found for replace_text intent")


def _find_parent_article(target_element):
    """
    Find the parent article element that contains the target element.
    Returns the element itself if it is an article, or None if no article is found.
    """
    current = target_element
    while current is not None:
        if current.tag == "art":
            return current
        current = current.getparent()
    return None


def _find_parent_chapter(target_element):
    """
    Find the parent chapter element that contains the target element.
    Returns the element itself if it is a chapter, or None if no chapter is found.
    """
    current = target_element
    while current is not None:
        if current.tag == "chapter":
            return current
        current = current.getparent()
    return None


def _extract_element_xml(element):
    """
    Extract an element (article, chapter, etc.) and return it as a standalone XML string.
    """
    # Create a deep copy to avoid modifying the original
    element_copy = deepcopy(element)
    # Indent the copy to ensure proper formatting
    etree.indent(element_copy, space="  ")
    # Convert to string with pretty printing
    return etree.tostring(element_copy, pretty_print=True, encoding="unicode")


def _diff_article_with_next_version(
    law_identifier, law_xml, action_xpath, codex_version
):
    """
    After applying an intent, diff the affected article with the same article
    from the next codex version.

    Raises:
        AdvertException: If the diff cannot be performed (no action_xpath, no targets,
            no article found, no next codex version, article not found in next version, etc.)
    """
    if not action_xpath:
        raise AdvertException(
            f"Cannot diff: no action_xpath provided for law {law_identifier}"
        )

    # Find the target element(s) from the action xpath
    targets = law_xml.xpath(action_xpath)
    if not targets:
        raise AdvertException(
            f"Cannot diff: no targets found for xpath '{action_xpath}' in law {law_identifier}"
        )

    # Find the article or chapter containing the first target
    target = targets[0]

    # Check if target is itself a chapter or article
    diff_element = None
    element_type = None
    element_nr = None

    if target.tag == "art":
        diff_element = target
        element_type = "article"
        element_nr = target.get("nr")
    elif target.tag == "chapter":
        diff_element = target
        element_type = "chapter"
        element_nr = target.get("nr")
    else:
        # Try to find parent article or chapter
        article = _find_parent_article(target)
        if article is not None:
            diff_element = article
            element_type = "article"
            element_nr = article.get("nr")
        else:
            # Try to find parent chapter
            chapter = _find_parent_chapter(target)
            if chapter is not None:
                diff_element = chapter
                element_type = "chapter"
                element_nr = chapter.get("nr")

    print(
        f"  DEBUG: Diff element = {diff_element}, type = {element_type}, nr = {element_nr}"
    )

    if diff_element is None:
        # No article or chapter found
        current = target
        level = 0
        parent_chain = []
        while current is not None and level < 10:
            tag_info = f"{current.tag}"
            if current.get("nr"):
                tag_info += f" (nr={current.get('nr')})"
            parent_chain.append(tag_info)
            print(f"    Level {level}: {tag_info}")
            current = current.getparent()
            level += 1
        raise AdvertException(
            f"Cannot diff: no article or chapter found for target element '{target.tag}' "
            f"in law {law_identifier}. Parent chain: {' -> '.join(parent_chain)}"
        )

    # Get the next codex version
    next_codex_version = LawManager.get_next_codex_version(codex_version)
    if next_codex_version is None:
        raise AdvertException(
            f"Cannot diff: no next codex version available (current: {codex_version})"
        )

    # Load the same law from the next codex version
    next_law = Law(law_identifier, next_codex_version)
    next_law_xml = next_law.xml().getroot()

    # Find the same element (article or chapter) in the next version
    next_element = None
    if element_type == "article":
        for art in next_law_xml.xpath(".//art[@nr='%s']" % element_nr):
            next_element = art
            break
    elif element_type == "chapter":
        for chapter in next_law_xml.xpath(".//chapter[@nr='%s']" % element_nr):
            next_element = chapter
            break

    if next_element is None:
        raise AdvertException(
            f"Cannot diff: {element_type} {element_nr} not found in next codex version "
            f"{next_codex_version} for law {law_identifier}"
        )

    # Extract both elements as XML strings
    current_element_xml = _extract_element_xml(diff_element)
    next_element_xml = _extract_element_xml(next_element)

    # Generate the diff
    diff = do_diff_str(next_element_xml, current_element_xml, context=3)
    if diff:
        print(
            f"\n  Diff for {element_type} {element_nr} (next codex {next_codex_version} → current modified):"
        )
        print("  " + "=" * 70)
        # Print diff with color coding
        for line in diff.splitlines():
            # Color code diff lines
            if line.startswith("-"):
                # Removed lines in red
                colored_line = f"{Fore.RED}{line}{Style.RESET_ALL}"
            elif line.startswith("+"):
                # Added lines in green
                colored_line = f"{Fore.GREEN}{line}{Style.RESET_ALL}"
            elif line.startswith("@"):
                # Hunk headers in cyan
                colored_line = f"{Fore.CYAN}{line}{Style.RESET_ALL}"
            else:
                # Context lines and other content stay normal
                colored_line = line
            print(f"  {colored_line}")
        print("  " + "=" * 70)
    else:
        print(
            f"  {element_type.capitalize()} {element_nr} is identical to next codex version {next_codex_version}"
        )
