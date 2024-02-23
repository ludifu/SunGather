#!/usr/bin/python3

from SungrowClient import SungrowClient
from version import __version__

import importlib
import logging
import logging.handlers
import sys
import getopt
import yaml
import time
import re
import os


def main():
    app_args = read_arguments_from_commandline()
    app_config = load_config_file(app_args["configfilename"])
    inverter_config = get_inverter_config(app_config)
    setup_log_levels_and_log_file(
        app_args["loglevel"],
        app_args["logfolder"],
        inverter_config["log_file"],
        inverter_config["log_console"],
    )

    print_welcome_message(app_args, inverter_config)

    check_config(app_config, inverter_config)

    register_config = load_registers(app_config, app_args["registersfilename"])

    inverter = setup_inverter(inverter_config, register_config)

    exports = setup_exports(app_config, inverter)

    core_loop(
        inverter,
        exports,
        inverter_config.get("scan_interval"),
        app_args["runonce"],
    )


#######################################################################
# functions for app start, reading parameters and loading app
# configuration


def read_arguments_from_commandline():
    # These values are available to be changed by commandline arguments:
    app_args = {
        "configfilename": "config.yaml",
        "registersfilename": "registers-sungrow.yaml",
        "logfolder": "logs/",
        "loglevel": None,
        "runonce": False,
    }
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hc:r:l:v:", ["runonce", "help"])
    except getopt.GetoptError:
        logging.error(
            f"Error parsing command line! Run with option ´-h` to show usage information."
        )
        sys.exit(2)

    if opts and len(opts) == 0:
        logging.debug(f"No options passed via command line")
        return app_args

    for opt, arg in opts:
        if opt == "-h" or opt == "--help":
            print_synopsis()
            sys.exit()
        elif opt == "-c":
            app_args["configfilename"] = arg
        elif opt == "-r":
            app_args["registersfilename"] = arg
        elif opt == "-l":
            app_args["logfolder"] = arg
        elif opt == "-v":
            if arg.isnumeric() and int(arg) >= 0 and int(arg) <= 50:
                app_args["loglevel"] = int(arg)
            else:
                # Note: The default of 30 only applies, if the log level has not been set in the config file.
                logging.error(
                    f"Valid verbose options: 10 = Debug, 20 = Info, 30 = Warning (default), 40 = Error"
                )
                sys.exit(2)
        elif opt == "--runonce":
            app_args["runonce"] = True

    return app_args


def print_synopsis():
    print(f"\nSunGatherEvo {__version__}")
    print(f"usage: python3 sungather.py [options]")
    print(f"\nCommandline arguments override any config file settings.")
    print(f"Options and arguments:")
    print(f"-c config.yaml          : Specify config file.")
    print(f"-r registers-file.yaml  : Specify registers file.")
    print(f"-l logs/                : Specify folder to store logs.")
    print(
        f"-v 30                   : Logging Level, 10 = Debug, 20 = Info, 30 = Warning, 40 = Error"
    )
    print(f"--runonce               : Run once then exit.")
    print(f"-h                      : print this help message and exit.")
    print(f"\nExample:")
    print(f"python3 sungather.py -c /full/path/config.yaml\n")


def load_config_file(configfilename):
    try:
        configfile = yaml.safe_load(open(configfilename, encoding="utf-8"))
        logging.debug(f"Loaded config: {configfilename}")
    except Exception as err:
        logging.exception(f"Failed loading config: {configfilename} \n\t\t\t     {err}")
        sys.exit(1)
    if not configfile.get("inverter"):
        logging.critical(f"Failed loading config, missing Inverter settings")
        sys.exit(1)

    return configfile


def get_inverter_config(app_configuration):
    config_inverter = {
        "host": app_configuration["inverter"].get("host", "localhost"),
        "port": app_configuration["inverter"].get("port", 502),
        "timeout": app_configuration["inverter"].get("timeout", 10),
        "retries": app_configuration["inverter"].get("retries", 3),
        "slave": app_configuration["inverter"].get("slave", 0x01),
        "scan_interval": app_configuration["inverter"].get("scan_interval", 30),
        "connection": app_configuration["inverter"].get("connection", "modbus"),
        "model": app_configuration["inverter"].get("model", None),
        "smart_meter": app_configuration["inverter"].get("smart_meter", False),
        "use_local_time": app_configuration["inverter"].get("use_local_time", False),
        "log_console": app_configuration["inverter"].get("log_console", "WARNING"),
        "log_file": app_configuration["inverter"].get("log_file", "OFF"),
        "level": app_configuration["inverter"].get("level", 1),
        "dyna_scan": app_configuration["inverter"].get("dyna_scan", False),
        "serial_number": app_configuration["inverter"].get("serial", None),
        "disable_custom_registers": app_configuration["inverter"].get(
            "disable_custom_registers", False
        ),
    }
    return config_inverter


def print_welcome_message(app_args, inverter_configuration):
    logging.info(f"##################################################################")
    logging.info(f"Starting SunGatherEvo {__version__}")
    logging.debug(f"Options (defaults if not modified by arguments): {app_args}")
    logging.debug(f"Inverter Config Loaded: {inverter_configuration}")
    logging.info(f"##################################################################")


def check_config(app_config, inverter_config):
    if not inverter_config["log_file"] in [
        "OFF",
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
    ]:
        logging.warning(
            f"log_file: Valid options are: DEBUG, INFO, WARNING, ERROR and OFF"
        )

    if not inverter_config["connection"] in ["http", "sungrow", "modbus"]:
        logging.critical(
            f"Unknown connection type ´{inverter_config['connection']}`, "
            + "Valid options are ´http`, ´sungrow` or ´modbus`!"
        )
        sys.exit(1)


#######################################################################
# functions for loading register definitions and patching registers


def load_registers(app_configuration, registersfilename):
    try:
        registersfile = yaml.safe_load(open(registersfilename, encoding="utf-8"))
        logging.info(
            f"Loaded registers: {registersfilename}, file version: {registersfile.get('version','UNKNOWN')}"
        )
    except Exception as err:
        logging.error(f"Failed: Loading registers: {registersfilename}  {err}")
        sys.exit(f"Failed: Loading registers: {registersfilename} {err}")

    # Full validation of the registers yaml syntax is rather scope of
    # implementing a schema.

    # These checks are to allow empty lists of read and hold sections within
    # sections registers and scan. If these are empty in the yaml there will
    # not be an empty list. This is substituted here.

    if registersfile["registers"][0].get("read") is None:
        registersfile["registers"][0]["read"] = []
    if registersfile["registers"][1].get("hold") is None:
        registersfile["registers"][1]["hold"] = []
    if registersfile["scan"][0].get("read") is None:
        registersfile["scan"][0]["read"] = []
    if registersfile["scan"][1].get("hold") is None:
        registersfile["scan"][1]["hold"] = []

    patch_registers(app_configuration, registersfile)
    print_register_list(registersfile)

    return registersfile


def patch_registers(app_configuration, register_configuration):
    # Update the register_configuration with modifications defined in the config file.
    patches = app_configuration["inverter"].get("register_patches", None)
    if patches is None:
        # section register_patches does not exist or does not have entries.
        return
    logging.info("Applying patches to register definitions ...")
    allregs = [
        *register_configuration["registers"][0]["read"],
        *register_configuration["registers"][1]["hold"],
    ]

    for patch in patches:
        apply_single_patch(patch, allregs)

    for reg in allregs:
        if reg.get("type") == "read":
            register_configuration["registers"][0]["read"].append(reg)
        elif reg.get("type") == "hold":
            register_configuration["registers"][1]["hold"].append(reg)


def apply_single_patch(patch, allregs):
    # Apply one patch. A patch contains one or more attributes with
    # values to add or change in one or more registers.
    reg_name = patch.get("name")
    if reg_name is None:
        logging.error(
            f"Register patch doesn't contain ´name` attribute, ignoring entry: {patch}."
        )
        return
    for attribute_name in list(patch):
        if attribute_name == "name":
            # value of attribute ´name` is for matching the register,
            # it doesn't contain a value for patching.
            continue
        attribute_value = patch.get(attribute_name)
        patch_attribute(reg_name, attribute_name, attribute_value, allregs)


def check_patch_value(attribute_name, attribute_value):
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
            + f"Attributes ´level`, ´address`, ´length`, ´undate_frequency` "
            + f"must not be patched to anything but an Integer!"
        )
        return False
    if attribute_name in ["unit", "datatype", "change_name_to"] and not isinstance(
        attribute_value, str
    ):
        logging.error(
            f"Trying to patch {attribute_name} to value ´{attribute_value}` failed. "
            + f"Attributes ´unit`, ´datatype` must not be patched to anything but a String!"
        )
        return False
    if attribute_name in ["accuracy"] and not isinstance(attribute_value, float):
        logging.error(
            f"Trying to patch {attribute_name} to value ´{attribute_value}` failed. "
            + f"Attribute ´accuracy` must not be patched to anything but a float!"
        )
        return False
    return True


def patch_attribute(reg_name, attribute_name, attribute_value, allregs):
    # Patch one attribute in all registers which match reg_name.
    if not check_patch_value(attribute_name, attribute_value):
        return False
    try:
        p = re.compile(reg_name)
    except re.error:
        logging.error(
            f"String ´{reg_name}` is not a valid expression for the attribute ´name` in a register patch!"
        )
        return False

    pattern_did_match = False
    for reg in allregs:
        if p.fullmatch(reg.get("name")):
            pattern_did_match = True
            patch_register(reg, attribute_name, attribute_value)

    # If there was no match for an existing register, then this entry is
    # intended to create a new register!
    if not pattern_did_match:
        newreg = {}
        newreg["name"] = reg_name
        logging.info(f"Adding new register ´{reg_name}`.")
        patch_register(newreg, attribute_name, attribute_value)
        allregs.append(newreg)
        # This still needs to be added to the ´read` or ´hold` register lists!

    return True


def patch_register(reg, attribute_name, attribute_value):
    # Add or change one attribute (named attribute_name) to the value
    # attribute_value in one register (reg).

    # First check whether this entry is to rename an attribute:
    if attribute_name == "change_name_to":
        # switch attribute_name to "name" will have the register name changed:
        attribute_name = "name"

    if reg.get(attribute_name):
        if reg.get(attribute_name) == attribute_value:
            # No need for a change, the attribute is already set to attribute_value.
            logging.info(
                f"Patching register ´{reg.get('name')}`: attribute {attribute_name} "
                + f"was already set to {attribute_value} (not changed)."
            )
        else:
            # We will overwrite an existing value.
            logging.info(
                f"Patching register ´{reg.get('name')}`: {attribute_name} = {attribute_value} "
                + f"(previous value was {reg.get(attribute_name)})."
            )
    else:
        # The attribute will be added to this register.
        logging.info(
            f"Patching register ´{reg.get('name')}`: adding attribute {attribute_name} = {attribute_value}."
        )
    reg[attribute_name] = attribute_value


def print_register_list(register_configuration):
    print(
        f"+-------------------------------------------------------------------------------+"
    )
    print(
        f"| Register definitions after applying patches.                                  |"
    )
    print(
        f"| Note: The list is not filtered by supported models!                           |"
    )
    print(
        f"+--------------------------------------------+-------+------+-------+-------+---+"
    )
    print(
        "| {:<42} | {:^5} | {:<4} | {:<5} | {:<5} |{:^3}|".format(
            "register name", "unit", "type", "freq.", "addr", "lvl"
        )
    )
    print(
        f"+--------------------------------------------+-------+------+-------+-------+---+"
    )
    for reg in register_configuration["registers"][0]["read"]:
        print(
            "| {:<42} | {:^5} | {:<4} | {:>5} | {:>5} |{:^3}|".format(
                reg.get("name"),
                reg.get("unit", ""),
                "read",
                reg.get("update_frequency", ""),
                reg.get("address", "-----"),
                reg.get("level", "-"),
            )
        )
    for reg in register_configuration["registers"][1]["hold"]:
        print(
            "| {:<42} | {:^5} | {:<4} | {:>5} | {:>5} |{:^3}|".format(
                reg.get("name"),
                reg.get("unit", ""),
                "hold",
                reg.get("update_frequency", ""),
                reg.get("address", "-----"),
                reg.get("level", "-"),
            )
        )
    print(
        f"+--------------------------------------------+-------+------+-------+-------+---+"
    )


#######################################################################
# Set up the inverter.


def setup_inverter(inverter_configuration, register_configuration):
    inverter = SungrowClient(inverter_configuration)

    # Establish the first connection.  Note the client will return True if no
    # exception occurred in the library even if the connection could not be
    # established!  A return value of False indicates an exception occured
    # during an attempted connect in the library code.  This is sufficient
    # reason for sys.exit().

    if not inverter.connect():
        logging.critical(
            f"Connection to inverter failed: {inverter_configuration.get('host')}:{inverter_configuration.get('port')}"
        )
        sys.exit(1)

    inverter.configure_registers(register_configuration)
    inverter.close()

    inverter.print_register_list()

    return inverter


#######################################################################
# Functions for setting up exports


def setup_exports(app_configuration, inverter):
    # Note that exports may fail during configuration if data cannot be
    # read from the inverter!
    exports = []
    logging.info(f"Start loading exports ...")
    export_config_section = app_configuration.get("exports")
    for exportconfig in export_config_section:
        export_loaded = load_one_export(exportconfig, inverter)
        if export_loaded is not None:
            exports.append(export_loaded)
    # Fall back to console if nothing else was configured.
    if len(exports) == 0:
        logging.warning(
            f"No exports were configured or enabled. Falling back to console export."
        )
        export_loaded = load_one_export({"name": "console", "enabled": True}, inverter)
        if export_loaded is not None:
            exports.append(export_loaded)
        else:
            logging.critical(f"Fallback to export ´console` failed, exiting.")
            sys.exit(1)

    return exports


def load_one_export(export, inverter):
    logging.debug(f"Checking enablement of export ´{export.get('name')}` ...")
    if export.get("enabled", False):
        logging.debug(f"... Export ´{export.get('name')}` is enabled.")
        try:
            logging.info(f"Loading module ´exports/{export.get('name')}.py`.")
            export_loaded = importlib.import_module("exports." + export.get("name"))
            logging.debug(f"Module ´{export.get('name')}` imported successfully.")
        except Exception as err:
            logging.error(
                f"Failed loading export ´{export.get('name')}`: {err}"
                + f". Please make sure ´{export.get('name')}.py` exists in the exports folder."
            )
            return None
        try:
            export_loaded = getattr(export_loaded, "export_" + export.get("name"))()
            export_loaded.configure(export, inverter)
            logging.debug(f"Configured export ´{export.get('name')}`.")
        except Exception as err:
            logging.error(f"Failed configuring export ´{export.get('name')}`: {err}")
            return None
        return export_loaded
    else:
        logging.debug(f"... Export ´{export.get('name')}` is not enabled.")
        return None


#######################################################################
# Functions for polling the inverter.


def core_loop(inverter, exports, interval, runonce):
    while True:
        logging.info(f"Starting scrape ...")
        loop_start = time.perf_counter()

        inverter.checkConnection()

        scrape_and_export_once(inverter, exports)

        if runonce:
            logging.info(f"Option ´--runonce` was specified, exiting.")
            sys.exit(0)

        loop_end = time.perf_counter()
        process_time = round(loop_end - loop_start, 2)
        logging.debug(f"Processing Time: {process_time} secs")

        if interval - process_time <= 1:
            logging.warning(
                f"Processing took {process_time}, which is longer than interval {interval}. Please increase scan interval!"
            )
            time.sleep(process_time)
        else:
            logging.info(f"Next scrape in {int(interval - process_time)} secs.")
            time.sleep(interval - process_time)


def scrape_and_export_once(inverter, exports):
    # Scrape the inverter.
    success = False
    try:
        success = inverter.scrape()
    except Exception as e:
        logging.exception("Failed to scrape: %s", e)
        success = False

    # Export all scraped data, if scraping was successful, otherwise skip.
    if success:
        for export in exports:
            try:
                export.publish(inverter)
            except Exception as e:
                logging.exception("Failed to export: %s", e)
        inverter.close()
    else:
        inverter.disconnect()
        logging.warning(f"Data collection failed, skipped exporting data.")


#######################################################################
# Functions for setup of logging


def setup_log_levels_and_log_file(loglevel, logfolder, lvl_file, lvl_console):
    # Setup logging targets.levels, etc.  Note that ´log_file` does not point
    # to a file but contains the log level for a log file. Same with
    # ´log_console`.

    # Get a reference to the root logger:
    logger = logging.getLogger()

    # console logging
    if loglevel is not None:
        # loglevel was provided as a commandline argument
        logger.handlers[0].setLevel(loglevel)
    else:
        # use log level provided in config file
        logger.handlers[0].setLevel(lvl_console)
    logging.debug(
        f"Logging to console with level {logging.getLevelName(logger.handlers[0].level)}"
    )

    # file logging
    if not lvl_file == "OFF":
        logfile = logfolder + "SunGather.log"
        try:
            fh = logging.handlers.RotatingFileHandler(
                logfile, mode="w", encoding="utf-8", maxBytes=10485760, backupCount=10
            )  # Log 10mb files, 10 x files = 100mb
        except IOError as ioe:
            logging.error(
                f"Error setting up log file. "
                + f"Logging to file could not be enabled. "
                + f"The original error was: {ioe}"
            )
        else:
            fh.formatter = logger.handlers[0].formatter
            fh.setLevel(lvl_file)
            logger.addHandler(fh)
            logging.debug(f"Logging to file with level {lvl_file}")


#######################################################################
# main ...

logging.basicConfig(
    # Format log messages as for example ´2024-02-11 05:57:40 INFO     Loaded config: config.yaml`
    format="%(asctime)s %(levelname)-8s %(message)s",
    # By default and until changed by config and / or command line arguments set level to DEBUG:
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
    # log to stdout (by default python logging logs to stderr):
    stream=sys.stdout,
)


if __name__ == "__main__":
    main()

sys.exit()
