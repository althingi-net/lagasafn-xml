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
            structure = xmljson.abdera.data(root)

            open(json_dir + file.replace('.xml', '.json'), 'w').write(json.dumps(structure, indent=2))
        except ET.ParseError as e:
            print(f"Error parsing XML file {file}. Skipping...")
            continue

    print("JSON generated successfully")


def update_elasticsearch(json_dir: str, elastic_server: str, elastic_index: str, elastic_apikey: str, elastic_user: str, elastic_password: str):
    if not elastic_server or not elastic_index:
        print("ElasticSearch server or index not provided. Exiting...")
        return
    
    if not os.path.exists(json_dir):
        print(f"JSON directory {json_dir} does not exist. Exiting...")
        return
        
    authtype = None
    if elastic_apikey:
        authtype = "apikey"
    elif elastic_user and elastic_password:
        authtype = "basic"
    else:
        print("No authentication provided. Exiting...")
        return
    
    print(f"Inserting JSON into ElasticSearch server {elastic_server}/{elastic_index} with {authtype} authentication")

    try:
        # Insert or update the JSON into ElasticSearch.
        if authtype == "basic":
            es = Elasticsearch(elastic_server, api_key=elastic_apikey)
        elif authtype == "apikey":
            es = Elasticsearch(elastic_server, basic_auth=(elastic_user, elastic_password))

        files = os.listdir(json_dir)

        for file in files:
            data = json.load(open(json_dir + file))

            id = file.replace('.json', '')

            # Insert the data into ElasticSearch
            es.index(index=elastic_index, id=id, document=data)

    except ConnectionRefusedError:
        print("Could not connect to ElasticSearch server. Exiting...")
        return
    except ConnectionAbortedError:
        print("Connection to ElasticSearch server aborted. Exiting...")
        return
    except ConnectionError as e:
        print(f"Error connecting to ElasticSearch server: {e}. Exiting...")
        return
    except AuthenticationException as e:
        print(f"Error authenticating to ElasticSearch server: {e}. Exiting...")
        return
    except AuthenticationException as e:
        print(f"Error authorizing to ElasticSearch server: {e}. Exiting...")
        return

    

@click.command()
@click.option('--xml-dir',                default='data/xml/',  help='Directory containing the XML files')
@click.option('--json-dir',               default='data/json/', help='Directory to store/retrieve the JSON files')
@click.option('--generate/--no-generate', default=True,         help='Generate JSON from the XML')
@click.option('--update/--no-update',     default=True,         help='Insert the JSON into ElasticSearch')
@click.option('--elastic-server',         default=lambda: os.environ.get('ELASTIC_SERVER', 'https://localhost:9200'), help='ElasticSearch server')
@click.option('--elastic-index',          default=lambda: os.environ.get('ELASTIC_INDEX'), help='ElasticSearch index')
@click.option('--elastic-apikey',         default=lambda: os.environ.get('ELASTIC_APIKEY'), help='ElasticSearch API Key')
@click.option('--elastic-user',           default=lambda: os.environ.get('ELASTIC_USER'), help='ElasticSearch user')
@click.option('--elastic-password',       default=lambda: os.environ.get('ELASTIC_PASSWORD'), help='ElasticSearch password')
def main(xml_dir: str, json_dir: str, generate: bool, update: bool, elastic_server: str, elastic_index: str, elastic_apikey: str, elastic_user: str, elastic_password: str):    
    if generate:
        generate_json(xml_dir, json_dir)

    if update:
        update_elasticsearch(json_dir, elastic_server, elastic_index, elastic_apikey, elastic_user, elastic_password)


if __name__ == '__main__':
    main()