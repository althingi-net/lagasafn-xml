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
# TODO:
# We can improve the search engine storage efficiency significantly by making a (file,xpath)->context mapping
# and use that rather than storing the context with every single token. This will also be faster.
#
# NOTE:
# Hereafter, any changes to the index format should increment the INDEX_VERSION constant.
INDEX_VERSION = 3
# Version history:
#  1: Initial version
#  2: Added refs index for storing natural language references to XPaths
#  3: Added tfidf_scores and tf_scores indexes

from collections import defaultdict
from datetime import datetime
import math
import os
from typing import List
import click
import pickle
from islenska import Bin
from lxml import etree as ET
from math import log

from lagasafn.utils import generate_legal_reference


class Results:
    def __init__(self):
        # A results object stores a list of files and their score, and then a list of XPaths in the file,
        # and a list of start and end positions in the text of each XPath.
        self.result_files = {}
        self.flattened = []
        self.metadata = {}
        self.refs = {}
        self.xpaths = {}

    @property
    def files(self):
        return self.result_files

    def sort_info(self, info):
        flattened = []
        for xpath, set in info.items():
            flattened.append((xpath, set["locations"], set["score"], set["context"]))

        return sorted(flattened, key=lambda x: x[2], reverse=True)

    def augment_with_metadata(self, metadata):
        for file in self.result_files.keys():
            if file not in metadata:
                continue
            self.metadata[file] = metadata[file]

    def augment_with_refs(self, refs):
        # TODO: Filter for only stuff that makes sense.
        for file in self.result_files.keys():
            self.refs[file] = {}
            for xpath, ref in refs[file].items():
                self.refs[file][xpath] = ref

    def sort(self):
        # Here we sort the result files by overall score, and the hits within
        # the files by their sub-score
        self.flattened = []
        for file, info in self.result_files.items():
            self.flattened.append(
                (file, self.sort_info(info), sum([z["score"] for y, z in info.items()]))
            )

        self.sorted = sorted(self.flattened, key=lambda x: x[2], reverse=True)
        return self.sorted

    def add(self, results):
        # NOTE: Any changes to the index format should increment INDEX_VERSION.
        for item in results:
            filename, xpath, start, end, context = item
            if filename not in self.result_files:
                self.result_files[filename] = {}

            if xpath not in self.result_files[filename]:
                self.result_files[filename][xpath] = {
                    "locations": [],
                    "score": 0,
                    "context": context,
                }

            self.result_files[filename][xpath]["score"] += 1
            self.result_files[filename][xpath]["locations"].append((start, end))

    def get_files(self):
        return self.result_files.keys()


class SearchEngine:
    def __init__(self, index_file="search_index.pkl"):
        # Load the search index from a pickle file
        self.bin = Bin()
        self._index_file = index_file
        try:
            print("Loading index...", end="", flush=True)
            fh = open(self._index_file, "rb")
            self._index = pickle.load(fh)
            fh.close()
            if self._index["version"] != INDEX_VERSION:
                print(
                    f"Index version mismatch: expected {INDEX_VERSION}, got {self._index['version']}. We cannot guarantee compatibility. Exiting."
                )
                exit(1)
            print(
                " done. [%d files, %d tokens, %d refs]"
                % (
                    len(self._index["metadata"]),
                    len(self._index["tokens"]),
                    len(self._index["refs"]),
                )
            )
        except FileNotFoundError:
            print("No search index found, starting with an empty index")
            self.empty()

    def empty(self):
        # NOTE: If you add or remove anything from the index, remember to increment INDEX_VERSION
        self._index = {
            "metadata": defaultdict(dict),
            "tokens": defaultdict(list),
            "refs": defaultdict(dict),
            "tfidf_scores": defaultdict(dict),
            "tf_scores": defaultdict(dict),
            "total_documents": 0,
            "version": INDEX_VERSION,
        }
        self.document_frequencies = defaultdict(int)
        self.save_index()

    def save_index(self):
        pickle.dump(self._index, open(self._index_file, "wb"))

    def index_xpath_ref(self, xml_file: str, xpath: str, ref: str):
        if xml_file not in self._index["refs"]:
            self._index["refs"][xml_file] = {}
        if xpath not in self._index["refs"][xml_file]:
            self._index["refs"][xml_file][xpath] = ref

    def index_dir(self, xml_dir: str, exclude: List[str] = []):
        print("Excluding files:", exclude)
        time_start = datetime.now()
        files = os.listdir(xml_dir)
        count = len(files)
        idx = 0
        for xml_file in files:
            idx += 1

            if xml_file in exclude or os.path.join(xml_dir, xml_file) in exclude:
                continue

            print(f"[{idx:>5}/{count:<5}] Indexing {xml_file}...", end="\r")
            self.index_file(os.path.join(xml_dir, xml_file), save_index=False)

        # Now that we have indexed all the files, we can calculate the TF-IDF scores
        self.calculate_tfidf()

        self.save_index()
        time_end = datetime.now()

        print(
            f"Indexing complete in {(time_end - time_start).total_seconds()} seconds. Indexed:"
        )
        print(f"{len(self._index['metadata']):>10} files")
        print(f"{len(self._index['tokens']):>10} tokens")
        locs = sum([len(x) for y, x in self._index["tokens"].items()])
        print(f"{locs:>10} locations")
        refs = sum([len(x) for y, x in self._index["refs"].items()])
        print(f"{refs:>10} references in {len(self._index['refs'])} files")

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

        self._index["total_documents"] += 1
        term_frequencies = defaultdict(int)

        for child in root.iter():
            # Tokenize the text
            text = child.text
            if text is None:
                continue
            tokens = self.tokenize(text)
            xpath = child.getroottree().getpath(child)
            xpath = "./" + xpath.replace(
                "/" + root.tag, ""
            )  # Remove the root tag from the XPath and replace with relative

            if child.tag in [
                "art",
                "subart",
                "numart",
                "art-chapter",
                "paragraph",
                "chapter",
                "subchapter",
                "numart-chapter",
            ]:
                try:
                    ref = generate_legal_reference(child, skip_law=True)
                    self.index_xpath_ref(xml_file, xpath, ref)
                except Exception as e:
                    print(
                        f"Could not generate reference for {xpath} in {xml_file}: {e}"
                    )
                    continue

            for token, start, end in tokens:
                # Token stemming not implemented.
                term_frequencies[token] += 1
                self.index_token(token, xml_file, xpath, start, end, text)

        # Update document frequencies for each unique token in this document
        for token in term_frequencies.keys():
            self.document_frequencies[token] += 1

        # Now we can add each token to the index with its TF for this document
        for token, tf in term_frequencies.items():
            # Optionally store TF for later calculation of TF-IDF
            self._index["tf_scores"][token][xml_file] = tf

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
            tok = tok.strip(".,?!;:\"()[]{}'")

            # Remove empty tokens
            if tok == "":
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

    def index_token(
        self, token: str, filename: str, xpath: str, start: int, end: int, context: str
    ):
        # NOTE: If you add or remove anything from the index, remember to increment INDEX_VERSION
        if token not in self._index["tokens"]:
            self._index["tokens"][token] = []
        self._index["tokens"][token].append((filename, xpath, start, end, context))

    def calculate_tfidf(self):
        """Compute and store TF-IDF for each token in each document"""
        print("Calculating TF-IDF scores...")
        for token, doc_data in self._index["tf_scores"].items():
            idf = math.log(
                self._index["total_documents"] / (1 + self.document_frequencies[token])
            )
            for doc, tf in doc_data.items():
                tfidf_score = tf * idf
                # Store the TF-IDF score in the index
                if token not in self._index["tfidf_scores"]:
                    self._index["tfidf_scores"][token] = {}
                self._index["tfidf_scores"][token][doc] = tfidf_score

    def search(self, query):
        print("Searching the index")
        tokens = self.tokenize(query)
        results = Results()

        for token, start, end in tokens:
            if token in self._index["tokens"]:
                results.add(self._index["tokens"][token])

        results.augment_with_metadata(self._index["metadata"])
        results.augment_with_refs(self._index["refs"])
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

    return "".join(result)


def print_results(results):
    sorted_results = results.sort()
    print(
        "Search results: (%d references in %d files)"
        % (len(results.flattened), len(results.files))
    )

    for file, hits, score in sorted_results:
        metadata = results.metadata[file]
        print(f"File: {file}")
        print("Title:", metadata.get("title", "Unknown"))
        print("Score:", score)
        print("Hits:")
        for item in hits:
            xpath, locs, score, context = item
            print(f"  {xpath}: {results.refs.get(file, {}).get(xpath, '')}")
            # Open the file and print the context of the XPath
            text = add_bold_ansi(context, locs)
            print("     ", text)
        print("")


@click.group()
def cli():
    pass


@cli.command()
@click.argument("xml_dir", type=click.Path(exists=True), required=True)
@click.option(
    "--empty",
    "-e",
    is_flag=True,
    help="Empty the index before adding the contents of the directory",
)
@click.option(
    "--exclude",
    "-x",
    multiple=True,
    type=click.Path(),
    help="A file containing a list of files to exclude from the index",
)
@click.option(
    "--index",
    "-i",
    type=click.Path(),
    default="search_index.pkl",
    help="The target file to save the index to",
)
def index(xml_dir, empty, index, exclude):
    """Build the search index"""
    search_engine = SearchEngine(index)

    if empty:
        print(
            f"Emptying the search index and adding the contents of `{xml_dir}` to the index"
        )
        search_engine.empty()
    else:
        print(f"Adding the contents of `{xml_dir}` the search index")

    search_engine.index_dir(xml_dir, exclude)


@cli.command()
@click.argument("query", type=str, required=True)
@click.option(
    "--index",
    "-i",
    type=click.Path(),
    default="search_index.pkl",
    help="The target file to save the index to",
)
def search(query):
    """Search the index"""
    search_engine = SearchEngine(index)
    results = search_engine.search(query)
    print_results(results)


@cli.command()
@click.option(
    "--index",
    "-i",
    type=click.Path(),
    default="search_index.pkl",
    help="The target file to save the index to",
)
def search_cli(index):
    """Start the search engine command-line interface"""
    print("Starting the search engine command-line interface")
    search_engine = SearchEngine(index)
    while True:
        query = input("Enter a search query (or 'exit' to quit): ")
        if query == "exit":
            break
        start_time = datetime.now()
        results = search_engine.search(query)
        end_time = datetime.now()
        print_results(results)
        print(f"Search time: {end_time - start_time} seconds")


@cli.command()
@click.option(
    "--num", "-n", type=int, default=10, help="The number of top tokens to display"
)
@click.option(
    "--index",
    "-i",
    type=click.Path(),
    default="search_index.pkl",
    help="The target file to save the index to",
)
def top(index, num):
    """Print the top 10 tokens from the search index"""
    search_engine = SearchEngine(index)
    items = list(search_engine._index["tokens"].items())
    items.sort(key=lambda x: len(x[1]), reverse=True)
    for token, locations in items[:num]:
        print(f"{token:<15}: {len(locations)} locations")


if __name__ == "__main__":
    cli()
