#!/usr/bin/python3

from SungrowModbusTcpClient import SungrowModbusTcpClient
from SungrowModbusWebClient import SungrowModbusWebClient
from pymodbus.client.sync import ModbusTcpClient

from datetime import datetime

import logging
import logging.handlers
import time

class SungrowClient():
    def __init__(self, config_inverter):

        self.client_config = {
            "host":     config_inverter.get('host'),
            "port":     config_inverter.get('port'),
            "timeout":  config_inverter.get('timeout'),
            "retries":  config_inverter.get('retries'),
            "RetryOnEmpty": False,
        }
        self.inverter_config = {
            "model":                     config_inverter.get('model'),
            "serial_number":             config_inverter.get('serial_number'),
            "level":                     config_inverter.get('level'),
            "scan_interval":             config_inverter.get('scan_interval'),
            "use_local_time":            config_inverter.get('use_local_time'),
            "smart_meter":               config_inverter.get('smart_meter'),
            "connection":                config_inverter.get('connection'),
            "slave":                     config_inverter.get('slave'),
            "dyna_scan":                 config_inverter.get('dyna_scan'),
            "disable_custom_registers":  config_inverter.get('disable_custom_registers'),
            "start_time":       ""
        }
        self.client = None
        
        self.registers = [[]]
        self.registers.pop() # Remove null value from list
        if not config_inverter.get('disable_custom_registers'):
            self.registers_custom = [   {'name': 'run_state', 'address': 'vr001'},
                                        {'name': 'timestamp', 'address': 'vr002'},
                                        {'name': 'last_reset', 'address': 'vr003'},
                                        {'name': 'export_to_grid', 'unit': 'W', 'address': 'vr004'}, 
                                        {'name': 'import_from_grid', 'unit': 'W', 'address': 'vr005'}, 
                                        {'name': 'daily_export_to_grid', 'unit': 'kWh', 'address': 'vr006'}, 
                                        {'name': 'daily_import_from_grid', 'unit': 'kWh', 'address': 'vr007'}
                                    ]
        else:
            self.registers_custom = []

        self.register_ranges = [[]]
        self.register_ranges.pop() # Remove null value from list

        self.latest_scrape = {}

    def connect(self):
        logging.debug("Connecting to the inverter ...")
        if self.client:
            try:
                self.client.connect()
            except:
                return False
            return True

        if self.inverter_config['connection'] == "http":
            self.client_config['port'] = '8082'
            self.client = SungrowModbusWebClient.SungrowModbusWebClient(**self.client_config)
        elif self.inverter_config['connection'] == "sungrow":
            self.client = SungrowModbusTcpClient.SungrowModbusTcpClient(**self.client_config)
        elif self.inverter_config['connection'] == "modbus":
            self.client = ModbusTcpClient(**self.client_config)
        else:
            logging.warning(f"Inverter: Unknown connection type {self.inverter_config['connection']}, Valid options are http, sungrow or modbus")
            return False
        logging.info("Client created for connection to inverter: " + str(self.client))

        try:
            self.client.connect()
        except:
            return False

        time.sleep(3)       # Wait 3 seconds, fixes timing issues
        return True

    def checkConnection(self):
        logging.debug("Checking whether connection to inverter is still established ...")
        if self.client:
            if self.client.is_socket_open():
                logging.debug("... Modbus session is still connected.")
                return True
            else:
                logging.debug(f'... Modbus session disconnected, connecting new session.')
                return self.connect()
        else:
            logging.debug(f'... Client is not connected, attempting to reconnect.')
            return self.connect()

    def close(self):
        if self.inverter_config['connection'] == "http":
            return
        logging.debug("Closing Session: " + str(self.client))
        try:
            self.client.close()
        except:
            pass

    def disconnect(self):
        logging.debug("Disconnecting: " + str(self.client))
        try:
            self.client.close()
        except:
            pass
        self.client = None


    def register_length(self, reg):
        # return the number of 16 bit registers that the register ´reg` requires.
        reg_datatype = reg.get("datatype")
        if reg_datatype == "S32" or reg_datatype == "U32":
            reg_len = 2
        elif reg_datatype == "UTF-8":
            # If length is defined as attribute of the register, we're fine.
            # If not use a default of 15. Rationale: As of the Sungrow specification (Hybrid) 1.0.23 the maximum length of any UTF-8 register is 15.
            # In the worst case we read 5 registers more than required, but this should not fail.
            reg_len = reg.get("length", 15)
        else:
            reg_len = 1
        return reg_len


    def load_single_register(self, reg_name, reg_type, registersfile):
        # load a single register from the inverter and return the register value.
        if reg_type == 'read':
            reg_list = registersfile['registers'][0]['read']
        else:
            reg_list = registersfile['registers'][1]['hold']
        for register in reg_list:
            if register.get('name') == reg_name:
                reg_address = register['address']
                reg_len = self.register_length(register)
                register['type'] = reg_type
                self.registers.append(register)
                break
        if reg_address is None:
            logging.warning(f"Failed loading register ´{reg_name}` of type ´{reg_type}`. Register is not defined or address is missing in the register definition!")
            return None

        success = self.load_registers(reg_type, reg_address -1, reg_len) # Needs to be address -1
        self.registers.pop()
        if not success:
            logging.warning(f"Failed loading register ´{reg_name}` of type ´{reg_type}`!")
            return None
        return self.latest_scrape.get(reg_name)


    def detect_model(self,registersfile):
        result = self.load_single_register("device_type_code", 'read', registersfile)
        if not result:
            logging.warning(f'Model detection failed, please set model in config.py!')
        elif isinstance(result, int):
            logging.warning(f"Unknown model type code detected: ´{result}`.")
        else:
            self.inverter_config['model'] = result
            logging.info(f"Model detected: ´{result}`.")


    def check_model(self, registersfile):
        # Check if the inverter model is configured, otherwise try to read the model code from the inverter.
        if self.inverter_config.get('model'):
            logging.info(f"Model configured: ´{self.inverter_config.get('model')}`.")
        else:
            logging.info(f"Model not configured, trying to detect model ...")
            self.detect_model(registersfile)


    def detect_serial(self,registersfile):
        result = self.load_single_register("serial_number", 'read', registersfile)
        if not result:
            logging.warning(f'Serial detection failed, please set serial number in config.py!')
        elif isinstance(result, int):
            logging.warning(f"Unknown result for serial number detected: ´{result}`.")
        else:
            self.inverter_config['serial_numbe'] = result
            logging.info(f"Serial number detected: ´{result}`.")


    def check_serial_number(self, registersfile):
        # Check whether serial number is configured, otherwise load from the inverter.
        if self.inverter_config.get('serial_number', None) is not None:
            logging.info(f"Serial number configured: ´{self.inverter_config.get('serial_number')}`.")
        else:
            logging.info(f"Serial number not configured, trying to detect serial number ...")
            self.detect_serial(registersfile)


    def build_register_list(self, registersfile):
        # Load register list based on name and value after checking model
        for register in registersfile['registers'][0]['read']:
            self.append_register_if_available_for_reading(register, 'read')
        for register in registersfile['registers'][1]['hold']:
            self.append_register_if_available_for_reading(register, 'hold')


    def append_register_if_available_for_reading(self, register, reg_type):
        # register will be appended only if it is available for reading in this installation.
        if register.get('level',3) <= self.inverter_config.get('level') or self.inverter_config.get('level') == 3:
            register['type'] = reg_type
            register.pop('level')
            if register.get('smart_meter') and self.inverter_config.get('smart_meter'):
                # read register, if it is provided by a smart meter and such a device is available according to the config.
                register.pop('models')
                self.registers.append(register)
            elif register.get('models') and not self.inverter_config.get('level') == 3:
                # read register, if it is provided by specific inverter models only and our inverter is among the supported models:
                # whether the register is available for this model at all is only checked, if level is < 3!
                for supported_model in register.get('models'):
                    if supported_model == self.inverter_config.get('model'):
                        register.pop('models')
                        self.registers.append(register)
            else:
                # read any remaining registers: even if the register is not configured to be available for this model.
                self.registers.append(register)


    def build_range_list(self, registersfile):
        # Build a list of address ranges to read from the inverter. Only address ranges are of interest which contain
        # at least one register we are interested in.
        for register_range in registersfile['scan'][0]['read']:
            self.append_address_range_if_required(register_range, 'read')
        for register_range in registersfile['scan'][1]['hold']:
            self.append_address_range_if_required(register_range, 'hold')
        # logging.debug(f"The following address ranges will be scraped: {self.register_ranges}.")


    def append_address_range_if_required(self, reg_range, reg_type):
        # Search for registers which are located in this address range, if any are found append the address range.
        range_start = reg_range.get("start")
        range_end = range_start  + reg_range.get("range")
        for register in self.registers:
            if register.get("type") == reg_type:
                reg_address = register.get('address')
                if reg_address >= range_start and reg_address <= range_end:
                    reg_range['type'] = reg_type
                    self.register_ranges.append(reg_range)
                    return


    def configure_registers(self,registersfile):
        # Determine the inverter model from config or by scraping:
        self.check_model(registersfile)

        # Determine the inverter's serial number from config or by scraping:
        self.check_serial_number(registersfile)

        # Filter the registers into a list available for scraping in this installation:
        self.build_register_list(registersfile)

        # Filter the list of address areas to read from the inverter to those which contain available registers:
        self.build_range_list(registersfile)
        return True


    # read and return an address range beginning with start and with count registers from the inverter.
    def read_input_registers(self, register_type, start, count):
        try:
            logging.debug(f'read_input_registers: {register_type}, {start}:{count}')
            if register_type == "read":
                rr = self.client.read_input_registers(start,count=count, unit=self.inverter_config['slave'])
            elif register_type == "hold":
                rr = self.client.read_holding_registers(start,count=count, unit=self.inverter_config['slave'])
            else:
                raise RuntimeError(f"Unsupported register type: {type}")
        except Exception as err:
            logging.warning(f"No data returned for type ´{register_type}`, start {start}, count {count}")
            logging.debug(f"(´{str(err)}`)")
            return None

        if rr.isError():
            logging.warning(f"Modbus connection failed!")
            logging.debug(f"{rr}")
            return  None

        if not hasattr(rr, 'registers'):
            logging.warning("No registers returned when reading from inverter!")
            return None

        if len(rr.registers) != count:
            logging.warning(f"Mismatched number of registers read {len(rr.registers)} != {count}")
            return None

        return rr


    def interpret_value_for_register(self, rr, num, register):
        # Convert the values delivered by the inverter into a format suitable for further work.

        register_value = rr.registers[num]

        # Convert unsigned to signed
        # If xFF / xFFFF then change to 0, looks better when logging / graphing
        if register.get('datatype') == "U16":
            if register_value == 0xFFFF:
                register_value = 0
            if register.get('mask'):
                # Filter the value through the mask.
                register_value = 1 if register_value & register.get('mask') != 0 else 0
        elif register.get('datatype') == "S16":
            if register_value == 0xFFFF or register_value == 0x7FFF:
                register_value = 0
            if register_value >= 32767:  # Anything greater than 32767 is a negative for 16bit
                register_value = (register_value - 65536)
        elif register.get('datatype') == "U32":
            u32_value = rr.registers[num+1]
            if register_value == 0xFFFF and u32_value == 0xFFFF:
                register_value = 0
            else:
                register_value = (register_value + u32_value * 0x10000)
        elif register.get('datatype') == "S32":
            u32_value = rr.registers[num+1]
            if register_value == 0xFFFF and (u32_value == 0xFFFF or u32_value == 0x7FFF):
                register_value = 0
            elif u32_value >= 32767:  # Anything greater than 32767 is a negative
                register_value = (register_value + u32_value * 0x10000 - 0xffffffff -1)
            else:
                register_value = register_value + u32_value * 0x10000
        elif register.get('datatype') == "UTF-8": # This seems to be Serial only
            utf_value = register_value.to_bytes(2, 'big')
            # Use attribute ´length` if configured for the UTF-8 attribute, otherwise assume 10 registers (20 characters), rr.registers[num] .. rr.registers[num+9].
            # According to an issue registered with bohdan-s/SunGather the serial is actually up to 11 characters, not 10.
            # https://github.com/bohdan-s/SunGather/issues/118
            # Note:
            # (a) Any UTF-8 attribute LONGER than 10 registers would be truncated, unless it has its length correctly configured as an attribute.
            # (b) Any UTF-8 attribute SHORTER than 10 registers will probably either contain garbage after its regular length or the reading
            #     may fail altogether if reading from rr exceeds the length of rr ...
            # (c) Version V1.0.23 of the Sungrow Specification ´Communication Protocol of Residential Hybrid Inverter` contains 3 UTF-8 registers
            #     with 10 (serial_number) and 15 (arm_software-version and dsp_software_version) characters.
            for x in range(1, register.get('length', 10-1)):
                utf_value += rr.registers[num+x].to_bytes(2, 'big')
            register_value = utf_value.decode()

        # Some registers contain one out of a range of specific values (effectivly an enumeration). These values are often simply
        # coded as hex values. For example in the register ´device_type_code` an inverter model ´SH8.0RT` is represented by the
        # value 0xE02. Such code are replaced by their corresponding values:
        if register.get('datarange'):
            match = False
            for value in register.get('datarange'):
                if value['response'] == rr.registers[num] or value['response'] == register_value:
                    register_value = value['value']
                    match = True
            if not match:
                default = register.get('default')
                logging.debug(f"No matching value for {register_value} in datarange of {register_name}, using default {default}.")
                register_value = default

        # The inverter does not have floating or fixed point numbers available. To deliver values with decimals these are multiplied
        # by factors of 10. For example a value of 50.4 degrees in the register ´internal_temperature` is represented as a value of 504.
        # Such values are converted to correct floating point values.
        if register.get('accuracy'):
            register_value = round(register_value * register.get('accuracy'), 2)

        return register_value


    def load_registers(self, register_type, start, count=100):
        logging.info(f"Start reading a single range of data, type ´{register_type}`, start {start}, count {count}.")

        # first read the data area containing the registers from the inverter.
        rr = self.read_input_registers(register_type, start, count)
        if rr is None:
            return False

        # for each address in the range check which registers they contain and extract the data for the registers accordingly.
        for num in range(0, count):
            run = int(start) + num + 1

            for register in self.registers:
                # skip register, if it is not yet time to read it:
                if register.get("update_frequency") and register.get("last_update") and (datetime.now() - register["last_update"]).total_seconds() < register.get("update_frequency"):
                    logging.debug(f"Skipping register {register.get('name')}, has been read within update_frequency.")
                    continue
                if register_type == register['type'] and register['address'] == run:
                    register_value = self.interpret_value_for_register(self, rr, num, register)
                    # remember the last update timestamp in the register, if the register has an individual update_frequency configured:
                    if register.get("update_frequency"):
                        register.put("last_update", timedate.now())

                    # Set the final register value with adjustments above included 
                    self.latest_scrape[register_name] = register_value
        logging.info(f"Finished reading a single range of data.")
        return True


    def validateRegister(self, check_register):
        for register in self.registers:
            if check_register == register['name']:
                return True
        for register in self.registers_custom:
            if check_register == register['name']:
                return True
        return False

    def getRegisterAddress(self, check_register):
        for register in self.registers:
            if check_register == register['name']:
                return register['address']
        for register in self.registers_custom:
            if check_register == register['name']:
                return register['address']
        return '----'

    def getRegisterUnit(self, check_register):
        for register in self.registers:
            if check_register == register['name']:
                return register.get('unit','')
        for register in self.registers_custom:
            if check_register == register['name']:
                return register.get('unit','')
        return ''

    def validateLatestScrape(self, check_register):
        for register, value in self.latest_scrape.items():
            if check_register == register:
                return True
        return False

    def getRegisterValue(self, check_register):
        for register, value in self.latest_scrape.items():
            if check_register == register:
                return value
        return False

    def getHost(self):
        return self.client_config['host']

    def getInverterModel(self, clean=False):
        if clean:
            return self.inverter_config['model'].replace('.','').replace('-','')
        else:
            return self.inverter_config['model']

    def getSerialNumber(self):
        return self.inverter_config['serial_number']


    def build_dyna_scan_address_ranges(self):
        # maximum length of an address range to read in one batch.
        # According to pyModbusTCP documentation the maximum number of registers to read with read_input_registers() is 125.
        max_range_len = 125
        ranges = []
        for reg_type in ["read", "hold"]:
            # extract the registers by type because every range may only contain registers of either "hold" or "read" type.
            regs = list(filter(lambda x: x.get("type") == reg_type, self.registers))
            # Sort registers in ascending order by address.
            regs = sorted(regs, key=lambda d: d['address'])

            range_start = 0
            timenow = datetime.now()
            for reg in regs:
                # skip reg if it has an update frequency set and the last update has been within the configured update_frequency:
                if reg.get("update_frequency") and reg.get("last_update"):
                    logging.debug(f"Register {reg.get('name')} has update_frequency = {reg.get('update_frequency')} and last_update = {reg.get('last_update')}.")
                    if (datetime.now() - reg["last_update"]).total_seconds() >= reg.get("update_frequency"):
                        logging.debug(f"Dropping register {reg.get('name')} from dynamically build scrape range due to update frequency.")
                        continue
                reg_addr =  reg.get("address")
                reg_len = self.register_length(reg)
                reg_datatype = reg.get("datatype")
                if (range_start == 0):
                    range_start = reg_addr # start a new range
                    range_end = reg_addr + reg_len - 1
                    continue
                if reg_addr < range_start + max_range_len - (reg_len - 1):
                    range_end = reg_addr + reg_len - 1
                    continue
                # previous register did not fit in the current range anymore. Emit current range and start a new one
                ranges.append({"start": range_start - 1, "range": range_end - range_start + 1, "type": reg_type})
                range_start = 0
            # loop finished, now complete the last open range, if one has been started:
            if range_start > 0:
                ranges.append({"start": range_start - 1, "range": range_end - range_start + 1, "type": reg_type})

        logging.debug(f"Built address ranges for reading: {ranges}")
        return ranges


    def persist_registers_from_previous_scrape(self):
        # some custom registers are derived using values from the current and - if available - the previous scrape.
        # Conserve any previous values already existing or initialize if not yet present.
        if not self.inverter_config['disable_custom_registers']:
            persist_registers = {
                "run_state":                self.latest_scrape.get("run_state","ON"),
                "last_reset":               self.latest_scrape.get("last_reset",""),
                "daily_export_to_grid":     self.latest_scrape.get("daily_export_to_grid",0),
                "daily_import_from_grid":   self.latest_scrape.get("daily_import_from_grid",0),
            }
        else:
            persist_registers = None

        return persist_registers


    def convert_alarm_time_fields_to_timestamp(self):
        if self.latest_scrape.get("pid_alarm_code"):
            try:
                self.latest_scrape["alarm_timestamp"] = "%s-%s-%s %s:%02d:%02d" % (
                    self.latest_scrape["alarm_time_year"], self.latest_scrape["alarm_time_month"], self.latest_scrape["alarm_time_day"],
                    self.latest_scrape["alarm_time_hour"], self.latest_scrape["alarm_time_minute"], self.latest_scrape["alarm_time_second"],
                )   
            except Exception:
                self.latest_scrape["alarm_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.exception(f"Converting fields for alarm time into timestamp failed! Substituting values from inverter by local timestamp.")
            finally:
                for field in ["alarm_time_year", "malarm_time_onth", "alarm_time_day", "alarm_time_hour", "alarm_time_minute", "alarm_time_second"]:
                    if field in self.latest_scrape:
                        del self.latest_scrape[field]


    def convert_time_fields_to_timestamp(self):
        # A timestamp is delivered in 6 distinct time fields by the inverter, create a timestamp from these values.
        ## vr002
        try:
            if self.inverter_config.get('use_local_time',False):
                self.latest_scrape["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.debug(f'Using local computer time as timestamp for scrape: {self.latest_scrape.get("timestamp")}')       
            else:
                try:
                    self.latest_scrape["timestamp"] = "%s-%s-%s %s:%02d:%02d" % (
                        self.latest_scrape["year"], self.latest_scrape["month"], self.latest_scrape["day"],
                        self.latest_scrape["hour"], self.latest_scrape["minute"], self.latest_scrape["second"],
                    )
                    logging.debug(f'Using inverter time as timestamp for scrape: {self.latest_scrape.get("timestamp")}')       
                except Exception:
                    self.latest_scrape["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    logging.warning(f'Failed to get timestamp from inverter, using local computer time as timestamp for scrape: {self.latest_scrape.get("timestamp")}')       
        finally:
            for field in ["year", "month", "day", "hour", "minute", "second"]:
                if field in self.latest_scrape:
                    del self.latest_scrape[field]


    def create_custom_registers(self):
        ## vr001 - run_state
        # See if the inverter is running, This is added to inverters so can be read via MQTT etc...
        # It is also used below, as some registers hold the last value on 'stop' so we need to set to 0
        # to help with graphing.
        try:
            if self.latest_scrape.get('start_stop'):
                logging.debug(f"start_stop:{self.latest_scrape.get('start_stop', 'null')} work_state_1:{self.latest_scrape.get('work_state_1', 'null')}")    
                if self.latest_scrape.get('start_stop', False) == 'Start' and self.latest_scrape.get('work_state_1', False).contains('Run'):
                    self.latest_scrape["run_state"] = "ON"
                else:
                    self.latest_scrape["run_state"] = "OFF"
            else:
                logging.debug(f"Couldn't read start_stop so run_state is OFF")    
                self.latest_scrape["run_state"] = "OFF"
        except Exception:
            pass

        ## vr003 - last_reset
        date_format = "%Y-%m-%d %H:%M:%S"
        if not self.latest_scrape.get('last_reset', False):
            logging.info('Setting Initial Daily registers; daily_export_to_grid, daily_import_from_grid, last_reset')
            self.latest_scrape["daily_export_to_grid"] = 0
            self.latest_scrape["daily_import_from_grid"] = 0
            self.latest_scrape['last_reset'] = self.latest_scrape["timestamp"]
        elif datetime.strptime(self.latest_scrape['last_reset'], date_format).date() < datetime.strptime(self.latest_scrape['timestamp'], date_format).date():
            logging.info('last_reset: ' + self.latest_scrape['last_reset'] + ', timestamp: ' + self.latest_scrape['timestamp'])
            logging.info('Resetting Daily registers; daily_export_to_grid, daily_import_from_grid, last_reset')
            self.latest_scrape["daily_export_to_grid"] = 0
            self.latest_scrape["daily_import_from_grid"] = 0
            self.latest_scrape['last_reset'] = self.latest_scrape["timestamp"]

        ## vr004 - import_from_grid, vr005 - export_to_grid
        # Create a registers for Power imported and exported to/from Grid
        if self.inverter_config['level'] >= 1:
            self.latest_scrape["export_to_grid"] = 0
            self.latest_scrape["import_from_grid"] = 0

            if self.validateRegister('meter_power'):
                try:
                    power = self.latest_scrape.get('meter_power', self.latest_scrape.get('export_power', 0))
                    if power < 0:
                        self.latest_scrape["export_to_grid"] = abs(power)
                    elif power >= 0:
                        self.latest_scrape["import_from_grid"] = power
                except Exception:
                    pass
            # in this case we connected to a hybrid inverter and need to use export_power_hybrid
            # export_power_hybrid is negative in case of importing from the grid
            elif self.validateRegister('export_power_hybrid'):
                try:
                    power = self.latest_scrape.get('export_power_hybrid', 0)
                    if power < 0:
                        self.latest_scrape["import_from_grid"] = abs(power)
                    elif power >= 0:
                        self.latest_scrape["export_to_grid"] = power
                except Exception:
                    pass
        
        try: # If inverter is returning no data for load_power, we can calculate it manually
            if not self.latest_scrape["load_power"]:
                self.latest_scrape["load_power"] = int(self.latest_scrape.get('total_active_power')) + int(self.latest_scrape.get('meter_power'))
        except Exception:
            pass  

        ## vr004
        if not self.latest_scrape.get('daily_export_to_grid', False):
            self.latest_scrape["daily_export_to_grid"] = 0

        self.latest_scrape["daily_export_to_grid"] += ((self.latest_scrape["export_to_grid"] / 1000) * (self.inverter_config['scan_interval'] / 60 / 60) )

        ## vr005
        if not self.latest_scrape.get('daily_import_from_grid', False):
            self.latest_scrape["daily_import_from_grid"] = 0       

        self.latest_scrape["daily_import_from_grid"] += ((self.latest_scrape["import_from_grid"] / 1000) * (self.inverter_config['scan_interval'] / 60 / 60) )


    def scrape(self):
        logging.info(f"Start reading ranges of data from inverter.")
        scrape_start = datetime.now()

        persisted = self.persist_registers_from_previous_scrape()

        # initialize the current scrape:
        self.latest_scrape = {}

        # copy the persisted values into the current scrape:
        if persisted is not None:
            for register, value in persisted.items():
                self.latest_scrape[register] = value

        # Note that using the value from the inverter config means that if the model has been configured, it will actually never be read from the inverter:
        self.latest_scrape['device_type_code'] = self.inverter_config['model']

        load_registers_count = 0
        load_registers_failed = 0

        scraper_ranges = self.register_ranges
        # Use a dynamically compiled list of address ranges instead of the configured one, if the dyna_scan option has been enabled:
        if self.inverter_config['dyna_scan']:
            scraper_ranges = self.build_dyna_scan_address_ranges()

        for range in scraper_ranges:
            load_registers_count +=1
            logging.debug(f'Reading data, type ´{range.get("type")}`, range ´{range.get("start")}:{range.get("range")}`')
            if not self.load_registers(range.get('type'), int(range.get('start')), int(range.get('range'))):
                load_registers_failed +=1
        if load_registers_failed == load_registers_count:
            # If every scrape fails, disconnect the client
            #logging.warning
            self.disconnect()
            return False
        if load_registers_failed > 0:
            logging.warning(f'Reading: Failed to read some ranges ({load_registers_failed} of {load_registers_count})!')

        # Leave connection open, see if helps resolve the connection issues
        #self.close()

        self.convert_time_fields_to_timestamp()

        # If alarm state exists then convert to timestamp, otherwise remove it
        self.convert_alarm_time_fields_to_timestamp()

        # derive custom registers from scraped values if required:
        if not self.inverter_config.get('disable_custom_registers'):
            self.create_custom_registers()

        scrape_end = datetime.now()
        logging.info(f'Finished reading ranges of data from inverter in {(scrape_end - scrape_start).seconds}.{(scrape_end - scrape_start).microseconds} seconds.')

        return True


    def print_register_list(self):
        print(f"+------------------------------------------+-------+------+-------+")
        print("| {:<40} | {:^5} | {:<4} | {:<5} |".format('register name', 'unit', 'type', 'freq.'))
        print(f"+------------------------------------------+-------+------+-------+")
        for reg in self.registers:
            print("| {:<40} | {:^5} | {:<4} | {:>5} |".format(reg["name"], reg.get("unit", ""), reg["type"], reg.get("update_frequency", "")))
        print(f"+------------------------------------------+-------+------+-------+")
