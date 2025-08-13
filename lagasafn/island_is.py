import json
import requests


def island_is_query(operation: str, input: dict):
    """
    Utility function for abstracting boilerplate away when dealing with data
    from Island.is.

    The URL to Island.is has "graphql" in it and returns results with type
    information, but doesn't seem to actually use GraphQL queries, or at least
    not in the way that GraphQL usually is, but rather more similarly to how
    REST is typically used.

    This is not a problem, but may signal that the API is likely to change.
    """
    base_url = "https://island.is/api/graphql"

    # Example operation: "Adverts"
    #
    # Example input:
    #
    #     input = {
    #         "department": ["a-deild"],
    #         "category": [""],
    #         "involvedParty": [""],
    #         "type": [""],
    #         "search": "",
    #         "page": 1
    #      }

    # Encode the input.
    q_variables = json.dumps({"input": input})

    # Taken from a real-life query. We don't know what this does yet, but it is
    # required to get the results we need.
    q_extensions = json.dumps({
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "ac5e448c4231814ce601406d40fee2361cace9cd80c731961d7195ada870fc25"
        }
    })

    # One step at a time so that it's obvious what's going wrong when something
    # does go wrong.
    url = f"{base_url}?{operation}&variables={q_variables}&extensions={q_extensions}"
    response = requests.get(url)
    content = response.content
    data = json.loads(content)["data"]
    return data
