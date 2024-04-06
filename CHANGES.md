# Change log


## Version SunGatherEvo  v1.3

### Improvements

* SunGatherEvo can now write holding registers. It will establish an HTTP
  server and listen to GET and POST requests. **Make sure to read the
documentation and understand the security implications before activating this
feature!**

## Version SunGatherEvo v1.2

### Improvements

* Updated registers-sungrow.yaml file to Sungrow specifications **Communication
  Protocol of PV Grid-Connected String Inverters V1.1.46** and **Communication
Protocol of Residential Hybrid Inverter V1.1.2**. This includes many added
inverter models as well as more added registers. The file has its own version
v2.0.0


## Version SunGatherEvo v1.1

### Improvements

* Added schema validation for the `registers-sungrow.yaml` and the
  `config.yaml` files.


## Version SunGatherEvo v1.0.0

Initial release, forked off of SunGather version v0.5.1 from
https://github.com/michbeck100/SunGather. Any changes after 2024-02-10 to the
original project by bohdans or after 2023-10-04 to michbeck100's fork are not
included in this version.

In this fork the application was renamed to **SunGatherEvo** with its own
independent version number. The first version working in my setup is thus
**SunGatherEvo v1.0.0**. It is tagged `v1.0.0` in GitHub as well as Docker Hub
accordingly.

### Fixes

* Wrong, misleading, duplicated log messages. Inappropriate levels of log
  messages. Logging to STDOUT instead of STDERR. Stack traces are logged where
appropriate.

* A serial number configured in the config file is now actually used.

* Serial numbers retrieved from the inverter will not be truncated.

* Don't crash when `--help` is provided on the command line and actually show
  usage information (as with `-h`).

* Recover instead of crashing on specific exceptions in communication with
  inverter.

* All registers delivering text (datatype UTF-8) are now interpreted as such.
  Also the correct length of these attributes is used to avoid truncating text.
The correct length of UTF-8 registers can be configured with the new `length`
attribute.

* Fixed an incompatibility caused by changes in Home Assistant.

### Improvements and Features

* Updated the register definitions to V1.1.2 of the Sungrow specification
_Communication Protocol of Residential Hybrid Inverter_. A few registers were
changed, many (not all) added.

> [!NOTE]
> Which models support which registers has not been updated with exception
of the SH8.0RT-V112 model.

* Register patch facility: Change register attributes, rename
registers and add new register definitions from the config.yaml. No need to
change the `registers-sungrow.yaml` file.

* On startup SunGatherEvo will print the list of registers as defined in the
  configuration file (after patching, see above). A second list is printed
after filtering the list by model and configured level showing the registers
that will _effectively_ be requested from the inverter.

* A volume `registers` is now exposed for docker builds which allows providing
  your own `registers-sungrow.yaml` when using docker.

* The creation of hard coded custom registers can be turned off using a feature
toggle.

* Reading battery registers is now possible.


### Optimizations

* Register update frequencies: Unlike the original, SunGatherEvo will not
  always read every register (limited by level and model) every time it
requests data from the inverter: Registers can individually be configured for
less frequent reading with the `update_frequency` parameter. This helps
reducing traffic and storage requirements.

* Dynamically calculated address ranges: Instead of using statically configured
  address ranges from the `registers-sungrow.yaml` file, SunGatherEvo will
dynamically calculate address ranges to read from the inverter. This reduces
the number of requests as well as the amount of data requested from the
inverter in comparison with the original.

### Internal changes

* Repository cleanup: Some files only relevant in the original project have been
removed from this fork.

* Docker build: The image size is reduced by using a multi stage build.

* GitHub: The workflow for building a docker image and publishing to Docker Hub
has been changed. Docker images are pushed with `latest` tag (only) on push to
main branch. On tagging in GitHub an image is pushed to Docker Hub with the
respective Tag as version number.

* Some libraries have been updated, notably pycryptodomex (removed the pinning
  of an older version) and paho.mqtt (required minor changes in the mqtt export
module).

* A docker-compose.yml file is added for `docker compose watch`.

* Code quality: Many refactorings, especially removal of duplicated code,
  splitting of very long routines into smaller ones, many code comments to
improve readability and maintainability. Code factored out into separate
utility classes. All new classes as well as `sungather.py` are formatted and
linted with `ruff` (no integration into the GitHub workflow yet).

