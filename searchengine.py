#!/usr/bin/env python3
import click
from datetime import datetime
from lagasafn.search import SearchEngine

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
def search(query, index):
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
