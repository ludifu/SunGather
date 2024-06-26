#!/usr/bin/python3

import logging
import yaml
import re
import sys
from JSONSchemaValidator import JSONSchemaValidator


class FieldConfigurator:
    def __init__(self, registers_filename, register_patch_config=None):
        # Filename of the yaml file to read register definitions from
        self._registers_filename = registers_filename

        # part of the configuration containing register patches
        self._patches = register_patch_config

        # The contents of the registers configuration file
        self.registers = None

    def get_register_config(self):
        # Return a fully configured lits of registers to read from the
        # inverter.  This includes reading the register definitions from a
        # configuration file, then applying the register patches.
        self._load_registers()
        self._patch_registers()
        self.print_register_list()
        return self.registers

    def _load_registers(self):
        try:
            regs = yaml.safe_load(open(self._registers_filename, encoding="utf-8"))
            logging.info(
                f"Loaded {self._registers_filename}, file version: {regs.get('version','UNKNOWN')}"
            )
        except Exception as err:
            logging.critical(
                f"Failed loading registers from {self._registers_filename}: {err}"
            )
            sys.exit(1)

        v = JSONSchemaValidator()
        logging.info(
            f"Performing schema validation of registers file ´{self._registers_filename}` ..."
        )
        if v.validate_registers_file(regs):
            logging.info(
                f"... registers file ´{self._registers_filename}` successfully validated."
            )
        else:
            logging.critical(
                f"... Validation of registers file ´{self._registers_filename}` failed!"
            )
            sys.exit(1)

        # These checks are to allow empty lists of read and hold sections within
        # sections registers and scan. If these are empty in the yaml there will
        # not be an empty list. This is substituted here.
        if regs["registers"][0].get("read") is None:
            regs["registers"][0]["read"] = []
        if regs["registers"][1].get("hold") is None:
            regs["registers"][1]["hold"] = []
        if regs["scan"][0].get("read") is None:
            regs["scan"][0]["read"] = []
        if regs["scan"][1].get("hold") is None:
            regs["scan"][1]["hold"] = []

        self.registers = regs

    def _patch_registers(self):
        # Update the register_configuration with modifications defined in the config file.
        if self._patches is None:
            # section register_patches does not exist or does not have entries.
            return
        logging.info("Applying patches to register definitions ...")
        allregs = [
            *self.registers["registers"][0]["read"],
            *self.registers["registers"][1]["hold"],
        ]

        for patch in self._patches:
            self._apply_single_patch(patch, allregs)

        for reg in allregs:
            # only new registers have a type (assuming that no one tries to change the type of an attribute ...)
            if reg.get("type") == "read":
                self.registers["registers"][0]["read"].append(reg)
            elif reg.get("type") == "hold":
                self.registers["registers"][1]["hold"].append(reg)
        logging.info("... finished applying patches to register definitions.")

    def _apply_single_patch(self, patch, allregs):
        # Apply one patch. A patch contains one or more attributes with
        # values to add or change in one or more registers.
        reg_name = patch.get("name")
        if reg_name is None:
            logging.error(f"´name` attribute missing, ignoring entry: {patch}.")
            return
        for attribute_name in list(patch):
            if attribute_name == "name":
                # value of attribute ´name` is for matching the register,
                # it doesn't contain a value for patching.
                continue
            attribute_value = patch.get(attribute_name)
            self._patch_attribute(reg_name, attribute_name, attribute_value, allregs)

    def _check_patch_value(self, attribute_name, attribute_value):
        # Check whether the type of attribute_value is allowed for
        # attribute_name and return True, otherwise return False.
        if attribute_name in [
            "address",
            "level",
            "length",
            "update_frequency",
        ] and not isinstance(attribute_value, int):
            logging.error(
                f"Trying to patch {attribute_name} to value ´{attribute_value}` failed. "
                + "Attributes ´level`, ´address`, ´length`, ´undate_frequency` "
                + "must not be patched to anything but an Integer!"
            )
            return False
        elif attribute_name in [
            "unit",
            "datatype",
            "change_name_to",
        ] and not isinstance(attribute_value, str):
            logging.error(
                f"Trying to patch {attribute_name} to value ´{attribute_value}` failed. "
                + "Attributes ´unit`, ´datatype` must not be patched to anything but a String!"
            )
            return False
        elif attribute_name in ["accuracy"] and not isinstance(attribute_value, float):
            logging.error(
                f"Trying to patch {attribute_name} to value ´{attribute_value}` failed. "
                + "Attribute ´accuracy` must not be patched to anything but a float!"
            )
            return False
        return True

    def _patch_attribute(self, reg_name, attribute_name, attribute_value, allregs):
        # Patch one attribute in all registers which match reg_name.
        if not self._check_patch_value(attribute_name, attribute_value):
            return False
        try:
            p = re.compile(reg_name)
        except re.error:
            logging.error(f"´{reg_name}` is not a valid ´name`!")
            return False

        # Try to find matches (may be more than one) and execute the patch:
        pattern_did_match = False
        for reg in allregs:
            if p.fullmatch(reg.get("name")):
                pattern_did_match = True
                self._patch_register(reg, attribute_name, attribute_value)

        # If there was no match for an existing register, then this entry is
        # intended to create a new register!
        if not pattern_did_match:
            newreg = {}
            newreg["name"] = reg_name
            logging.debug(f"Adding new register ´{reg_name}`.")
            self._patch_register(newreg, attribute_name, attribute_value)
            allregs.append(newreg)
            # This still needs to be added to the ´read` or ´hold` register lists later!
        return True

    def _patch_register(self, reg, attribute_name, attribute_value):
        # Add or change one attribute (named attribute_name) to the value
        # attribute_value in one register (reg).

        # First check whether this entry is to rename an attribute:
        if attribute_name == "change_name_to":
            # switch attribute_name to "name" will have the register name changed:
            attribute_name = "name"

        if reg.get(attribute_name):
            if reg.get(attribute_name) == attribute_value:
                # No need for a change, the attribute is already set to attribute_value.
                logging.debug(
                    f"Patching register ´{reg.get('name')}`: attribute {attribute_name} "
                    + f"was already set to {attribute_value} (not changed)."
                )
            else:
                # We will overwrite an existing value.
                logging.debug(
                    f"Patching register ´{reg.get('name')}`: {attribute_name} = {attribute_value} "
                    + f"(previous value was {reg.get(attribute_name)})."
                )
        else:
            # The attribute will be added to this register.
            logging.debug(
                f"Patching register ´{reg.get('name')}`: adding attribute {attribute_name} = {attribute_value}."
            )
        reg[attribute_name] = attribute_value

    def print_register_list(self):
        max_name_len = 1
        for reg in self.registers["registers"][0]["read"]:
            max_name_len = max(max_name_len, len(reg["name"]))
        for reg in self.registers["registers"][1]["hold"]:
            max_name_len = max(max_name_len, len(reg["name"]))
        table_width = 89 - 44 + max_name_len

        bar = "+" + str.ljust("", table_width, "-") + "+"

        print(bar)
        print(
            "| "
            + str.ljust("Register definitions after applying patches.", table_width - 2)
            + " |"
        )
        print(
            "| "
            + str.ljust(
                "Note: The list is not (yet) filtered by supported models!",
                table_width - 2,
            )
            + " |"
        )
        print(bar)
        print(
            "| "
            + str.ljust("register name", max_name_len)
            + " | {:^5} | {:<4} | {:^5} | {:>5} |{:^3}| {:^5} |".format(
                "unit", "type", "freq.", "addr", "lvl", "slave"
            )
        )
        print(bar)
        for reg in self.registers["registers"][0]["read"]:
            print(
                "| "
                + str.ljust(reg.get("name"), max_name_len)
                + " | {:^5} | {:<4} | {:^5} | {:>5} |{:^3}| {:^5} |".format(
                    reg.get("unit", ""),
                    "read",
                    reg.get("update_frequency", ""),
                    reg.get("address", "-----"),
                    reg.get("level", "-"),
                    reg.get("slave", " "),
                )
            )
        for reg in self.registers["registers"][1]["hold"]:
            print(
                "| "
                + str.ljust(reg.get("name"), max_name_len)
                + " | {:^5} | {:<4} | {:^5} | {:>5} |{:^3}| {:^5} |".format(
                    reg.get("unit", ""),
                    "read",
                    reg.get("update_frequency", ""),
                    reg.get("address", "-----"),
                    reg.get("level", "-"),
                    reg.get("slave", " "),
                )
            )
        print(bar)
