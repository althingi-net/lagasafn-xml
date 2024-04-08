This repo is composed of 4 separate parts.

1. **Lagasafn-XML** (`lagasafn`): A tool for turning the HTML in which Icelandic law is published into machine-readable XML.
2. **MechLaw** (`mechlaw`): A web application displaying the codex with features made available with the new XML format.
3. **RefBuilder** (`refbuilder`): An experimental project, inactive for now, for using AI to analyze references in legal text.
4. **Data** (`data`): The static XML data produced by Lagasafn-XML and utilized by MechLaw.

# Lagasafn-XML

## About

Icelandic law is currently published in PDF and HTML, neither of which is easy or convenient to manage programmatically. This tool parses the HTML version of Icelandic law and generates orderly XML files which can then be used programmatically.

*Example (constitution of Iceland):*

| Format   | URL                                                                           |
| :------: | :-----------------------------------------------------------------------------|
| HTML     | https://www.althingi.is/lagas/nuna/1944033.html                               |
| PDF      | https://www.althingi.is/lagasafn/pdf/nuna/1944033.pdf                         |
| **XML**  | https://github.com/althingi-net/lagasafn-xml/blob/master/data/xml/1944.33.xml |

The entire law can be downloaded in HTML form, in a zip file, at http://www.althingi.is/lagasafn/zip-skra-af-lagasafni/. Versions are denoted by Parliament number, higher numbers meaning more recent. The version number "151c" for example, means "the 151th Parliament" and the letter "c" means that it's the version of the legal codex that was in effect when that Parliament convened.

It is developed and tested on Ubuntu, but should work on anything that runs Python 3. These instructions assume a Unix-based operating system.

## Running

The script is run in a command line.

As per Pythonic tradition, the required Python packages are listed in a text file called `requirements.txt`. There is also an alternative file called `requirements-frozen.txt`, which contains specific versions of the required packages, known to work.

To install the required packages, run:

    pip install -r requirements.txt

If that fails, try using the "frozen" list:

    pip install -r requirements-frozen.txt

Alternatively, if using a Debian-derivative (such as Ubuntu), you can install the libraries system-wide with:

    apt-get -y install python3-bs4 python3-html5lib python3-lxml python3-roman python3-formencode

Run the script in a terminal with no parameters for usage instructions.

    ./lagasafn-xml

## Data

If you are only interested in the generated XML files themselves, then feel free to dig around in the `data/xml` directory.

Icelandic laws have a number/year combination. For example, the constitution of Iceland is law nr. 33/1944, meaning that it was the 33rd law enacted in the year 1944. The XML files are named `[year].[nr].xml`.

**Please note that this is still a work in progress and the XML is not guaranteed to be correct.**

## Patching errors in data

Published law is unfortunately not always perfect, in fact we see quite frequently errors of some kind that cause issues to the parsing process. When an error is somewhat easily fixable we create a patch for the cleaned HTML file and store it for the given published law version.

### Patch creation example

**Note**: In order to create the "cleaned" version, you must first attempt to process a law. Example, by running `./lagasafn-xml 134/1995`, the file `cleaned/1995-134.html` will be created, and it is this latter file that you then patch.

Let's say the current published law version is `151c` and we want to fix some error in law `1995-134`, then we first run:

```bash
mkdir -p patched
cp cleaned/1995-134.html patched/1995-134.html
```

then we fix the error in `patched/1995-134.html` and save it, then run:

```bash
mkdir -p patches/151c
# if you have GNU diff at your disposal then you can just run
diff -U10 "data/cleaned/1995-134.html" "data/patched/1995-134.html" > "data/patches/151c/1995-134.html.patch"
# or if you don't have GNU diff you can run
python diff_patch_utils.py -c 10 -mp -fa "data/cleaned/1995-134.html" -fb "data/patched/1995-134.html" -o "data/patches/151c/1995-134.html.patch"
```

Now if we want to document what the error was about we can open the `patches/151c/1995-134.html.patch` file and add comments in the header on what the issue was. Like this for example:

```
# Two square brackets closed but only one opened
#
# Looked it up, new closing square bracket should have opening square bracket for whole 19. gr. a.
# See 19. gr. a, https://www.althingi.is/lagas/151c/1995134.html
#     + 1) https://www.althingi.is/altext/stjt/2021.018.html
#     + 2) https://www.althingi.is/altext/stjt/2005.062.html#G13
--- cleaned/1995-134.html	2022-01-21 18:16:00.690116352 +0000
+++ patched/1995-134.html	2022-01-21 19:06:13.395058432 +0000
@@ -1101 +1101 @@
-   [19. gr. a.
+   [[19. gr. a.

```

and you're done. You can push the new patch file to the repo, or create a pull request.

# License

See the document `LICENSE.md`. (It's MIT.)
