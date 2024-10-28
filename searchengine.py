#!/usr/bin/env python3
#
# Python based full text search engine for XML files
#
# This script is a full text search engine for XML files. It reads XML files from a directory, 
# builds a text index from the contents of the XML files, and then allows you to search the index.
# Queries result in a list of filenames that match the query, and the XPaths to the matching text.
#
# We want to support Icelandic language stemming, because the XML files are in Icelandic.
#

from datetime import datetime
import os
from typing import List
import click
import pickle
from islenska import Bin
from lxml import etree as ET
from math import log
import pdb


class Results:
    def __init__(self):
        # A results object stores a list of files and their score, and then a list of XPaths in the file,
        # and a list of start and end positions in the text of each XPath.
        self.result_files = {}
        self.flattened = []
        self.metadata = {}

    @property
    def files(self):
        return self.result_files
    
    def sort_info(self, info):
        flattened = []
        for xpath, set in info.items():
            flattened.append((xpath, set["locations"], set["score"]))

        return sorted(flattened, key=lambda x: x[2], reverse=True)
    
    def augment_with_metadata(self, metadata):
        for file in self.result_files.keys():
            if file not in metadata:
                continue
            self.metadata[file] = metadata[file]

    def sort(self):
        # Here we sort the result files by overall score, and the hits within
        # the files by their sub-score
        self.flattened = []
        for file, info in self.result_files.items():
            self.flattened.append((file, self.sort_info(info), sum([z["score"] for y,z in info.items()])))

        self.sorted = sorted(self.flattened, key=lambda x: x[2], reverse=True)
        return self.sorted

    def add(self, results):
        for item in results:
            filename, xpath, start, end, context = item
            if filename not in self.result_files:
                self.result_files[filename] = {}

            if xpath not in self.result_files[filename]:
                self.result_files[filename][xpath] = {"locations": [], "score": 0}

            self.result_files[filename][xpath]["score"] += 1
            self.result_files[filename][xpath]["locations"].append((start, end, context))

    def get_files(self):
        return self.result_files.keys()
    

class SearchEngine:
    def __init__(self, index_file="search_index.pkl"):
        # Load the search index from a pickle file
        self.bin = Bin()
        self._index_file = index_file
        try:
            print("Loading index...", end="", flush=True)
            fh = open(self._index_file, 'rb')
            self._index = pickle.load(fh)
            fh.close()
            print(" done.")
        except FileNotFoundError:
            print("No search index found, starting with an empty index")
            self._index = {"metadata": {}, "tokens": {}}

    def empty(self):
        self._index = {"metadata": {}, "tokens": {}}
        self.save_index()

    def save_index(self):
        pickle.dump(self._index, open(self._index_file, 'wb'))

    def index_dir(self, xml_dir: str):
        print("Building the search index")
        time_start = datetime.now()
        files = os.listdir(xml_dir)
        count = len(files)
        idx = 0
        for xml_file in files:
            idx += 1
            print(f"[{idx:>5}/{count:<5}] Indexing {xml_file}...", end='\r')
            self.index_file(os.path.join(xml_dir, xml_file), save_index=False)

        self.save_index()
        time_end = datetime.now()

        print(f"Indexing complete in {(time_end - time_start).total_seconds()} seconds. Indexed:")
        print(f"{len(self._index["metadata"]):>10} files")
        print(f"{len(self._index["tokens"]):>10} tokens")
        locs = sum([len(x) for y,x in self._index["tokens"].items()])
        print(f"{locs:>10} locations")
        

    def index_metadata(self, xml_file: str, metadata: dict):
        self._index["metadata"][xml_file] = metadata

    def index_file(self, xml_file: str, save_index=True):
        # Parse the XML file
        tree = ET.parse(xml_file)
        root = tree.getroot()

        metadata = dict(root.items())

        name = root.find("name")
        if name is not None:
            metadata["title"] = name.text
        else:
            print(f"Could not find <name> tag in {xml_file}")

        self.index_metadata(xml_file, metadata)

        for child in root.iter():
            # Tokenize the text
            text = child.text
            if text is None:
                continue
            tokens = self.tokenize(text)
            xpath = child.getroottree().getpath(child)
            xpath = xpath.replace("/" + root.tag, "") # Remove the root tag from the XPath, because... reasons

            for (token, start, end) in tokens:
                # Token stemming not implemented.
                self.index_token(token, xml_file, xpath, start, end, text)

        if save_index:
            self.save_index()

    def split(self, text: str, splitchars: str = [" ", "\n", "\t"]):
        # This will return a list of tuples consisting of the token, 
        # and its start and end position in the string.
        results = []
        start = None
        for i, char in enumerate(text):
            if char in splitchars:
                if start is not None:
                    results.append((text[start:i], start, i))
                    start = None
            else:
                if start is None:
                    start = i

        # Add the last token if the string doesn't end with a splitchar
        if start is not None:
            results.append((text[start:], start, len(text)))

        return results
        

    def tokenize(self, text: str):
        # Tokenize the text
        toks = []
        tokens = self.split(text)
        for tok, start, end in tokens:
            # Remove punctuation and such:
            tok = tok.strip('.,?!;:"()[]{}\'')
            
            # Remove empty tokens
            if tok == '':
                continue

            # Lowercase the token
            tok = tok.lower()

            # Get the base form of the token
            lemmas = self.bin.lookup_lemmas(tok)[1]
            if len(lemmas) > 0:
                for lemma in lemmas:
                    toks.append((lemma.ord, start, end))
            else:
                toks.append((tok, start, end))

        # toks = list(set(toks))

        return toks

    def index_token(self, token: str, filename: str, xpath: str, start: int, end: int, context:str):
        if token not in self._index["tokens"]:
            self._index["tokens"][token] = []
        self._index["tokens"][token].append((filename, xpath, start, end, context))

    def search(self, query):
        print("Searching the index")
        tokens = self.tokenize(query)
        results = Results()

        for (token, start, end) in tokens:
            if token in self._index["tokens"]:
                results.add(self._index["tokens"][token])

        results.augment_with_metadata(self._index["metadata"])
        results.sort()
        return results

    def serve(self):
        print("Starting the search engine web server")


def add_bold_ansi(text: str, positions: list):
    """
    Adds ANSI bold formatting to the given text at the specified positions.
    
    Parameters:
    - text: The original string.
    - positions: A list of tuples, where each tuple contains (start, end) indices.

    Returns:
    - The formatted string with ANSI bold characters.
    """
    # ANSI escape sequences for bold and reset
    BOLD = "\033[1m\033[34m"
    RESET = "\033[0m"
    
    # Sort positions to ensure we process them in order
    positions = sorted(positions, key=lambda x: x[0])
    
    result = []
    last_index = 0
    
    for start, end in positions:
        # Add the text before the bold section
        result.append(text[last_index:start])
        # Add the bold text
        result.append(f"{BOLD}{text[start:end]}{RESET}")
        last_index = end
    
    # Add the remaining part of the text after the last bold section
    result.append(text[last_index:])
    
    return ''.join(result)


def print_results(results):
    s = results.sort()
    for file, refs, score in s:
        print("File:", file)
        print("Score:", score)
        print("Hits:")
        for xpath, info in refs.items():
            print(f"  {xpath}:")
            # Open the file and print the context of the XPath
            locs = info["locations"]
            score = info["score"]
            tree = ET.parse(file)
            elem = tree.find("./" + xpath)
            text = add_bold_ansi(elem.text, locs)
            print("     ", text)
        print("")


@click.group()
def cli():
    pass

@cli.command()
@click.argument('xml_dir', type=click.Path(exists=True), required=True)
@click.option('--empty', '-e', is_flag=True, help='Empty the index before adding the contents of the directory')
def index(xml_dir, empty):
    """Build the search index"""
    search_engine = SearchEngine()

    if empty:
        print(f"Emptying the search index and adding the contents of `{xml_dir}` to the index")
        search_engine.empty()
    else:
        print(f"Adding the contents of `{xml_dir}` the search index")

    search_engine.index_dir(xml_dir)


@cli.command()
@click.argument('query', type=str, required=True)
def search(query):
    """Search the index"""
    search_engine = SearchEngine()
    results = search_engine.search(query)
    print_results(results)


@cli.command()
def search_cli():
    """Start the search engine command-line interface"""
    from datetime import datetime
    print("Starting the search engine command-line interface")
    search_engine = SearchEngine()
    while True:
        query = input("Enter a search query (or 'exit' to quit): ")
        if query == 'exit':
            break
        start_time = datetime.now()
        results = search_engine.search(query)
        end_time = datetime.now()
        print_results(results)
        print(f"Search time: {end_time - start_time} seconds")



@cli.command()
def serve():
    """Start the search engine web server"""
    print("Starting the search engine web server")



if __name__ == '__main__':
    cli()