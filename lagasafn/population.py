import glob

from lagasafn.parser import LawParser, parse_end_of_law, parse_intro, parse_law
from datetime import datetime

class LawFile:
    year = 0
    number = 0
    title = ""
    parser = None

    def __init__(self, number: int, year: int):
        self.year = int(year)
        self.number = int(number)
        self.parser = LawParser(self.number, self.year)

class Statistics:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.items = {}
        self.item_locations = {}
        self.ignore_list = []

    def ignore(self, item):
        self.ignore_list.append(item)

    def accumulate(self, corpus, getter: callable, location_getter=None):
        for member in corpus:
            try:
                self.add(getter(member))
                if location_getter:
                    self.add_location(getter(member), location_getter(member))
            except Exception as e:
                pass

    def add(self, item):
        if item not in self.items:
            self.items[item] = 1
        else:
            self.items[item] += 1

    def add_location(self, item, location):
        if item not in self.item_locations:
            self.item_locations[item] = []
        self.item_locations[item].append(location)
    
    def print(self, headline=""):
        total = sum([count for count in self.items.values()])
        if headline and total > 0:
            print(headline)
        # Sort by count:
        sorted_items = {k: v for k, v in sorted(self.items.items(), key=lambda item: item[1], reverse=True)}
        for item, count in sorted_items.items():
            if item in self.ignore_list:
                continue
            print(f" - {item}: {count} ({count/total*100:.2f}%)")

    def print_locations(self, headline=""):
        if headline:
            print(headline)

        # Sort items by how many locations they appear in:
        sorted_items = {k: v for k, v in sorted(self.item_locations.items(), key=lambda item: len(item[1]), reverse=True)}
        for item, locations in sorted_items.items():
            if item in self.ignore_list:
                continue
            print(f" - {item}: {len(locations)}\n     - ")
            for location in locations:
                print(f"{location}, ", end="")
            print()


def population_game():
    """
    What we're going to do here is load *all* of the input HTML files and process them in lock-step, 
    reporting which tags come next after each step. This will help us understand the structure of the
    overall corpus.
    """

    # It's only 1670 files amounting to 38MB of data. So let's start by loading them all into memory.
    files = glob.glob('data/cleaned/*.html')
    print(f"Found {len(files)} files.")
    print("Loading files into memory...")
    start_time = datetime.now()

    laws = []
    for file in files:
        law_year, law_num = file.split('/')[-1].split('.')[0].split('-')
        law = LawFile(law_num, law_year)
        laws.append(law)

    end_time = datetime.now()
    print(f"Loaded {len(laws)} laws in {end_time - start_time}")

    next_tags = Statistics()
    next_tags.ignore("</html>")
    next_three = Statistics()
    errors = Statistics()
    stopping_lines = Statistics()
    for law in laws:
        try:
            parse_law(law.parser)
        except Exception as e:
            errors.add(str(e))
    
    next_tags.accumulate(laws, lambda law: law.parser.line[:30], lambda law: f"{law.year}-{law.number}.html:{law.parser.lines.current_line_number}")
    next_three.accumulate(laws, lambda law: law.parser.line[:30] + law.parser.peeks(1)[:30] + law.parser.peeks(2)[:30], lambda law: f"{law.number}/{law.year}")
    stopping_lines.accumulate(laws, lambda law: law.parser.lines.current_line_number)

    next_tags.print_locations("Next tags:")
    next_three.print("Next three tags:")
    errors.print("Errors:")
    stopping_lines.print("Halting lines:")
    
    
