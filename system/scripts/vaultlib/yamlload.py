"""YAML loading that keeps every scalar a string (spec §6.15)."""
import yaml

_DROP = {
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:timestamp",
}


class StringLoader(yaml.SafeLoader):
    """SafeLoader whose implicit resolvers never produce non-string scalars."""


StringLoader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag not in _DROP]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(text: str):
    """Parse YAML text. Scalars are always str; an empty document returns None."""
    return yaml.load(text, Loader=StringLoader)
