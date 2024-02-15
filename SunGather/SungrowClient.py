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
            "model":            config_inverter.get('model'),
            "serial_number":    config_inverter.get('serial_number'),
            "level":            config_inverter.get('level'),
            "scan_interval":    config_inverter.get('scan_interval'),
            "use_local_time":   config_inverter.get('use_local_time'),
            "smart_meter":      config_inverter.get('smart_meter'),
            "connection":       config_inverter.get('connection'),
            "slave":            config_inverter.get('slave'),
            "start_time":       ""
        }
        self.client = None
        
        self.registers = [[]]
        self.registers.pop() # Remove null value from list
        self.registers_custom = [   {'name': 'run_state', 'address': 'vr001'},
                                    {'name': 'timestamp', 'address': 'vr002'},
                                    {'name': 'last_reset', 'address': 'vr003'},
                                    {'name': 'export_to_grid', 'unit': 'W', 'address': 'vr004'}, 
                                    {'name': 'import_from_grid', 'unit': 'W', 'address': 'vr005'}, 
                                    {'name': 'daily_export_to_grid', 'unit': 'kWh', 'address': 'vr006'}, 
                                    {'name': 'daily_import_from_grid', 'unit': 'kWh', 'address': 'vr007'}
                                ]

        self.register_ranges = [[]]
        self.register_ranges.pop() # Remove null value from list

        self.latest_scrape = {}

    def connect(self):
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
        logging.info("Connection: " + str(self.client))

        try:
            self.client.connect()
        except:
            return False

        time.sleep(3)       # Wait 3 seconds, fixes timing issues
        return True

    def checkConnection(self):
        logging.debug("Checking Modbus Connection")
        if self.client:
            if self.client.is_socket_open():
                logging.debug("Modbus, Session is still connected")
                return True
            else:
                logging.info(f'Modbus, Connecting new session')
                return self.connect()
        else:
            logging.info(f'Modbus client is not connected, attempting to reconnect')
            return self.connect()

    def close(self):
        if self.inverter_config['connection'] == "http":
            return
        logging.info("Closing Session: " + str(self.client))
        try:
            self.client.close()
        except:
            pass

    def disconnect(self):
        logging.info("Disconnecting: " + str(self.client))
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


    def load_registers(self, register_type, start, count=100):
        try:
            logging.debug(f'load_registers: {register_type}, {start}:{count}')
            if register_type == "read":
                rr = self.client.read_input_registers(start,count=count, unit=self.inverter_config['slave'])
            elif register_type == "hold":
                rr = self.client.read_holding_registers(start,count=count, unit=self.inverter_config['slave'])
            else:
                raise RuntimeError(f"Unsupported register type: {type}")
        except Exception as err:
            logging.warning(f"No data returned for {register_type}, {start}:{count}")
            logging.debug(f"{str(err)}')")
            return False

        if rr.isError():
            logging.warning(f"Modbus connection failed")
            logging.debug(f"{rr}")
            return False

        if not hasattr(rr, 'registers'):
            logging.warning("No registers returned")
            return False

        if len(rr.registers) != count:
            logging.warning(f"Mismatched number of registers read {len(rr.registers)} != {count}")
            return False

        for num in range(0, count):
            run = int(start) + num + 1

            for register in self.registers:
                if register_type == register['type'] and register['address'] == run:
                    register_name = register['name']

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
                    elif register.get('datatype') == "UTF-8": # This seems to be Serial only, 10 bytes
                        utf_value = register_value.to_bytes(2, 'big')
                        for x in range(1,5):
                            utf_value += rr.registers[num+x].to_bytes(2, 'big')
                        register_value = utf_value.decode()


                    # We convert a system response to a human value 
                    if register.get('datarange'):
                        match = False
                        for value in register.get('datarange'):
                            if value['response'] == rr.registers[num] or value['response'] == register_value:
                                register_value = value['value']
                                match = True
                        if not match:
                            default = register.get('default')
                            logging.debug(f"No matching value for {register_value} in datarange of {register_name}, using default {default}")
                            register_value = default

                    if register.get('accuracy'):
                        register_value = round(register_value * register.get('accuracy'), 2)

                    # Set the final register value with adjustments above included 
                    self.latest_scrape[register_name] = register_value
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

    def scrape(self):        
        scrape_start = datetime.now()

        # Clear previous inverter values, persist some values
        persist_registers = {
            "run_state":                self.latest_scrape.get("run_state","ON"),
            "last_reset":               self.latest_scrape.get("last_reset",""),
            "daily_export_to_grid":     self.latest_scrape.get("daily_export_to_grid",0),
            "daily_import_from_grid":   self.latest_scrape.get("daily_import_from_grid",0),
        }

        self.latest_scrape = {}
        self.latest_scrape['device_type_code'] = self.inverter_config['model']

        for register, value in persist_registers.items():
            self.latest_scrape[register] = value

        load_registers_count = 0
        load_registers_failed = 0

        for range in self.register_ranges:
            load_registers_count +=1
            logging.debug(f'Scraping: {range.get("type")}, {range.get("start")}:{range.get("range")}')
            if not self.load_registers(range.get('type'), int(range.get('start')), int(range.get('range'))):
                load_registers_failed +=1
        if load_registers_failed == load_registers_count:
            # If every scrape fails, disconnect the client
            #logging.warning
            self.disconnect()
            return False
        if load_registers_failed > 0:
            logging.info(f'Scraping: {load_registers_failed}/{load_registers_count} registers failed to scrape')

        # Leave connection open, see if helps resolve the connection issues
        #self.close()

        ## vr002
        if self.inverter_config.get('use_local_time',False):
            self.latest_scrape["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.debug(f'Using Local Computer Time: {self.latest_scrape.get("timestamp")}')       
            del self.latest_scrape["year"]
            del self.latest_scrape["month"]
            del self.latest_scrape["day"]
            del self.latest_scrape["hour"]
            del self.latest_scrape["minute"]
            del self.latest_scrape["second"]
        else:
            try:
                self.latest_scrape["timestamp"] = "%s-%s-%s %s:%02d:%02d" % (
                    self.latest_scrape["year"],
                    self.latest_scrape["month"],
                    self.latest_scrape["day"],
                    self.latest_scrape["hour"],
                    self.latest_scrape["minute"],
                    self.latest_scrape["second"],
                )
                logging.debug(f'Using Inverter Time: {self.latest_scrape.get("timestamp")}')       
                del self.latest_scrape["year"]
                del self.latest_scrape["month"]
                del self.latest_scrape["day"]
                del self.latest_scrape["hour"]
                del self.latest_scrape["minute"]
                del self.latest_scrape["second"]
            except Exception:
                self.latest_scrape["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.warning(f'Failed to get Timestamp from Inverter, using Local Time: {self.latest_scrape.get("timestamp")}')       
                del self.latest_scrape["year"]
                del self.latest_scrape["month"]
                del self.latest_scrape["day"]
                del self.latest_scrape["hour"]
                del self.latest_scrape["minute"]
                del self.latest_scrape["second"]
                pass

        # If alarm state exists then convert to timestamp, otherwise remove it
        try:
            if self.latest_scrape["pid_alarm_code"]:
                self.latest_scrape["alarm_timestamp"] = "%s-%s-%s %s:%02d:%02d" % (
                    self.latest_scrape["alarm_time_year"],
                    self.latest_scrape["alarm_time_month"],
                    self.latest_scrape["alarm_time_day"],
                    self.latest_scrape["alarm_time_hour"],
                    self.latest_scrape["alarm_time_minute"],
                    self.latest_scrape["alarm_time_second"],
                )   
            del self.latest_scrape["alarm_time_year"]
            del self.latest_scrape["alarm_time_month"]
            del self.latest_scrape["alarm_time_day"]
            del self.latest_scrape["alarm_time_hour"]
            del self.latest_scrape["alarm_time_minute"]
            del self.latest_scrape["alarm_time_second"]
        except Exception:
            pass

        ### Custom Registers
        ######################

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
                logging.info(f"DEBUG: Couldn't read start_stop so run_state is OFF")    
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

        scrape_end = datetime.now()
        logging.info(f'Inverter: Successfully scraped in {(scrape_end - scrape_start).seconds}.{(scrape_end - scrape_start).microseconds} secs')

        return True
