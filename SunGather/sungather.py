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
    # These values are available to be changed by commandline arguments:
    app_args = {"configfilename": 'config.yaml', "registersfilename": 'registers-sungrow.yaml', "logfolder": 'logs/', "loglevel": None, "runonce": False, "dump-regs": False}
    read_arguments_from_commandline(app_args)

    app_configuration = load_config_file(app_args['configfilename'])
    inverter_configuration = get_inverter_config(app_configuration)

    # Note that ´log_file` does not point to a file but contains the log level for a log file. Same with ´log_console`.
    setup_log_levels_and_log_file(app_args['loglevel'], app_args['logfolder'], inverter_configuration ['log_file'], inverter_configuration['log_console'])

    # After this point log message are also written into the logging file - if a log file is configured.
    logging.info(f"######################################################################################")
    logging.info(f'Starting SunGatherEvo {__version__}')
    logging.info(f"Options after reading commandline (defaults if not modified by arguments): {app_args}")
    logging.info(f'Inverter Config Loaded: {inverter_configuration}')    
    logging.info(f"######################################################################################")

    # Check config for obvious errors, do some corrections, exit on fatal errors.
    check_config(app_configuration, inverter_configuration)

    # Load the register_configuration and update registers according to configuration in the config file.
    register_configuration = load_registers(app_args['registersfilename']) 
    update_register_configuration_with_frequencies(app_configuration, register_configuration)

    print(f"+--------------------------------------------+-------+------+-------+-------+---+")
    print("| {:<42} | {:^5} | {:<4} | {:<5} | {:<5} |{:^3}|".format('register name', 'unit', 'type', 'freq.', 'addr', 'lvl'))
    print(f"+--------------------------------------------+-------+------+-------+-------+---+")
    for reg in register_configuration['registers'][0]['read']:
        print("| {:<42} | {:^5} | {:<4} | {:>5} | {:>5} |{:^3}|".format(reg.get("name"), reg.get("unit", ""), "read", reg.get("update_frequency", ""), reg.get("address","-----"), reg.get("level")))
    for reg in register_configuration['registers'][1]["hold"]:
        print("| {:<42} | {:^5} | {:<4} | {:>5} | {:>5} |{:^3}|".format(reg.get("name"), reg.get("unit", ""), "hold", reg.get("update_frequency", ""), reg.get("address","-----"), reg.get("level")))
    print(f"+--------------------------------------------+-------+------+-------+-------+---+")

    # Setup the inverter from the configuration and establish a first connection.
    inverter = setup_inverter(inverter_configuration, register_configuration)
    if app_args['dump-regs']:
        inverter.print_register_list()
    
    # Setup the exports from definitions in the the configuration file.
    exports = setup_exports(app_configuration, inverter)

    # Start the polling loop. If the ´runonce` parameter is set this will exit after a first iteration thus ending the program.
    core_loop(inverter, exports, inverter_configuration.get('scan_interval'), app_args['runonce'])


def read_arguments_from_commandline(app_args):
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hc:r:l:v:", ["runonce", "help", "dump-regs"])
    except getopt.GetoptError:
        logging.error(f'Error parsing command line! Run with option ´-h` to show usage information.')
        sys.exit(2)

    if opts and len(opts) == 0:
        logging.debug(f'No options passed via command line')
        return

    for opt, arg in opts:
        if opt == '-h' or opt == '--help':
            print_synopsis()
            sys.exit()
        elif opt == '--dump-regs':
            app_args['dump-regs'] = True
        elif opt == '-c':
            app_args['configfilename'] = arg 
        elif opt == '-r':
            app_args['registersfilename'] = arg 
        elif opt == '-l':
            app_args['logfolder'] = arg 
        elif opt  == '-v':
            if arg.isnumeric() and int(arg) >= 0 and int(arg) <= 50:
                app_args['loglevel'] = int(arg) 
            else:
                # Note: The default of 30 only applies, if the log level has not been set in the config file.
                logging.error(f"Valid verbose options: 10 = Debug, 20 = Info, 30 = Warning (default), 40 = Error")
                sys.exit(2) 
        elif opt == '--runonce':
            app_args['runonce'] = True


def print_synopsis():
    print(f'\nSunGatherEvo {__version__}')
    print(f'usage: python3 sungather.py [options]')
    print(f'\nCommandline arguments override any config file settings.')
    print(f'Options and arguments:')
    print(f'-c config.yaml             : Specify config file.')
    print(f'-r registers-file.yaml     : Specify registers file.')
    print(f'-l logs/                   : Specify folder to store logs.')
    print(f'-v 30                      : Logging Level, 10 = Debug, 20 = Info, 30 = Warning (default), 40 = Error')
    print(f'--runonce                  : Run once then exit.')
    print(f'--dump-regs                : Dump register list after final configuration.')
    print(f'-h                         : print this help message and exit.')
    print(f'\nExample:')
    print(f'python3 sungather.py -c /full/path/config.yaml\n')


def  load_config_file(configfilename):
    try:
        configfile = yaml.safe_load(open(configfilename, encoding="utf-8"))
        logging.debug(f"Loaded config: {configfilename}")
    except Exception as err:
        logging.exception(f"Failed loading config: {configfilename} \n\t\t\t     {err}")
        sys.exit(1)
    if not configfile.get('inverter'):
        logging.critical(f"Failed loading config, missing Inverter settings")
        sys.exit(1)

    return configfile 


def load_registers(registersfilename):
    try:
        registersfile = yaml.safe_load(open(registersfilename, encoding="utf-8"))
        logging.info(f"Loaded registers: {registersfilename}, file version: {registersfile.get('version','UNKNOWN')}")
    except Exception as err:
        logging.error(f"Failed: Loading registers: {registersfilename}  {err}")
        sys.exit(f"Failed: Loading registers: {registersfilename} {err}")
    return registersfile 


def get_inverter_config(app_configuration):
    config_inverter = {
        "host": app_configuration['inverter'].get('host',"localhost"),
        "port": app_configuration['inverter'].get('port',502),
        "timeout": app_configuration['inverter'].get('timeout',10),
        "retries": app_configuration['inverter'].get('retries',3),
        "slave": app_configuration['inverter'].get('slave',0x01),
        "scan_interval": app_configuration['inverter'].get('scan_interval',30),
        "connection": app_configuration['inverter'].get('connection',"modbus"),
        "model": app_configuration['inverter'].get('model',None),
        "smart_meter": app_configuration['inverter'].get('smart_meter',False),
        "use_local_time": app_configuration['inverter'].get('use_local_time',False),
        "log_console": app_configuration['inverter'].get('log_console','WARNING'),
        "log_file": app_configuration['inverter'].get('log_file','OFF'),
        "level": app_configuration['inverter'].get('level',1),
        "dyna_scan": app_configuration['inverter'].get('dyna_scan',False),
        "serial_number": app_configuration['inverter'].get('serial', None),
        "disable_custom_registers": app_configuration['inverter'].get('disable_custom_registers',False)
    }
    
    return config_inverter 


def check_config(app_configuration, inverter_configuration):
    if not inverter_configuration.get('host'):
        logging.critical(f"´host` option in config is required!")
        sys.exit(1)

    if not inverter_configuration['log_file'] in ["OFF", "DEBUG", "INFO", "WARNING", "ERROR"]:
        logging.warning(f"log_file: Valid options are: DEBUG, INFO, WARNING, ERROR and OFF")

    if not inverter_configuration['connection'] in ["http", "sungrow", "modbus"]:
        logging.critical(f"Unknown connection type ´{inverter_configuration['connection']}`, Valid options are ´http`, ´sungrow` or ´modbus`!")
        sys.exit(1)

    if not app_configuration.get('exports') or len(app_configuration.get('exports')) == 0:
        logging.critical(f"Failed loading config, missing exports section or exports section empty.")
        sys.exit(1)


def update_register_configuration_with_frequencies(app_configuration, register_configuration):
    # Update the register_configuration with register specific update_frequency defined in the config file.
    allregs = [*register_configuration['registers'][0]['read'], *register_configuration['registers'][1]["hold"]]
    for ruf in app_configuration['inverter'].get('register_update_frequencies',[]):
        reg_name = ruf.get("name")
        if reg_name is None:
            logging.error(f"Configuration of update frequency failed, key ´name` is missing in entry: ´{ruf}`. Check configuration section ´register_update_frequencies`!")
            continue
        uf = ruf.get("update_frequency")
        if uf is None:
            logging.error(f"Configuration of update frequency failed, key ´update_frequency` is missing for entry ´{reg_name}`. Check configuration section ´register_update_frequencies`!")
            continue
        try:
            i = int(uf)
        except ValueError:
            logging.error(f"Configuration of update frequency failed, value ´{uf}` of ´update_frequency` in entry ´{reg_name}` is not an integer. Check configuration section ´register_update_frequencies`!")
            continue
        p = re.compile(reg_name)
        for reg in allregs:
            if not reg.get("update_frequency") and p.fullmatch(reg.get('name')):
                reg['update_frequency'] = uf


def setup_inverter(inverter_configuration, register_configuration):
    inverter = SungrowClient(inverter_configuration)

    # Establish the first connection.
    # A return value of False indicates an exception occured during an attempted connect in the library code.
    # This is sufficient reason for sys.exit().
    # The client will return True if no exception occurred in the library even if the connection could not be established!
    if not inverter.connect():
        logging.critical(f"Connection to inverter failed: {inverter_configuration.get('host')}:{inverter_configuration.get('port')}")
        sys.exit(1)       

    inverter.configure_registers(register_configuration)
    inverter.close()

    return inverter


def setup_exports(app_configuration, inverter):
    # Note that exports may fail during configuration if data cannot be read from the inverter!
    exports = []
    logging.info(f"Loading exports")
    for exportconfig in app_configuration.get('exports'):
        export_loaded = load_one_export(exportconfig, inverter)
        if export_loaded is not None: 
            exports.append(export_loaded)

    if len(exports) == 0:
        logging.critical(f'No exports configured! Make sure at least one export is enabled in the configuration exports section! Exiting ... ')
        sys.exit(1)

    return exports


def load_one_export(export, inverter):
    logging.debug(f"Checking enablement of export ´{export.get('name')}` ...")
    if export.get('enabled', False):
        logging.debug(f"... Export ´{export.get('name')}` is enabled.")
        try:
            logging.info(f"Loading module ´exports/{export.get('name')}.py`.")
            export_loaded = importlib.import_module("exports." + export.get('name'))
            logging.debug(f"Module ´{export.get('name')}` imported successfully.")
        except Exception as err:
            logging.error(f"Failed loading export ´{export.get('name')}`: {err}" +
                        f". Please make sure ´{export.get('name')}.py` exists in the exports folder.")
            return None
        try:
            export_loaded = getattr(export_loaded, "export_" + export.get('name'))()
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
        loop_start = time.perf_counter()

        # reestablish connection if required.
        inverter.checkConnection()

        scrape_and_export_once(inverter, exports)

        if runonce:
            logging.info(f"Option ´--runonce` was specified, exiting.")
            sys.exit(0)
        
        loop_end = time.perf_counter()
        process_time = round(loop_end - loop_start, 2)
        logging.debug(f'Processing Time: {process_time} secs')

        # Sleep until the next scan
        if interval - process_time <= 1:
            logging.warning(f"Processing took {process_time}, which is longer than interval {interval}. Please increase scan interval!")
            time.sleep(process_time)
        else:
            logging.info(f'Next scrape in {int(interval - process_time)} secs.')
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
    if(success):
        for export in exports:
            try:
                export.publish(inverter)
            except Exception as e:
                logging.exception("Failed to export: %s", e)
        inverter.close()
    else:
        inverter.disconnect()
        logging.warning(f"Data collection failed, skipped exporting data.")


def setup_log_levels_and_log_file(loglevel, logfolder, lvl_file, lvl_console):
    # Get a reference to the root logger:
    logger = logging.getLogger()

    # console logging
    if loglevel is not None:
        # loglevel was provided as a commandline argument
        logger.handlers[0].setLevel(loglevel)
    else:
        # use log level provided in config file
        logger.handlers[0].setLevel(lvl_console)
    logging.debug(f"Logging to console with level {logging.getLevelName(logger.handlers[0].level)}")

    # file logging
    if not lvl_file == "OFF":
        if not os.path.exists(logfolder):
            os.makedirs(logfolder)
        logfile = logfolder + "SunGather.log"
        fh = logging.handlers.RotatingFileHandler(logfile, mode='w', encoding='utf-8', maxBytes=10485760, backupCount=10) # Log 10mb files, 10 x files = 100mb
        fh.formatter = logger.handlers[0].formatter
        fh.setLevel(lvl_file)
        logger.addHandler(fh)
        logging.debug(f"Logging to file with level {lvl_file}")
   

logging.basicConfig(
    # Format log messages as for example ´2024-02-11 05:57:40 INFO     Loaded config: config.yaml`
    format='%(asctime)s %(levelname)-8s %(message)s',
    # By default and until changed by config and / or command line arguments set level to DEBUG:
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S',
    # log to stdout (by default python logging logs to stderr):
    stream=sys.stdout)


if __name__== "__main__":
    main()

sys.exit()
