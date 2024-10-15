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


def generate_json(xml_dir: str, json_dir: str):
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


def get_elasticsearch(elastic_server: str, elastic_apikey: str, elastic_user: str, elastic_password: str) -> Elasticsearch:
    if not elastic_server or not elastic_index:
        print("ElasticSearch server or index not provided. Exiting...")
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
    
    info = es.info()
    print(f"Connected to ElasticSearch server {info['name']} version {info['version']['number']}")
    
    return es


def set_elasticsearch_mapping(es: Elasticsearch, index: str, mapping: dict):
    print(f"Setting mapping for index {index}")

    try:
        es.indices.create(index=index, body=mapping)
    except Exception as e:
        print(f"Error setting mapping for index {index}: {e}. Exiting...")
        return

    print(f"Mapping set for index {index}")


def update_elasticsearch(json_dir: str, es: Elasticsearch, elastic_index: str):    
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


@click.command()
@click.option('--xml-dir',                default='data/xml/',  help='Directory containing the XML files')
@click.option('--json-dir',               default='data/json/', help='Directory to store/retrieve the JSON files')
@click.option('--generate/--no-generate', default=True,         help='Generate JSON from the XML')
@click.option('--update/--no-update',     default=True,         help='Insert the JSON into ElasticSearch')
@click.option('--add-mapping',            type=click.File,      help='Add mapping to ElasticSearch')
@click.option('--elastic-server',         default=lambda: os.environ.get('ELASTIC_SERVER', 'https://localhost:9200'), help='ElasticSearch server')
@click.option('--elastic-index',          default=lambda: os.environ.get('ELASTIC_INDEX'), help='ElasticSearch index')
@click.option('--elastic-apikey',         default=lambda: os.environ.get('ELASTIC_APIKEY'), help='ElasticSearch API Key')
@click.option('--elastic-user',           default=lambda: os.environ.get('ELASTIC_USER'), help='ElasticSearch user')
@click.option('--elastic-password',       default=lambda: os.environ.get('ELASTIC_PASSWORD'), help='ElasticSearch password')
def main(xml_dir: str, json_dir: str, generate: bool, update: bool, add_mapping: click.File, 
         elastic_server: str, elastic_index: str, elastic_apikey: str, elastic_user: str, elastic_password: str
        ):
    if generate:
        generate_json(xml_dir, json_dir)

    if add_mapping or update:
        es = get_elasticsearch(elastic_server, elastic_apikey, elastic_user, elastic_password)

        if add_mapping:
            set_elasticsearch_mapping(es, elastic_index, json.load(add_mapping))

        if update:
            update_elasticsearch(json_dir, es, elastic_index)


if __name__ == '__main__':
    main()