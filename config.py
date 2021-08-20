# Manage config.toml file

import toml


def load_config(filename: str) -> dict:
    """
    Load a configuration from the provided toml file if it exists or generate
    a file with default configs otherwise.
    """
    configs: dict = {}
    try:
        with open(filename) as file:
            configs = toml.load(file)
    except FileNotFoundError:
        pass

    write = False
    if "login" not in configs:
        write = True
        configs["login"] = ""
    if "password" not in configs:
        write = True
        configs["login"] = ""

    if write:
        with open(filename, "w") as file:
            toml.dump(configs, file)

    return configs
