import yaml
import tomllib
import argparse
import logging
import shutil
from pathlib import Path
import jsonschema
import json
from subprocess import check_output

INVENTORY_ROOT = 'inventory_root'
HOST_JSONSCHEMA = 'host_jsonschema'
JSONSCHEMAS = 'jsonschemas'

def main():
    logging.basicConfig(level=logging.DEBUG)

    # Required to ignore vault tags in yaml files
    CustomLoader.add_constructor(u'!vault', CustomLoader.let_tag_thru)
    print("Hello from ansible-inv-validator!")
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", required=True)

    args = parser.parse_args()

    config_path = args.config

    ############################################################################
    # Pre-flight checks
    ############################################################################

    missing_deps = []
    deps = ["jq", "ansible-inventory"]

    for dep in deps:
        logging.debug(f'''msg="checking if dependency on PATH" dep={dep}''')
        if shutil.which(dep) is None:
            logging.error(f'''msg="dependency missing" dep={dep}''')
            missing_deps.append(dep)
        else:
            logging.info(f'''msg="dependency found!" dep={dep}''')

    if missing_deps:
        logging.error(f"missing dependencies: {','.join(missing_deps)} - Exiting")
        # exit(1)

    # Read config
    config = None
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    if config is None:
        logging.error(f'''msg="failed to read config file. Exiting" file={config_path}''')
    print(config)

    # Find the number of inventories in the root inventory folder
    target_dir = Path(config[INVENTORY_ROOT])
    subdirs = [entry for entry in target_dir.iterdir() if entry.is_dir()]
    logging.info(f'''msg="found subdirs from given config path" config_path={target_dir.resolve()} count={len(subdirs)} subdirs="{','.join([x.name for x in subdirs])}"''')


    # 
    for subdir in subdirs:
        logging.info(f'''msg="beginning validation of inventory" path={subdir}''')

        ########################################################################
        # Run host validation
        ########################################################################

        if len(config[HOST_JSONSCHEMA]) == 0:
            logging.debug(f'''msg="config key host_jsonschema was empty. Skipping host checks" config_path={config_path}''')
        else:
            # Get the hosts in JSON format
            hosts_cmd = f"ansible-inventory -i {subdir} --list | jq -c '._meta.hostvars | to_entries | map(.value + {{id: .key}}) | .[]'"
            logging.debug(f'''msg="executing shell command" cmd="{hosts_cmd}"''')
            hosts_jsonl = check_output(hosts_cmd, shell=True).decode().strip()
            # print(f"XXX: {hosts_jsonl}")

            # Load jsonschema
            host_jsonschema = None
            with open(config[HOST_JSONSCHEMA], "rb") as f:
                # TODO: Perform json validation
                host_jsonschema = json.load(f)

            validator = jsonschema.Draft202012Validator(host_jsonschema)
            for host in hosts_jsonl.split('\n'):
                host_parsed = json.loads(host)
                try:
                    validator.validate(host_parsed)
                except jsonschema.ValidationError as e:
                    print(f"{e}")

        ########################################################################
        # Run all user defined json schema variables
        ########################################################################
        for schema in config[JSONSCHEMAS]:
            # Read yaml into python dict
            target_path = Path(f"{subdir}/{schema['path']}")
            target_yaml = None
            logging.info(f'''msg="loading yaml file for user defined jsonschema checking" file={target_path}''')
            with open(target_path, "rb") as f:
                target_yaml = yaml.load(f, Loader=CustomLoader)
            if target_yaml is None:
                logging.warn(f'''msg="target yaml was empty. Skipping udf schema and moving on" file={target_path}''')
                continue

            # Get the jsonschema
            schema_path = schema['jsonschema']
            udf_schema = None
            with open(schema_path, "rb") as f:
                udf_schema = json.load(f)
            udf_validator = jsonschema.Draft202012Validator(udf_schema)

            try:
                logging.info(f'''running jsonschema schema={schema_path} target={target_path}''')
                udf_validator.validate(target_yaml)
            except jsonschema.ValidationError as e:
                print(f"{e}")
        



    # For each subdir, run the json schema batch
    # for 


class CustomLoader(yaml.SafeLoader):
    def let_tag_thru(self, node):
        return self.construct_scalar(node)

if __name__ == "__main__":
    main()
