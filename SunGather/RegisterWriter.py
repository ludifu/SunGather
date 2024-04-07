#!/usr/bin/python3

import json
from functools import cached_property
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlparse
import threading
from collections import deque

import logging

def _thread_start():
    # Must be a function (not a method) to be used in the Thread() constructor
    # ...
    r = RegisterWriter()
    server = HTTPServer(("0.0.0.0", r.serverport), WebRequestHandler)
    server.serve_forever()


class RegisterWriter(object):

    # This class provides services to write to holding registers. It spawns an
    # HTTPServer thread and listens to POST and GET requests. Via POST request
    # to /registers and providing a JSON representation of a python dictionary
    # with register names as keys and target values as values one or more
    # holding registers can be written. A GET request to /registers will
    # deliver a list of holding registers know to the running instance of the
    # SungrowClient which can be written to.

    # The Singleton instance of this class
    _instance = None

    # The SungrowClient is required to access the register configuration and
    # the ModbusTCPClient
    _sungrow_client = None

    # The server thread
    _server_thread = None

    # The port the HTTPserver is listening on.
    serverport = None

    def __new__(cls):
        # Implements a Singleton
        if cls._instance is None:
            cls._instance = super(RegisterWriter, cls).__new__(cls)
        return cls._instance

    def setup(self, sgclient, port=8888):
        # This method must be called exactly once after acquiring an instance
        # of this class. A fully configured (i.e. including registers) instance
        # of a SungrowClient must be provided. Subsequent calls will fail and
        # log an error.
        if self._sungrow_client is None:
            self._sungrow_client = sgclient
            self.serverport = port
            self._server_thread = threading.Thread(target=_thread_start)
            # setting daemon to True causes the thread to terminate when the
            # main programm stops:
            self._server_thread.daemon = True
            self._server_thread.start()
        else:
            logging.error("The server thread is already running!")

    def determine_updates(self, postdata):
        # retrieve register names and target values from post_data and create
        # and return a dictionary containing the target addresses and target
        # values.
        updates = {}
        for key, value in postdata.items():
            register = None
            for reg in self._sungrow_client.get_my_register_list():
                if key == reg["name"]:
                    register = reg
                    logging.debug(f"Matched register ´{key}`.")
                    break
            self._check_and_add_register(register, value, updates)
        return updates

    def _check_and_add_register(self, register, target_value, updates):
        # Check if the register can be updated with the provided target value
        # and if so add it to the updates dictionary.
        if register is None:
            # register is not part of the registers which are known to the
            # inverter client (configured as either custom field or in
            # the registers-sungrow.yaml file, not excluded due to
            # level, not exccluded due to model support.)
            logging.error(f"Unknown register ´{register['name']}`!")
            return

        if register.get("type") != "hold":
            # register must be a hold register as we cannot write
            # to read registers ...
            logging.error(f"Cannot update read register ´{register['name']}`!")
            return

        address = register.get("address")
        if address is None:
            # custom registers do not have an actual address.  These should not
            # be 'hold' registers' anyway, but who knows what has been
            # configured ...
            logging.error(f"Cannot update custom register ´{register['name']}`!")
            return

        datarange = register.get("datarange")
        if datarange is not None:
            # If the provided target value is found in the mapping substitute
            # with the "real" value. If the provided value is not found emit a
            # warning, but keep the target value. This allows to set registers
            # even if the mapping is not known by specifying the required
            # integer number directly. If an unknow string is provided this
            # would not work, but this case is covered by the next check.
            match = False
            for entry in datarange:
                if entry["value"] == target_value:
                    target_value = entry["response"]
                    match = True
                    break
            if not match:
                logging.warning(
                    f"Value ´{target_value}` not found in the value mapping for register ´{register['name']}`!"
                )

        accuracy = register.get("accuracy")
        if accuracy is not None:
            # Apply an accuracy value if configured for that register. The
            # accuracy is a factor to apply to a register read from the
            # inverter. For writing a division is required. The result must be
            # an integer, so apply integer division.
            target_value = target_value // accuracy

        if not isinstance(target_value, int):
            # we can only update with integer values.
            logging.error(f"Integer required, got ´{target_value}` instead!")
            return

        datatype = register.get("datatype")
        if not (
            (datatype == "S16" and target_value <= 32767 and target_value >= -32768)
            or (datatype == "U16" and target_value <= 65536 and target_value >= 0)
        ):
            logging.error(
                f"Value ´{target_value}` is not suitable for datatype ´{datatype}` of register ´{register['name']}`!"
            )
            return

        updates[address] = target_value

    def compact_updates(self, update_dict):
        # update_dict contains key value pairs of register addresses and target
        # values. Create and return a dictionary containing addresses as keys
        # and a list of target values to write starting at the address.
        # Rationale: The PyModbus can write a list of values to a starting
        # address. Instead of one write operation per register this requires
        # only one write operation per contiguous address area.
        compacted_updates = {}

        # To handle the addresses in ascending order, use a deque to be able to
        # pop finished values from the left side.
        addresses = deque(sorted([*update_dict]))

        while len(addresses) > 0:
            adr = addresses.popleft()
            compacted_updates[adr] = list()
            compacted_updates[adr].append(update_dict.get(adr))
            subs_adr = adr
            while True:
                try:
                    # assume a subsequent address ...
                    subs_adr += 1
                    # ... and try to delete it from the addresses. Deleting a
                    # non existing address will throw a ValueError, thus ending
                    # the inner loop:
                    del addresses[addresses.index(subs_adr)]
                    # if deleting worked, then the address exists, append the
                    # corresponding value to the list at the beginning address:
                    compacted_updates[adr].append(update_dict.get(subs_adr))
                except ValueError:
                    break
        return compacted_updates

    def write_updates(self, compacted_update_dict):
        try:
            # avoid updates to holding registers while the SungrowClient is
            # reading data:
            self._sungrow_client.sem.acquire()
            self._write_updates_guarded(compacted_update_dict)
        finally:
            self._sungrow_client.sem.release()

    def _write_updates_guarded(self, compacted_update_dict):
        self._sungrow_client.checkConnection()
        for address, vals in compacted_update_dict.items():
            logging.debug(f"Write ´{vals}` to ´{address}` ...")
            # With version 3.3.0 of PyModbus the ´unit` parameter is
            # changed to ´slave`. We keep both, otherwise it will be more
            # than difficult to identify when it stops working after an
            # update of PyModbus. Actually it is optional, however the
            # default is not what we need, so we need the parameter here
            # ...
            rr = self._sungrow_client.client.write_registers(
                address - 1,
                vals,
                slave=self._sungrow_client.inverter_config.get("slave"),
                unit=self._sungrow_client.inverter_config.get("slave"),
            )
            if rr.isError():
                logging.warning("Modbus connection failed!")
                logging.debug(f"{rr}")
            else:
                logging.debug("... finished writing holding registers.")


class WebRequestHandler(BaseHTTPRequestHandler):
    @cached_property
    def url(self):
        return urlparse(self.path)

    @cached_property
    def query_data(self):
        return dict(parse_qsl(self.url.query))

    @cached_property
    def post_data(self):
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    @cached_property
    def form_data(self):
        return dict(parse_qsl(self.post_data.decode("utf-8")))

    @cached_property
    def cookies(self):
        return SimpleCookie(self.headers.get("Cookie"))

    def get_response(self):
        return json.dumps(
            {
                "path": self.url.path,
                "query_data": self.query_data,
                "post_data": self.post_data.decode("utf-8"),
                "form_data": self.form_data,
                "cookies": {
                    name: cookie.value for name, cookie in self.cookies.items()
                },
            }
        )

    def do_GET(self):
        if self.url.path != "/registers":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.get_response().encode("utf-8"))
        else:
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                rw = RegisterWriter()
                regs = [
                    reg["name"]
                    for reg in rw._sungrow_client.get_my_register_list()
                    if (reg.get("type") == "hold" and reg.get("address") is not None)
                ]
                self.wfile.write(json.dumps(regs).encode("utf-8"))
            except Exception as err:
                # Not clear what went wrong if we end up here, so report a server
                # error.
                logging.exception(err)
                self.send_response(500)
                self.end_headers()
                return

    def do_POST(self):
        if self.url.path != "/registers":
            logging.warning(f"Illegal path: ´{self.url.path}`.")
            self.send_response(404)
            self.end_headers()
            return

        try:
            postdata = json.loads(self.post_data.decode("utf-8"))
        except Exception:
            logging.error(f"Could not decode POST data: ´{self.post_data}`.")
            self.send_response(400)
            self.end_headers()
            return

        try:
            rw = RegisterWriter()
            updates = rw.determine_updates(postdata)
            compacted_updates = rw.compact_updates(updates)
            rw.write_updates(compacted_updates)
        except Exception as err:
            # Not clear what went wrong if we end up here, so report a server
            # error.
            logging.exception(err)
            self.send_response(500)
            self.end_headers()
            return

        # Everything worked, report an HTTP 200 and the structire written to
        # the registers.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(compacted_updates).encode("utf-8"))
