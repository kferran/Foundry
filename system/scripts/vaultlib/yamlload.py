"""YAML loading that keeps every scalar a string (spec §6.15)."""
import yaml

_DROP = {
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:timestamp",
    "tag:yaml.org,2002:merge",
    "tag:yaml.org,2002:value",
}


class StringLoader(yaml.SafeLoader):
    """SafeLoader whose implicit resolvers never produce non-string scalars."""


StringLoader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag not in _DROP]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

# Register string constructor for explicit tags that would normally type-convert.
# PyYAML copies the constructor dict on first add_constructor for a subclass,
# so this does not mutate SafeLoader's constructor table.
for tag in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float", "tag:yaml.org,2002:null", "tag:yaml.org,2002:timestamp"}:
    StringLoader.add_constructor(tag, yaml.constructor.SafeConstructor.construct_yaml_str)


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            dup = key in seen
        except TypeError:
            continue
        if dup:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StringLoader.construct_mapping = _construct_mapping


def load(text: str):
    """Parse YAML text. Scalars are always str; an empty document returns None."""
    return yaml.load(text, Loader=StringLoader)
