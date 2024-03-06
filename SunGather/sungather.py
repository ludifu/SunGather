#!/usr/bin/python3

from SungrowClient import SungrowClient
from FieldConfigurator import FieldConfigurator
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

    patches = app_config["inverter"].get("register_patches", None)
    fc = FieldConfigurator(app_args["registersfilename"], register_patch_config=patches)
    register_config = fc.get_register_config()

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
    print(f"-v 30                   : Logging Level")
    print(f"                          10 = Debug, 20 = Info, 30 = Warning, 40 = Error")
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
        "customfields": app_configuration["inverter"].get("customfields", []),
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


def setup_inverter(inverter_config, register_configuration):

    inverter = SungrowClient(inverter_config)

    # Establish the first connection.  Note the client will return True if no
    # exception occurred in the library even if the connection could not be
    # established!  A return value of False indicates an exception occured
    # during an attempted connect in the library code.  This is sufficient
    # reason for sys.exit().

    if not inverter.connect():
        logging.critical(
            f"Connection to inverter failed: {inverter_config.get('host')}:{inverter_config.get('port')}"
        )
        sys.exit(1)

    inverter.configure_registers(register_configuration)
    inverter.close()

    inverter.print_register_list()

    return inverter


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
    format="%(asctime)s %(levelname)-8s %(module)-14.14s %(message)s",
    # By default and until changed by config and / or command line arguments set level to DEBUG:
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
    # log to stdout (by default python logging logs to stderr):
    stream=sys.stdout,
)


if __name__ == "__main__":
    main()

sys.exit()
