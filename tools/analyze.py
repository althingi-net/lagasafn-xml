# XML Document Structure Analyzer
# Smári McCarthy <smari AT ecosophy.is>
# Date: 2024-06-03
#
# License: MIT
#
# This script reads a directory of XML files and generates a report of the structure of the XML documents.
#
import click
import json
import sys
from pathlib import Path
from xml.dom import minidom

# Things we want to track:
#  - Which elements exist, and how many there are of each
#  - Which attributes exist, and how many there are of each
#  - Which attributes are present on which elements
#  - Which elements are present inside which other elements
#  - Which elements are parents of which other elements

class XMLStructureInfo:
    def __init__(self):
        self.elements = {}
        self.attributes = {}
        self.element_parents = {}
        self.element_children = {}
        self.element_attributes = {}

    def parse(self, filename):
        # file = open(filename, "r").read()
        doc = minidom.parse(str(filename))
        self._parse_node(doc.documentElement)
    
    def _parse_node(self, node):
        if node.nodeType == node.ELEMENT_NODE:
            self.elements[node.tagName] = self.elements.get(node.tagName, 0) + 1
            self._parse_attributes(node)
            for child in node.childNodes:
                self._parse_node(child)
                if child.nodeType == node.ELEMENT_NODE:
                    self.element_children.setdefault(node.tagName, {}).setdefault(child.tagName, 0)
                    self.element_children[node.tagName][child.tagName] += 1
                    self.element_parents.setdefault(child.tagName, {}).setdefault(node.tagName, 0)
                    self.element_parents[child.tagName][node.tagName] += 1

    def _parse_attributes(self, node):
        if node.hasAttributes():
            for attr in node.attributes.items():
                self.attributes[attr[0]] = self.attributes.get(attr[0], 0) + 1
                self.element_attributes.setdefault(node.tagName, {}).setdefault(attr[0], 0)
                self.element_attributes[node.tagName][attr[0]] += 1

    def report(self, format):
        if format == "json":
            self._report_json()
        elif format == "yaml":
            self._report_yaml()

    def _report_json(self):
        print(json.dumps({
            "elements": self.elements,
            "attributes": self.attributes,
            "element_children": self.element_children,
            "element_parents": self.element_parents,
            "element_attributes": self.element_attributes
        }, indent=2, sort_keys=True))

    def _report_yaml(self):
        print("elements:")
        for element, count in self.elements.items():
            print(f"  {element}: {count}")
        print("attributes:")
        for attr, count in self.attributes.items():
            print(f"  {attr}: {count}")
        print("element children:")
        for element, children in self.element_children.items():
            print(f"  {element}:")
            for child, count in children.items():
                print(f"    {child}: {count}")
        print("element_parents:")
        for element, parents in self.element_parents.items():
            print(f"  {element}:")
            for parent, count in parents.items():
                print(f"    {parent}: {count}")
        print("element_attributes:")
        for element, attrs in self.element_attributes.items():
            print(f"  {element}:")
            for attr, count in attrs.items():
                print(f"    {attr}: {count}")

@click.command()
@click.argument("dir", type=click.Path(exists=True))
@click.option("--format", type=click.Choice(["json", "yaml"]), default="yaml")
@click.option("--verbose", type=bool, default=False)
def main(dir, format, verbose):
    """Analyze XML files in DIR and display a summary of elements"""
    info = XMLStructureInfo()

    for file in Path(dir).rglob("*.xml"):
        try:
            if verbose:
                click.echo(f"Parsing {file} ...", file=sys.stderr)
            info.parse(file)
        except Exception as e:
            if verbose:
                click.echo(f"Error parsing {file}: {e}", err=True, file=sys.stderr)

    info.report(format)


if __name__ == "__main__":
    main()