# Refbuilder

This directory contains tools for producing a list of backreferences from Icelandic law XML files, by
processing the natural language text and detecting text that refers to other laws.

The main script here is `refbuilder.py`, which can be run like so:
```
python refbuilder.py process path/to/law.xml
```

We assume XML files are in the althingi.net XML format.

## Requirements

First, you'll need dependencies:
```
pip install requirements.txt
```

Next you'll need to edit `.env` and make sure it has the appropriate values set up. See `.env.template`.


## OpenAI Assistant setup

Currently this tool depends on the OpenAI Assistant API for natural language processing steps. Note that
using this will incur API costs.

If you don't have an Assistant set up already, the following command will help you get set up:
```
python refbuilder.py make-assistant
```
It will output an ID that you can put in your `.env` file.

You can use the `--prompt-file` option to determine which prompt file to use. If none is selected, the
most recent version from the `prompts/` folder will be used.

If you want to update the assistant, you can do so via the OpenAI assistants editor, or using the
command:

```
python refbuilder.py update-assistant
```
with the parameters it offers.


# TODO

 * [ ] Have prompt files include info to define which model they prefer and such.
 * [ ] Handle automatic partitioning of inputs into smaller units if the law is too big for the model.
