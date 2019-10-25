# althingi-document-cleaner

A tool for turning the HTML in which Icelandic law is published into machine-readable XML.

## About

Icelandic law is currently published in PDF and HTML, neither of which is easy or convenient to manage programmatically. This tool parses the HTML version of Icelandic law and generates orderly XML files which can then be used programmatically.

*Example (constitution of Iceland):*

| Format   | URL                                                                                   |
| :------: | :------------------------------------------------------------------------------------ |
| HTML     | https://www.althingi.is/lagas/149c/1944033.html                                       |
| PDF      | https://www.althingi.is/lagasafn/pdf/149c/1944033.pdf                                 |
| **XML**  | https://github.com/piratar/althingi-document-cleaner/blob/master/xml/1944.33.149c.xml |

The entire law can be downloaded in HTML form, in a zip file, at http://www.althingi.is/lagasafn/zip-skra-af-lagasafni/. Versions are denoted by Parliament number, higher numbers meaning more recent. The version number "148c" for example, means "the 148th Parliament" and the letter "a" means that it's the version of the legal codex that was in effect when that Parliament convened.

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

    ./althingi-document-cleaner

## Data

If you are only interested in the generated XML files themselves, then feel free to dig around in the `xml` directory. Just make sure that you're viewing the most recent, available version.

Icelandic laws have a number/year combination. For example, the constitution of Iceland is law nr. 33/1944, meaning that it was the 33rd law enacted in the year 1944. The XML files are named `[year].[nr].[version].xml`.

The version is the third value in the XML file's name. For example, `1944.33.148c.xml` is newer than `1944.33.148a.xml` and both are newer than `1944.33.147.xml`.

**Please note that this is still a work in progress and the XML is not guaranteed to be correct. In fact, not all laws are yet available due to unsolved problems with parsing them.** To see how many of them are available, you can run the script with the `-E` option, which will show you what errors remain processing which laws, as well as success/failure statistics.

## License

See the document `LICENSE.md`. (It's MIT.)
