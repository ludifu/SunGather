class export_console(object):
    def __init__(self):
        pass

    # Configure Console
    def configure(self, config, inverter):
        print("+--------------------------------------------------------+")
        print("| {:^54} |".format("Inverter Configuration Settings"))
        print("+--------------------------------------------------------+")
        print("{:<30} {:<25} {:<1}".format("| " + "Config", "| " + "Value", "|"))
        print("+------------------------------+-------------------------+")
        for setting, value in inverter.client_config.items():
            print(
                "{:<30} {:<25} {:<1}".format(
                    "| " + str(setting), "| " + str(value), "|"
                )
            )
        for setting, value in inverter.inverter_config.items():
            print(
                "{:<30} {:<25} {:<1}".format(
                    "| " + str(setting), "| " + str(value), "|"
                )
            )
        print("+------------------------------+-------------------------+")

        return True

    def publish(self, inverter):
        max_name_len = 1
        for reg in inverter.get_my_register_list():
            max_name_len = max(max_name_len, len(reg["name"]))
        table_width = 42 + max_name_len

        bar = "+" + str.ljust("", table_width, "-") + "+"

        print(bar)
        print(
            "| {:<7} | ".format("Address")
            + str(str.ljust("Register", max_name_len))
            + " | {:<27} |".format("Value")
        )
        print(bar)
        for register, value in inverter.latest_scrape.items():
            print(
                "| {:<7} | ".format(str(inverter.getRegisterAddress(register)))
                + str(str.ljust(register, max_name_len))
                + " | {:<27} |".format(
                    str(value) + " " + str(inverter.getRegisterUnit(register))
                )
            )
        print(bar)

        print(f"Logged {len(inverter.latest_scrape)} registers to Console")
        return True
