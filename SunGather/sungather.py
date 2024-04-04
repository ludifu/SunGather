#!/usr/bin/python3

from SungrowClient import SungrowClient
from SungrowClient import SungrowClientCore
from FieldConfigurator import FieldConfigurator
from JSONSchemaValidator import JSONSchemaValidator
from version import __version__

import importlib
import logging
import logging.handlers
import sys
import getopt
import yaml
import time


def main():
    app_args = read_arguments_from_commandline()
    # Use log level from command line if specified:
    setup_console_logging(app_args["loglevel"])

    app_config = load_config_file(app_args["configfilename"])
    inverter_config = get_inverter_config(app_config)

    if app_args["loglevel"] is None:
        # fall back to log level from config file
        setup_console_logging(inverter_config["log_console"])
    setup_file_logging(app_args["logfolder"], inverter_config["log_file"])

    print_welcome_message(app_args, inverter_config)

    inverter = setup_inverter(inverter_config, app_args["registersfilename"])

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
            "Error parsing command line! Run with option ´-h` to show usage information."
        )
        sys.exit(2)

    if opts and len(opts) == 0:
        logging.debug("No options passed via command line")
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
                    "Valid verbose options: 10 = Debug, 20 = Info, 30 = Warning (default), 40 = Error"
                )
                sys.exit(2)
        elif opt == "--runonce":
            app_args["runonce"] = True

    return app_args


def print_synopsis():
    print(f"\nSunGatherEvo {__version__}")
    print("usage: python3 sungather.py [options]")
    print("\nCommandline arguments override any config file settings.")
    print("Options and arguments:")
    print("-c config.yaml          : Specify config file.")
    print("-r registers-file.yaml  : Specify registers file.")
    print("-l logs/                : Specify folder to store logs.")
    print("-v 30                   : Logging Level")
    print("                          10 = Debug, 20 = Info, 30 = Warning, 40 = Error")
    print("--runonce               : Run once then exit.")
    print("-h                      : print this help message and exit.")
    print("\nExample:")
    print("python3 sungather.py -c /full/path/config.yaml\n")


def load_config_file(configfilename):
    try:
        configfile = yaml.safe_load(open(configfilename, encoding="utf-8"))
        logging.debug(f"Loaded config: {configfilename}")
    except Exception as err:
        logging.exception(f"Failed loading config: {configfilename} \n\t\t\t     {err}")
        sys.exit(1)

    v = JSONSchemaValidator()
    logging.debug(f"Performing schema validation of config file ´{configfilename}` ...")
    if v.validate_config_file(configfile):
        logging.debug(f"... config file ´{configfilename}` successfully validated.")
    else:
        logging.critical(f"... Validation of config file ´{configfilename}` failed!")
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
        "disable_legacy_custom_registers": app_configuration["inverter"].get(
            "disable_legacy_custom_registers", False
        ),
        "customfields": app_configuration["inverter"].get("customfields", []),
        "register_patches": app_configuration["inverter"].get("register_patches", []),
    }
    return config_inverter


def print_welcome_message(app_args, inverter_configuration):
    logging.info("##################################################################")
    logging.info(f"Starting SunGatherEvo {__version__}")
    logging.debug(f"Options (defaults if not modified by arguments): {app_args}")
    logging.debug(f"Inverter Config Loaded: {inverter_configuration}")
    logging.info("##################################################################")


def setup_inverter(inverter_config, register_config_filename):
    patches = inverter_config.get("register_patches", None)
    fc = FieldConfigurator(register_config_filename, register_patch_config=patches)
    register_configuration = fc.get_register_config()

    if inverter_config.get("disable_legacy_custom_registers"):
        inverter = SungrowClientCore(inverter_config)
    else:
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
    logging.info("Start loading exports ...")
    export_config_section = app_configuration.get("exports")
    for exportconfig in export_config_section:
        export_loaded = load_one_export(exportconfig, inverter)
        if export_loaded is not None:
            exports.append(export_loaded)
    # Fall back to console if nothing else was configured.
    if len(exports) == 0:
        logging.warning(
            "No exports were configured or enabled. Falling back to console export."
        )
        export_loaded = load_one_export({"name": "console", "enabled": True}, inverter)
        if export_loaded is not None:
            exports.append(export_loaded)
        else:
            logging.critical("Fallback to export ´console` failed, exiting.")
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
        logging.info("Starting scrape ...")
        loop_start = time.perf_counter()

        inverter.checkConnection()

        scrape_and_export_once(inverter, exports)

        if runonce:
            logging.info("Option ´--runonce` was specified, exiting.")
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
        logging.warning("Data collection failed, skipped exporting data.")


def setup_console_logging(loglevel):
    # Get a reference to the root logger:
    logger = logging.getLogger()
    if loglevel is not None:
        logger.handlers[0].setLevel(loglevel)


def setup_file_logging(logfolder, loglevel):
    # Get a reference to the root logger:
    logger = logging.getLogger()
    if not loglevel == "OFF":
        logfile = logfolder + "SunGather.log"
        try:
            fh = logging.handlers.RotatingFileHandler(
                logfile, mode="w", encoding="utf-8", maxBytes=10485760, backupCount=10
            )  # Log 10mb files, 10 x files = 100mb
        except IOError as ioe:
            logging.error(
                f"Error setting up log file. Logging to file could not be enabled. The original error was: {ioe}"
            )
        else:
            fh.formatter = logger.handlers[0].formatter
            fh.setLevel(loglevel)
            logger.addHandler(fh)
            logging.debug(f"Logging to file with level {loglevel}")


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
