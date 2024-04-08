#!/usr/bin/env python3
import click
import dotenv
import json
import openai
import os
import time
from openai import OpenAI
from lxml import etree

PROMPT_PATH = "prompts/"

dotenv.load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
assistant = os.getenv("OPENAI_ASSISTANT_ID")

all_references = []
most_recent_prompt = ""


def find_most_recent_prompt():
    """
    Prompt files have version numbers in their names. This function finds the
    most recent one.
    Example: "v0.02.txt" is more recent than "v0.01.txt".
    """
    global most_recent_prompt

    def find_highest_version_filename(folder_path):
        highest_version = -1
        highest_version_filename = ""

        for filename in os.listdir(folder_path):
            if filename.startswith("v") and filename.endswith(".txt"):
                # Converting this to float is dumb but good enough for now.
                version = float(filename[1:-4])  # Remove "v" and ".txt"
                if version > highest_version:
                    highest_version = version
                    highest_version_filename = filename

        return highest_version_filename

    most_recent_prompt = find_highest_version_filename(PROMPT_PATH)


def check_status(run_id, thread_id):
    run = client.beta.threads.runs.retrieve(
        thread_id=thread_id,
        run_id=run_id,
    )
    return run.status


def wait_on_run(run, thread, article=None):
    SLEEP_TIME = 0.5
    total = 0
    status = ""
    while status != "completed":
        status = check_status(run.id, thread.id)
        print(
            "\r[%0.2lf][%s] Waiting (article %s)         " % (total, status, article),
            end="",
        )
        total += SLEEP_TIME
        time.sleep(SLEEP_TIME)
    print("\r[%0.2lf][%s] Done                  " % (total, status), end="\n")


def get_references_from_article(xml_struct):
    obj_xml = etree.tostring(
        xml_struct, pretty_print=False, xml_declaration=False, encoding="utf-8"
    ).decode("utf-8")
    obj_xml = str(obj_xml)

    thread = client.beta.threads.create()

    message = client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=obj_xml
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant,
    )

    wait_on_run(run, thread, article=xml_struct.attrib.get("nr", "unknown"))

    messages = client.beta.threads.messages.list(
        thread_id=thread.id, order="asc", after=message.id
    )

    refs = []
    for m in messages:
        for t in m.content:
            try:
                newrefs = json.loads(t.text.value)
            except json.decoder.JSONDecodeError:
                print(f"JSON decode error. Input was: '{t.text.value}'")
                continue
            refs += newrefs

    return obj_xml, refs


def process_xml(tree, output):
    for item in tree:
        if item.tag == "chapter":
            process_xml(item, output)

        if item.tag == "art":
            for a in item.findall("footnote"):
                print(f"Removed footnote '{a}'")
                item.remove(a)
            xml, references = get_references_from_article(item)
            all_references.append((xml, references))

        # Do this after each item has been processed, so that we don't lose any data if the script crashes
        output.truncate(0)
        output.seek(0)
        json.dump(all_references, output, indent=2)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("input", type=click.File("rb"))
@click.option(
    "--output",
    type=click.Path(),
    default="output.json",
    help="The output file to write to.",
)
def process(input, output):
    inxml = input.read()
    tree = etree.fromstring(inxml)

    output = open(output, "w+")

    if len(tree) == 0:
        print("No items found in XML. Exiting.")
        return

    if assistant == "":
        print(
            "You don't have an assistant set up in .env. Fix this before trying to process anything!"
        )
        return

    try:
        client.beta.assistants.retrieve(assistant_id=assistant)
    except openai.NotFoundError:
        print("Assistant not found. Update it with 'update_assistant' command.")
        return

    process_xml(tree, output)


@cli.command()
@click.option(
    "--model",
    default="gpt-3.5-turbo",
    help="The model to use for the assistant. Check available models on OpenAI Documentation.",
)
@click.option(
    "--prompt-file",
    type=click.Path(),
    default="",
    help="The prompt file to use. Check the prompts/ folder for available prompts or make your own.",
)
@click.option("--name", default="Reference Builder", help="The name of the assistant.")
def make_assistant(prompt_file, model, name):
    global assistant
    if assistant != "":
        print(
            "You already have an assistant set up. Unset the value in .env if you want to make a new one."
        )
        return

    if prompt_file == "":
        prompt_file = PROMPT_PATH + most_recent_prompt
        print("No prompt file supplied. Using most recent prompt file: " + prompt_file)
    prompt = open(prompt_file, "r").read()

    print(f"Creating assistant.\nModel: {model}\nPrompt: '''\n{prompt}\n'''")
    new_assistant = client.beta.assistants.create(
        name=name,
        instructions=prompt,
        model=model,
    )
    print("Assistant ID: " + new_assistant.id)


@cli.command()
@click.option(
    "--model",
    default="gpt-3.5-turbo",
    help="The model to use for the assistant. Check available models on OpenAI Documentation.",
)
@click.option(
    "--prompt-file",
    type=click.Path(),
    default="",
    help="The prompt file to use. Check the prompts/ folder for available prompts or make your own.",
)
@click.option("--name", default="Reference Builder", help="The name of the assistant.")
def update_assistant(prompt_file, model, name):
    global assistant
    if assistant == "":
        print(
            "You don't have an assistant set up in .env. Fix this before trying to update anything!"
        )

    if prompt_file == "":
        prompt_file = PROMPT_PATH + most_recent_prompt
        print("No prompt file supplied. Using most recent prompt file: " + prompt_file)

    prompt = open(prompt_file, "r").read()

    print(f"Updating assistant.\nModel: {model}\nPrompt: '''\n{prompt}\n'''")
    updated_assistant = client.beta.assistants.update(
        assistant_id=assistant,
        name=name,
        instructions=prompt,
        model=model,
    )
    print("Assistant updated.")


if __name__ == "__main__":
    find_most_recent_prompt()
    cli()
