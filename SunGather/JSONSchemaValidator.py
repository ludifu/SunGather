#!/usr/bin/python3

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource
import json
from json import JSONDecodeError
import logging
from pathlib import Path
import os


class JSONSchemaValidator:
    # This class provides a schema validation service for
    # registers-sungrow.yaml and the config.yaml files. Files passing these
    # tests are structurally validated.

    # Note the error messages of the underlying json-schema implementation in
    # case of validation errors are far from good. Such messages often lack the
    # required context to understand what caused a problem and where the
    # problem is located in the file.  This is imostly an implementation
    # weakness of the used libraries.

    # The json schema files must be located within a subdirectory ´json_schema`
    # of the location of this file. This class will read all *.json files
    # within this directory and add them to its internal registry:
    SCHEMA_FILE_PATH = Path(os.path.abspath(os.path.dirname(__file__))) / "json_schema"

    # The schema urn's for register-sungrow.yaml and config.yaml files.
    ROOT_SCHEMA_URN_REGISTERS = "urn:sungatherevo:registers"
    ROOT_SCHEMA_URN_CONFIG = "urn:sungatherevo:config"

    def __init__(self):
        # Initialize an empty registry:
        self.registry = Registry()
        # ... and populate the registry from the file system:
        if self._populate_schema_registry():
            logging.debug("Successfully populated schema registry.")
        else:
            logging.warning(
                "Creating the json schema registry failed, subsequent validation attempts will probably fail!"
            )

    def validate_registers_file(self, loaded_yaml):
        # Validate the loaded file against the schema for the
        # registers-sungrow.yaml file. Return True on successful validation,
        # False otherwise.
        return self._validate_file(loaded_yaml, self.ROOT_SCHEMA_URN_REGISTERS)

    def validate_config_file(self, loaded_yaml):
        # Validate the loaded file against the schema for the config.yaml file.
        # Return True on successful validation, False otherwise.
        return self._validate_file(loaded_yaml, self.ROOT_SCHEMA_URN_CONFIG)

    def _validate_file(self, loaded_yaml, schema_urn):
        # Peform the schema validation of a file against a provided schema. Log
        # any errors, then return True if no errors occurred, False otherwise.
        try:
            v = Draft202012Validator(
                self.registry.get_or_retrieve(schema_urn).value.contents,
                registry=self.registry,
            )
        except NoSuchResource:
            logging.error(
                f"Failed to retrieve the schema ´{schema_urn}` from the schema registry."
            )
            return False

        errors = sorted(v.iter_errors(loaded_yaml), key=lambda e: e.path)
        if len(errors) > 0:
            for error in errors:
                if len(error.context) > 0:
                    for suberror in error.context:
                        logging.error(
                            f"Schema validation error: {suberror.message}. Error occurred in path: {list(suberror.path)}"
                        )
                else:
                    logging.error(
                        f"Schema validation error: {error.message}. Error occurred in path: {list(error.path)}"
                    )
            return False
        else:
            return True

    def _populate_schema_registry(self):
        # Populate self.registry from the file system.  In case reading from
        # the path yields an error return False, otherwise True.
        with os.scandir(self.SCHEMA_FILE_PATH) as dir_entries:
            for entry in dir_entries:
                if (
                    not entry.name.startswith(".")
                    and entry.name.endswith(".json")
                    and entry.is_file()
                ):
                    if not self._add_entry_to_registry(entry):
                        return False
        return True

    def _add_entry_to_registry(self, entry):
        # Add an entry from a json schema file as a Resource into
        # self.registry. Return True on success, False in case of errors of any
        # kind.
        schema = None
        try:
            with open(entry, "r") as f:
                try:
                    schema = json.loads(f.read())
                except JSONDecodeError as de:
                    logging.error(
                        f"Error decoding json schema file ´{entry.name}`: ", de
                    )
                    return False
        except Exception as err:
            logging.error(f"Error reading file ´{entry.name}`: ", err)
            return False
        res = Resource.from_contents(schema)
        if res is not None:
            self.registry = res @ self.registry
            return True
        else:
            logging.error("Failed to create a Resource from a loaded schema.")
            return False
