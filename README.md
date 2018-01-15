# althingi-document-cleaner

Experimental and incomplete tool for cleaning up the HTML in which Icelandic law is published.

## Purpose

This script is an incomplete experiment to see how far the HTML version of Icelandic law can be deduced into something programmatically useful.

## History

Icelandic law can be downloaded in its entirety in HTML form at this location: `http://www.althingi.is/lagasafn/zip-skra-af-lagasafni/`. The appropriate zip file (typically the newest one) can be downloaded and extracted. This script assumes that it has been downloaded, extracted and its folder named `current`. The Icelandic law is included in the project, but may not be the newest version, depending on how much time has passed since this was written and if anyone has bothered to update it.

The problem with the HTML is that its format is archaic, old-fashioned and not easy to parse as it appears in the downloaded zip. This script is an attempt to remove anything irrelevant to the content, fix various problems in the HTML (`<img>` tags not being properly closed, for example) and format the HTML in a way that makes it easier to manage programmatically.

The ultimate goal is to produce a version of the legal content that can easily be turned into XML, imported to a database or whatever, so that the content can be referenced managed and produced programmatically.

As stated earlier, this is currently an incomplete experiment, not fit for production use. In fact, it may very well be discontinued at some point or replaced with something that makes more sense.

## Installing / Running

You're assumed to know how to use Python and how to use virtual environments or how to install Python requirements on your operating system. The required Python libraries are listed in `requirements.txt`. So-called "frozen" requirements are listed in `requirements-frozen.txt`, which contain prerequisited of libraries with the version numbers that were known to work at some point.

```
pip install -r requirements.txt
```

If that fails, try using the "frozen" list:

```
pip install -r requirements-frozen.txt
```

To run, simply run the script with the law number and year that you wish to clean up. You can also choose to clean up everything, which may take a while.

### Examples:

The Constitution of the Republic of Iceland:

```
python althingi-document-cleaner 33/1944
```

The general criminal code:

```
python althingi-document-cleaner 19/1940
```

Clean up everything (may take a while):

```
python althingi-document-cleaner -a
```

## License

See the document `LICENSE.md`. (It's MIT.)
