#!/usr/bin/env python3
# XML or JSON to ElasticSearch
#
# Smári McCarthy <smari AT ecosophy.is>
# Date: 2024-06-03
# 
# This does the following:
#  - Generate JSON from the XML
#  - Insert JSON into ElasticSearch
#
# There are assumptions:
#  - The filenames are unique for the index
#  - That the filenames are acceptable ID's for documents in the index
#  - That the XML and JSON files have the same name
#

import os
import click
import xmljson
import json
import xml.etree.ElementTree as ET
from elasticsearch import Elasticsearch, ConnectionError, AuthenticationException, AuthorizationException


settings = {
    'xml_dir': 'data/xml/',
    'json_dir': 'data/json/',
    'elastic_server': 'https://localhost:9200',
    'elastic_index': None,
    'elastic_apikey': None,
    'elastic_user': None,
    'elastic_password': None
}

@click.group()
@click.option('--xml-dir',                default='data/xml/',  help='Directory containing the XML files')
@click.option('--json-dir',               default='data/json/', help='Directory to store/retrieve the JSON files')
@click.option('--elastic-server',         default=lambda: os.environ.get('ELASTIC_SERVER', 'https://localhost:9200'), help='ElasticSearch server')
@click.option('--elastic-index',          default=lambda: os.environ.get('ELASTIC_INDEX'), help='ElasticSearch index')
@click.option('--elastic-apikey',         default=lambda: os.environ.get('ELASTIC_APIKEY'), help='ElasticSearch API Key')
@click.option('--elastic-user',           default=lambda: os.environ.get('ELASTIC_USER'), help='ElasticSearch user')
@click.option('--elastic-password',       default=lambda: os.environ.get('ELASTIC_PASSWORD'), help='ElasticSearch password')
def cli(xml_dir: str, json_dir: str, 
         elastic_server: str, elastic_index: str, elastic_apikey: str, elastic_user: str, elastic_password: str
    ):

    settings['xml_dir'] = xml_dir
    settings['json_dir'] = json_dir
    settings['elastic_server'] = elastic_server
    settings['elastic_index'] = elastic_index
    settings['elastic_apikey'] = elastic_apikey
    settings['elastic_user'] = elastic_user
    settings['elastic_password'] = elastic_password    



@cli.command()
def generate_json():
    """Generate JSON from the XML files in the given xml directory"""

    xml_dir = settings['xml_dir']
    json_dir = settings['json_dir']

    print("Generating JSON from XML")
    files = os.listdir(xml_dir)

    # Ensure the JSON directory exists
    if not os.path.exists(json_dir):
        os.makedirs(json_dir)

    count = len(files)
    idx = 0

    for file in files:
        try:
            idx += 1
            print(f"{idx:<4}/{count:<4}: {file:<20}", end='\r')

            tree = ET.parse(xml_dir + file)
            root = tree.getroot()

            # Convert the XML to JSON
            structure = xmljson.abdera.data(root, int_type=str)

            open(json_dir + file.replace('.xml', '.json'), 'w').write(json.dumps(structure, indent=2))
        except ET.ParseError as e:
            print(f"Error parsing XML file {file}. Skipping...")
            continue

    print("JSON generated successfully")


def get_elasticsearch() -> Elasticsearch:
    elastic_server = settings['elastic_server']
    elastic_apikey = settings['elastic_apikey']
    elastic_user = settings['elastic_user']
    elastic_password = settings['elastic_password']

    if not elastic_server:
        print("ElasticSearch server not provided. Exiting...")
        return None

    authtype = None
    if elastic_apikey:
        authtype = "apikey"
    elif elastic_user and elastic_password:
        authtype = "basic"
    else:
        print("No authentication provided. Exiting...")
        return None

    print(f"Connecting to elasticSearch server {elastic_server} with {authtype} authentication...")

    try:
        # Retrieve the JSON from ElasticSearch
        if authtype == "apikey":
            es = Elasticsearch(elastic_server, api_key=elastic_apikey)
        elif authtype == "basic":
            es = Elasticsearch(elastic_server, basic_auth=(elastic_user, elastic_password))

        info = es.info()
        print(f"Connected to ElasticSearch server {info['name']} version {info['version']['number']}")

    except ConnectionRefusedError:
        print("Could not connect to ElasticSearch server. Exiting...")
        return None
    except ConnectionAbortedError:
        print("Connection to ElasticSearch server aborted. Exiting...")
        return None
    except ConnectionError as e:
        print(f"Error connecting to ElasticSearch server: {e}. Exiting...")
        return None
    except AuthenticationException as e:
        print(f"Error authenticating to ElasticSearch server: {e}. Exiting...")
        return None
    except AuthenticationException as e:
        print(f"Error authorizing to ElasticSearch server: {e}. Exiting...")
        return None
        
    return es


@cli.command()
@click.argument('mapping', type=click.File('r'))
def add_mapping(mapping: click.File):
    """Set a mapping for an index in ElasticSearch"""
    index = settings['elastic_index']
    if not index:
        print("ElasticSearch index not provided. Exiting...")
        return
    
    print(f"Setting mapping for index {index}")

    try:
        mapping = json.load(mapping)
    except json.JSONDecodeError:
        print(f"Error parsing mapping JSON. Exiting...")
        return

    es = get_elasticsearch()
    if not es:
        return

    try:
        es.indices.create(index=index, body=mapping)
    except Exception as e:
        print(f"Error setting mapping for index {index}: {e}. Exiting...")
        return

    print(f"Mapping set for index {index}")


@cli.command()
def delete_mapping():
    """Delete the mapping for an index in ElasticSearch"""

    index = settings['elastic_index']
    if not index:
        print("ElasticSearch index not provided. Exiting...")
        return
    
    print(f"Deleting mapping for index {index}")

    es = get_elasticsearch()
    if not es:
        return

    try:
        es.indices.delete(index=index)
    except Exception as e:
        print(f"Error deleting mapping for index {index}: {e}. Exiting...")
        return

    print(f"Mapping deleted for index {index}")


@cli.command()
def update():
    """Update ElasticSearch with the JSON files in the given json directory"""

    json_dir = settings['json_dir']
    elastic_index = settings['elastic_index']

    es = get_elasticsearch()
    if not es:
        return

    if not os.path.exists(json_dir):
        print(f"JSON directory {json_dir} does not exist. Exiting...")
        return
        
    files = os.listdir(json_dir)
    count = len(files)
    idx = 0

    for file in files:
        idx += 1
        print(f"{idx:<4}/{count:<4}: {file:<20}", end='\r')

        data = json.load(open(json_dir + file))
        id = file.replace('.json', '')

        # Insert the data into ElasticSearch
        es.index(index=elastic_index, id=id, document=data)


#@click.option('--generate/--no-generate', default=True,         help='Generate JSON from the XML')
#@click.option('--update/--no-update',     default=True,         help='Insert the JSON into ElasticSearch')
#@click.option('--add-mapping',            type=click.File('r'), help='Add mapping to ElasticSearch')


if __name__ == '__main__':
    cli()