**SunGatherEvo** is the tool of choice for extracting data from your network
connected Sungrow inverter to make it available for monitoring for example via
Grafana or in a home automation like Home Assistant.

If you encounter any problems or have questions or suggestions or simply want
to report this fork as working for your inverter please file [an
issue](https://github.com/ludifu/SunGather/issues).

# About this fork

SunGatherEvo is a fork of [Sungather](https://github.com/bohdan-s/SunGather) from
@bohdan-s, the creator of the original project.[^1]  Without his work my fork would
not have been possible. I'm highly grateful for this.

[^1]: Actually SunGatherEvo was forked off of [another
fork](https://github.com/michbeck100/SunGather) by @michbeck100, because this
already contained many valuable updates. michbeck100 also implemented a
[monitoring stack](https://github.com/michbeck100/pv-monitoring) with InfluxDB
and Grafana, which I **highly recommend.**

When I created this fork bohdan's project had stalled for more than a year: No bugfixes,
no updates to new Sungrow specifications, no support for new inverter models,
...

I created this fork to do all of this for my own purposes. I also needed
support for reading registers from a Sungrow battery and some other features,
so I added this as well. I make it available just in case it is useful for
anyone else.

SunGatherEvo is based on version v0.5.3 (last original version from February
2023) plus changes from michbeck100. It has its own version number, starting at
`v1.0.0`.[^2] For a detailed list of changes see the [change log](CHANGES.md).

[^2]: I did not plan to contribute back into the original project via pull
    requests. The reasin is that I did not assume the original project would be
continued after an inactive period that long. So I needed a way to keep track
of development, i.e. a version number. Of course I cannot continue using the
original version number as maintaining the original project's version is the
author's exclusive right. Btw. creating my own independent version number was
the main reason why I renamed the fork to SunGatherEvo: The version number
would have been ambiguous otherwise.

# Using SunGatherEvo

Check [Using SunGather](USAGE.md) and the [configuration
refererence](REFERENCE.md) to learn how to use SunGatherEvo.

> [!TIP]
> In general SunGatherEvo _should_ behave like the original if you reuse
> your existing config file - apart from bug fixes and changed
> log messages of course).

## Supported devices

See [tested devices and supported
devices](https://github.com/bohdan-s/SunGather/blob/main/README.md#tested-devices).
Any device supported by the original project should work.

> [!IMPORTANT]
> Note that all tested devices according to the link are connected via
> WiNet-Communication Dongle.  Sungrow inverters behave differently depending
> on how they are connected to the network. Hybrid inverters have a dedicated
> LAN port in addition to a WiNet-S communication device and some registers are
> only available when this dedicated port is used. Also some registers may
> behave differently depending on which port is used.

My test scope / my installation:

* Sungrow SH8.0RT-V112 inverter and SBR096 battery.

* Access via dedicated LAN port and a modbus-proxy.

* Exports: Only mqtt with a mosquitto mqtt broker.

* Raspberry Pi4 as a monitoring server.

## Register support

Although SunGatherEvo should recognize all current hybrid inverter models by
questioning your inverter, the mapping of registers support per model is not
complete. I.e. even if SunGatherEvo will detect and display a valid inverter
model code, not all registers may be available that should be.

> [!NOTE]
> Register support by model is not as simple as it may seem. There is a large
> number of inverter models and only limited availability of up to date and
> complete manufacturer specifications.

Configuring a compatible model in your `config.yaml` as a workaround will make
the registers of the configured model available. For example SunGatherEvo is
not aware that an SH10RT-V112 is compatible with an SH10RT. If you have an
SH10RT-V112 you could configure the SH10RT and this should work.

