# SunGatherEvo Configuration Reference

Also see
[config-example.yaml](https://github.com/ludifu/SunGather/blob/main/SunGather/config-example.yaml)
for information.

## Section `inverter`

In this section the access to the inverter is configured.  All parameters are
optional and have sensible defaults.

- `host` - IP address of your inverter or modbus-proxy (default: `localhost`).

- `port` - Port of your inverter (default: `502` or `8082` depending on whether
the connection is `modbus` or `http`)

- `connection` - How SunGatherEvo contacts your inverter. Valid options are
`modbus` (this is the default), `http` (for access by http protocol) or
`sungrow` (for old models).

- `slave` - The slave id of your inverter. Default is 1.

- `timeout` and `retries` - Parameters for the low level access to the inverter.

- `scan_interval` - Seconds between read attempts. Default is 30 seconds, i.e.
SunGatherEvo tries to read twice per minute. Lower value gives more frequent
reads, however the inverter's network interface may become instable.

- `model` - SunGatherEvo only reads registers which are supported by your
  inverter's model. Without model SunGatherEvo will read onyl a very small
subset of registers available to all models. Nonetheless this parameter is only
required, if SunGatherEvo fails to detect your inverter's model. This will
happen (and shown in the log!), when a new model is not yet known to
SunGatherEvo.

- `serial` - SunGatherEvo reads the inverter's serial number on startup.
  Unless this fails (which would be visible in the log!) you do not need to
configure this parameter. The serial number is used by some exports.

- `smart_meter` - Some non-hybrid inverters may optionally be installed with a
  smart meter. This makes available additional registers for these models.
Default is False. This is not required for hybrid inverters.

- `use_local_time` - Makes SunGatherEvo use a local timestamp instead of the
  time stamp delivered by the inverter. Default is False. This parameter is
only used if you let SunGatherEvo create the legacy custom fields (see below).

- `log_console` - Set the log level for console logging. Possible levels are
`DEBUG`, `INFO`, `WARNING` (default), `ERROR`.

- `log_file` - Set the log level for the separate log file. Available levels like
log_console plus `OFF` (default) which turns off file logging.

- `level` - How much data will be read from the inverter. Level 1 (default)
  reads only a few important fields, level 2 most fields, and level 3 tries to
read everything whether the inverter supports it or not. Also see the [original
documentation](https://github.com/bohdan-s/SunGather/blob/main/README.md#registers).

- `dyna_scan` - Whether to dynamically determine address areas to read from the
  inverter. The default is True. This parameter is new to SunGatherEvo to make
it possible to disable the optimization should the need arise. It should be set
to False only, if you experience errors or exceptions in the log while reading
from the inverter.
                                            
- `disable_legacy_custom_registers` - SunGatherEvo still contains the code to
  create custom registers from the original project. Setting this feature
toggle to True will disable the legacy code. (The default is False.) This
switch allows to disable this. Custom fields cann be created by a configuration
in SunGatherEvo and contains example configuration for all legacy custom
fields.

## Subsection `register_patches`

This section is part of the `inverter` section and allows the following
operations.[^1]

[^1]: All of these changes could be made in the registers configuration file
directly as well. However you cannot update a registers file as easily
anymore if you made individual changes there.

### Change attributes of registers

For example change `length` to 15, `datatype` to UTF-8 and `level` to 1.

```
    - name: ".*_software_version"
      length: 15
      datatype: "UTF-8"
      level: 1
```

> [!TIP]
> You can use regular expressions for such changes as shown in the
example.

### Add attributes to registers

For example the new attribute `update_frequency`:

```
    - name: (protocol_.*|.*_software_version)
      update_frequency: 3600
```

> [!TIP]
> The new `update_frequency` attribute causes SunGatherEvo to skip reading
an attribute if it has been read within the last number of seconds configured
here. Many registers will actually never be changed like a serial number or
very infrequently like an installed nominal power.

### Add a register

Simply specify it with all required attributes plus `type` set to either "hold"
or "read". Obviously this is for cases only when your inverter supports a
register which is not yet included in the registers-sungrow.yaml file.

```
    - name: "new_register"
      type: "read"
      address: <valid address>
      unit: "W"
      accuracy: 0.1
      level: 3
```

If you add a battery register you need to specify the `slave` parameter to 200.

```
    - name: "new_battery_register"
      type: "read"
      slave: 200
      address: <valid address>
```
 

### Rename a register

This works by using the pseudo attribute `change_name_to`, for example:

```
    - name: "load_power_hybrid"
      change_name_to: "load_power"
```

> [!NOTE]
> The entries in this section are evaluated top down. I.e. if an attribute
of a specific register is changed by more than one entry in this section, the
last of these changes will win.

Limitation: You cannot delete a register using this feature. Deleting a
register can however easily be simulated by setting its level to anything > 3.

## Subsection `customfields` 

This section is part of the `inverter` section.

Use this section to create custom fields which cannot be retrieved from the
inverter, but are calculated from other values.

All formulae are actual Python code.[^2] The examples should be straightforward though.

[^2]: Technically speaking a Python expression. Expressions must return a value
which will be used as the value for the custom field.

> [!IMPORTANT]
> When creating expressions make sure you carefully watch the log to check
whether they are syntactically correct! You _are_ writing code after
all. Any syntax errors will be shown with a stack trace in the log.
Once your expression compiles without error it can still fail if it refers to
non existing values. Such cases can only be detected when the expressions are
actually evaluated.

Example:

```
  - name: "total_self_consumption"
    expression: "total_direct_energy_consumption / total_pv_generation * 100.0"
    guard: "total_pv_generation > 0 and total_direct_energy_consumption > total_pv_generation"
```

This entry creates a custom field `total_self_consumption`. It will be
calculated as shown in the `expression` unless `guard` is
evaluated to False.[^3] The field is then available just like any field retrieved
from the inverter. `name` and `expression` are mandatory, `guard` and everything
else is optional.

[^3]: `guard` is a Python expression as well. The return value of this
expression is not strictly required to be True or False, but it is tested
for Trueness / Falseness.

You can add a unit to a field. It should be configured to a field like "%" or
"kWh". The unit is available to exports, but has no other function in
SanGatherEvo apart from this.

```
  - name: "total_self_consumption"
    expression: "total_direct_energy_consumption / total_pv_generation * 100.0"
    unit: "%"
```

If any of the required fields for the calculation of the expression or the
guard condition are not available, then nothing bad will happen. (There will be
a WARNING in the log, though.) This is actually not unexpected, because
attributes may not be read at every iteration.

It is possible to configure a fallback value for the case the evaluation fails.
If evaluation is not possible for example because a variable is missing, then
the fallback[^4] will be used:

```
  - name: "total_self_consumption"
    expression: "total_direct_energy_consumption / total_pv_generation * 100.0"
    fallback: "0"
```

[^4]: The fallback is a Python expression as well, i.e. a calculation is possible
instead of a simple value.

Expressions may refer to `datetime` as shown in the example:

```
  - name: "timestamp"
    expression: "datetime.now().strftime('%Y-%m-%d %H:%M:%S')"
```

Custom fields can be aggregated on a daily[^5]  basis, for example a field
`daily_export_to_grid` with an aggregated daily value of `export_to_grid`:

[^5]: It is possible to configure "total" instead of "daily" here. The
aggregated value will not be reset at all then. Unless you are interested
in a total since last start of SunGatherEvo you should avoid this. Use a
time series database, if you are interested in aggregated total values.

```
  - name: "daily_export_to_grid"
    expression: "export_to_grid / 1000 / 60 / 60 * seconds_since_last_update()"
    aggregate: "daily"
```

The result of the expression is added to the running daily value. It will be
reset to 0 at midnight.[^6] For the calculation a function
`seconds_since_last_update()` is available which delivers the number of seconds
since the custom field was calculated the last time.

[^6]: On the first evaluation of an aggregated custom field SunGatherEvo
assumes a last reset on last midnight. This will cause the values to be off
on the first day unless SunGatherEvo is started shortly after midnight.
If SunGatherEvo runs without interruption on subsequent days the values
calculated can be considered ok. SunGatherEvo is meant to run continuously, so
this should not be a problem.

Entries can be configured to be executed only if an attribute with the
corresponding name is not yet available (`new_only`) or if it is already
available and will be overwritten (`replace_only`) as shown in these examples.
This is useful for more complicated cases of fallbacks:

```
  - name: "load_power"
    expression: "int(total_active_power) + int(meter_power)"
    write_mode: "new_only" 
```

and

```
  - name: "load_power_times_10"
    expression: "load_power * 10"
    write_mode: "replace_only"
```

The custom field feature is not limited to Python expressions. Python
statements are possible as well. A statement is an arbitrary piece of code
which does not need to return a value, but can contain more complex logic.

An entry in this section cannot have both an expression and a statement.

As an easy example an entry to remove a field from the data:

```
  - name: "remove date field month"
    statement: "if results.get('month', False): del results['month']"
```

Statements have access to the values of the registers just like expressions.

Also they have access to a list of registers in the `results` variable. A
statement may change this list to store or even delete values.

Statements can also store arbitrary values into a dictionary `previous_results`
which will be available the next time this statement is evaluated. Values in
this dictionary do not become part of the result.


## Section imports

Imports are used to modify the inverter configuration.

This section contains one import `http` which can be enabled. This import
allows sending HTTP POST requests to SunGatherEvo. The request body must
contain a json representation of a dictionary with key value pairs of register
names and values.

The register names must be in the list of holding registers which SunGatherEvo
is configured to read from the inverter after evaluating the
`registers-sungrow.yaml` file, applying any register patches and filtering for
model compatibility and level.

An example POST call via `curl` made from `localhost` to set the `soc-reserve`
register to 14:

```
curl -s -X POST 'http://0.0.0.0:8888/registers' --data '{ "soc_reserve" : 14 }' | jq
```

This call assumes the port is configured to 8888. The call will return a json structure
indicating the effective addresses and values written to the inverter. (Piping
to `jq` can be omitted, this is not part of the call, just for visualization of the result.)

> [!CAUTION]
> Enabling the web server is a significant security risk! There is no
> authentication / authorization. Before enabling this server make sure you
> understand the security risks this imposes!



## Section exports

This section is completely unchanged form the original project (as are the
actual export modules). Refer to the [original
documentation](https://github.com/bohdan-s/SunGather/blob/main/README.md#exports)
for details.

