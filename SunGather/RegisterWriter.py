#!/usr/bin/python3

import json
from functools import cached_property
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlparse
import threading
from collections import deque

import logging

# First working version.

# TODO Use datarange attributes of registers to allow specifying data in the
# format the client uses for output, especially "enabled" or "disabled" instead
# of numeric values.

# Possible enhancements:

# Provide some more meaningful http methods like GET for /registers to
# provide all registers or at least some user inforamtion pointiung to a
# possible usage of curl.

# GET could as well produce a small form which can be used to provide the PUT
# request. This would allow remote operation without a console. (It could be
# made into a more complete web application, but this used framework is not
# best suited for this.)


def _thread_start():
    # Must be a function (not a method) to be used in the Thread() constructor
    # ...
    r = RegisterWriter()
    server = HTTPServer(("0.0.0.0", r.serverport), WebRequestHandler)
    server.serve_forever()


class RegisterWriter(object):
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
        # of this class. Subsequent calls will fail and log an error.
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
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.get_response().encode("utf-8"))

    def do_POST(self):
        rw = RegisterWriter()
        sgclient = rw._sungrow_client
        if self.url.path != "/registers":
            logging.warning(
                f"Integrated HTTP Server is not serving requested path: ´{self.url.path}`."
            )
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

        updates = {}
        try:
            for key, value in postdata.items():
                register = None
                for reg in sgclient.get_my_register_list():
                    if key == reg["name"]:
                        register = reg
                        logging.debug(
                            f"Matched register ´{key}` for updating with value ´{value}`."
                        )
                        break

                if register is not None:
                    # register is part of the registers which are known to the
                    # inverter client (configured as either custom field or in
                    # the registers-sungrow.yaml file, not excluded due to
                    # level, not exccluded due to model support.)
                    if register.get("type") == "hold":
                        # register must be a hold register as we cannot write
                        # to read registers ...
                        address = register.get("address")
                        if address is not None:
                            # custom registers do not have an actual address.
                            # These should not be 'hold' registers' anyway, but
                            # who knows what has been configured ...
                            if isinstance(value, int):
                                # we can only update with integer values.
                                datatype = register.get("datatype")
                                if (
                                    datatype == "S16"
                                    and value <= 32767
                                    and value >= -32768
                                ) or (
                                    datatype == "U16" and value <= 65536 and value >= 0
                                ):
                                    # FINALLY!!!!

                                    # TODO
                                    # Well, nearly. We need to convert the
                                    # value according to the accuracy of the
                                    # register definition

                                    updates[address] = value
                                else:
                                    logging.error(
                                        f"Value ´{value}` is not suitable for datatype ´{datatype}` of register ´{key}`!"
                                    )
                            else:
                                logging.error(
                                    f"Register updates require integer values, got ´{value}` instead!"
                                )
                        else:
                            logging.error(f"Cannot update custom register ´{key}`!")
                    else:
                        logging.error(
                            f"Register ´{key}` is a read register and cannot be updated!"
                        )
                else:
                    logging.error(
                        f"Register ´{key}` is not configured to be read by the inverter!"
                    )

            compacted_updates = {}
            addresses = deque(sorted([*updates]))

            while len(addresses) > 0:
                adr = addresses.popleft()
                compacted_updates[adr] = list()
                compacted_updates[adr].append(updates.get(adr))
                subs_adr = adr
                while True:
                    try:
                        # try if a subsequent address exists.
                        subs_adr += 1
                        # deleting a non existing subsequent address from
                        # addresses will throw a ValueError, thus ending the
                        # inner loop:
                        del addresses[addresses.index(subs_adr)]
                        # if deleting worked, then the address exists, append
                        # the corresponding value to the beginning address:
                        compacted_updates[adr].append(updates.get(subs_adr))
                    except ValueError:
                        break

            sgclient.checkConnection()
            for address in compacted_updates:
                logging.debug(
                    f"Write holding registers at ´{address}`, values: ´{compacted_updates[address]}` ..."
                )
                # With version 3.3.0 of PyModbus the ´unit` parameter is
                # changed to ´slave`. We keep both, otherwise it will be more
                # than difficult to identify when it stops working after an
                # update of PyModbus. Actually it is optional, however the
                # default is not what we need, so we need the parameter here
                # ...
                rr = sgclient.client.write_registers(
                    address - 1,
                    compacted_updates[address],
                    slave=sgclient.inverter_config.get("slave"),
                    unit=sgclient.inverter_config.get("slave"),
                )

                if rr.isError():
                    logging.warning("Modbus connection failed!")
                    logging.debug(f"{rr}")
                else:
                    logging.debug("... finished writing holding registers.")

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
