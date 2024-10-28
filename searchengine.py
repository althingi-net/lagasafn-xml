#
# Python based full text search engine for XML files
#
# This script is a full text search engine for XML files. It reads XML files from a directory, 
# builds a text index from the contents of the XML files, and then allows you to search the index.
# Queries result in a list of filenames that match the query, and the XPaths to the matching text.
#
# We want to support Icelandic language stemming, because the XML files are in Icelandic.
#

import os
from typing import List
import click
import pickle
from islenska import Bin
from lxml import etree as ET
from math import log
import pdb

class IndexItem:
    def __init__(self, filename: str, xpath: str, start: int, end: int):
        self.filename = filename
        self.xpath = xpath
        self.start = start
        self.end = end

    def __str__(self):
        return f"{self.filename}: {self.xpath} ({self.start}-{self.end})"

    def __repr__(self):
        return self.__str__()


class Results:
    def __init__(self):
        # A results object stores a list of files and their score, and then a list of XPaths in the file,
        # and a list of start and end positions in the text of each XPath.
        self.result_files = {}
        self.flattened = []

    @property
    def files(self):
        return self.result_files
    
    def sort(self):
        # Here we sort the result files by overall score, and the hits within
        # the files by their sub-score
        self.flattened = []
        for file, info in self.result_files.items():
            self.flattened.append((file, info, sum([z["score"] for y,z in info.items()])))

        self.sorted = sorted(self.flattened, key=lambda x: x[2], reverse=True)
        return self.sorted

    def add(self, results, intersect_files=False):
        _results = results
        if intersect_files:
            # If we want to intersect the files, we need to find the files that don't come up in
            # this set of results and remove them from the result_files dictionary, as well as the
            # results from this set.
            files = self.get_files()
            new_files = [item.filename for item in results]
            for file in files:
                if file not in new_files:
                    del self.result_files[file]

            for item in _results:
                if item.filename not in files:
                    _results.remove(item)

        for item in _results:
            if item.filename not in self.result_files:
                self.result_files[item.filename] = {}

            if item.xpath not in self.result_files[item.filename]:
                self.result_files[item.filename][item.xpath] = {"locations": [], "score": 0}

            self.result_files[item.filename][item.xpath]["score"] += 1
            self.result_files[item.filename][item.xpath]["locations"].append((item.start, item.end))

        #for file in self.result_files:
        #    self.result_files[file]["score"] = log(self._index[] / self.result_files[file]["count"])

    def get_files(self):
        return self.result_files.keys()
    

class SearchEngine:
    def __init__(self):
        # Load the search index from a pickle file
        self.bin = Bin()
        self._index_file = "search_index.pkl"
        try:
            fh = open(self._index_file, 'rb')
            self._index = pickle.load(fh)
            fh.close()
        except FileNotFoundError:
            print("No search index found, starting with an empty index")
            self._index = {}

    def empty(self):
        self._index = {}
        self.save_index()

    def save_index(self):
        pickle.dump(self._index, open(self._index_file, 'wb'))

    def index_dir(self, xml_dir: str):
        print("Building the search index")
        files = os.listdir(xml_dir)
        count = len(files)
        idx = 0
        for xml_file in files:
            idx += 1
            print(f"[{idx:>5}/{count:<5}] Indexing {xml_file}...", end='\r')
            self.index_file(os.path.join(xml_dir, xml_file), save_index=False)

        self.save_index()

    def index_file(self, xml_file: str, save_index=True):
        # Parse the XML file
        tree = ET.parse(xml_file)
        root = tree.getroot()

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
                self.index_token(token, xml_file, xpath, start, end)

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

    def index_token(self, token: str, filename: str, xpath: str, start: int, end: int):
        if token not in self._index:
            self._index[token] = []
        self._index[token].append(IndexItem(filename, xpath, start, end))

    def search(self, query):
        print("Searching the index")
        tokens = self.tokenize(query)
        results = Results()

        for (token, start, end) in tokens:
            if token in self._index:
                results.add(self._index[token], intersect_files=False)
        
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