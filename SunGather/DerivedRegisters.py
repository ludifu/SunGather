#!/usr/bin/python3

import logging


class DerivedRegisters:

    # Calculate derived registers from existing registers in the data retrieved
    # from the inverter.

    # If prerequisites for calculations are not met, then the derived registers
    # will not be calculated. No error will be logged in case prerequisites are not
    # met. This is expected: Whether prerequisite registers are available in the
    # data depends on the configured level configured and the configured (or
    # detected) inverter model.

    # Derived registers are available with name and value just like scraped
    # registers. There is no detailed configuration for which derived registers are
    # created and which are not. This class will calculate all derived registers.

    # This class has no state. None of the derived registers calculated here are
    # dependent from values of previously read values.

    def __init__(self, inverter):

        self.data = inverter.latest_scrape

    def calc(self):
        self.create_reg_daily_self_consumption_ratio()
        self.create_reg_total_self_consumption_ratio()
        self.create_reg_self_sufficiency_rate()
        self.create_reg_residential_consumption()
        self.create_regs_power_flow()
        self.create_reg_battery_total_charge_efficiency()
        self.create_reg_battery_load_cycles()
        self.create_reg_mppt_power()

    def create_reg_mppt_power(self):
        if "mppt_1_voltage" in self.data and "mppt_1_current" in self.data:
            self.data["mppt_1_power"] = (
                self.data["mppt_1_voltage"] * self.data["mppt_1_current"]
            )
        if "mppt_2_voltage" in self.data and "mppt_2_current" in self.data:
            self.data["mppt_2_power"] = (
                self.data["mppt_2_voltage"] * self.data["mppt_2_current"]
            )
        if "mppt_3_voltage" in self.data and "mppt_3_current" in self.data:
            self.data["mppt_3_power"] = (
                self.data["mppt_3_voltage"] * self.data["mppt_3_current"]
            )

        if "mppt_1_power" in self.data:
            self.data["mppt_power"] = self.data["mppt_1_power"]
        if "mppt_2_power" in self.data:
            self.data["mppt_power"] += self.data["mppt_2_power"]
        if "mppt_3_power" in self.data:
            self.data["mppt_power"] += self.data["mppt_3_power"]

        return True

    def create_reg_battery_total_charge_efficiency(self):
        if not "total_battery_discharge_energy" in self.data:
            return False
        if not "total_charge_energy" in self.data:
            return False
        self.data["battery_total_charge_efficiency"] = (
            self.data["total_battery_discharge_energy"]
            / self.data["total_charge_energy"]
            * 100.0
        )
        return True

    def create_reg_battery_load_cycles(self):
        if not "total_charge_energy" in self.data:
            return False
        if not "battery_capacity_high_precision" in self.data:
            return False
        self.data["battery_load_cycles"] = (
            self.data["total_charge_energy"]
            / self.data["battery_capacity_high_precision"]
        )
        return True

    def create_reg_daily_self_consumption_ratio(self):
        if not "daily_export_energy" in self.data:
            return False
        if not "daily_pv_generation" in self.data:
            return False

        if self.data["daily_pv_generation"] <= 0:
            # generated energy must be > 0.
            self.data["daily_self_consumption_ratio"] = 0
        elif self.data["daily_export_energy"] > self.data["daily_pv_generation"]:
            # cannot have consumed more generated energy than has been generated.
            self.data["daily_self_consumption_ratio"] = 100.0
        else:
            self.data["daily_self_consumption_ratio"] = (
                (self.data["daily_pv_generation"] - self.data["daily_export_energy"])
                / self.data["daily_pv_generation"]
                * 100.0
            )
        return True

    def create_reg_total_self_consumption_ratio(self):
        # Calculation:  (generated - exported) / generated

        # generated is the pv generated energy (SunGather: total_pv_generation)
        # and exported is the total_export_energy.

        # fail if prerequisites are missing:
        if not "total_export_energy" in self.data:
            return False
        if not "total_pv_generation" in self.data:
            return False

        if self.data["total_pv_generation"] <= 0:
            # generated energy must be > 0.
            self.data["total_self_consumption_ratio"] = 0
        elif self.data["total_export_energy"] > self.data["total_pv_generation"]:
            # cannot have consumed more generated energy than has been generated.
            self.data["total_self_consumption_ratio"] = 100.0
        else:
            self.data["total_self_consumption_ratio"] = (
                (self.data["total_pv_generation"] - self.data["total_export_energy"])
                / self.data["total_pv_generation"]
                * 100.0
            )
        return True

    def create_reg_self_sufficiency_rate(self):
        # Calculation: (direct consumption + battery discharge) / (direct
        # consumption + battery discharge + imported energy)

        # Calculation for today as well as total.
        # self_sufficiency_of_today
        # self_sufficiency_total

        # Check prerequisite registers
        if not "daily_direct_energy_consumption" in self.data:
            return False
        if not "daily_battery_discharge_energy" in self.data:
            return False
        if not "daily_import_energy" in self.data:
            return False

        if not "total_direct_energy_consumption" in self.data:
            return False
        if not "total_battery_discharge_energy" in self.data:
            return False
        if not "total_import_energy" in self.data:
            return False

        self.data["daily_self_sufficiency_rate"] = (
            (
                self.data["daily_direct_energy_consumption"]
                + self.data["daily_battery_discharge_energy"]
            )
            / (
                self.data["daily_direct_energy_consumption"]
                + self.data["daily_battery_discharge_energy"]
                + self.data["daily_import_energy"]
            )
            * 100.0
        )

        self.data["total_self_sufficiency_rate"] = (
            (
                self.data["total_direct_energy_consumption"]
                + self.data["total_battery_discharge_energy"]
            )
            / (
                self.data["total_direct_energy_consumption"]
                + self.data["total_battery_discharge_energy"]
                + self.data["total_import_energy"]
            )
            * 100.0
        )

        return True

    def create_reg_residential_consumption(self):
        if not "daily_direct_energy_consumption" in self.data:
            return False
        if not "daily_battery_discharge_energy" in self.data:
            return False
        if not "daily_import_energy" in self.data:
            return False

        if not "total_direct_energy_consumption" in self.data:
            return False
        if not "total_battery_discharge_energy" in self.data:
            return False
        if not "total_import_energy" in self.data:
            return False

        self.data["daily_residential_consumption"] = (
            self.data["daily_direct_energy_consumption"]
            + self.data["daily_battery_discharge_energy"]
            + self.data["daily_import_energy"]
        )

        self.data["total_residential_consumption"] = (
            self.data["total_direct_energy_consumption"]
            + self.data["total_battery_discharge_energy"]
            + self.data["total_import_energy"]
        )

        return True

    def create_regs_power_flow(self):
        # power values for visualization in a graph displaying PV, Load,
        # Battery, and Grid. Every component is connected to each other with
        # one ower flow value between each pair of components.

        # fmt: off
        '''
              +--- PV ----+
             /      |      \
            /      (a)      \
           /        |        \
          /        Load       \
         +       /     \      +
         |      /       \     |
        (b)   (d)       (e)  (c)
         |    /           \   |
         Battery---(f)-----Grid
        '''
        # fmt: on.

        # The power flow registers are:
        # (a): flow_pv_to_load
        # (b): flow_pv_to_battery
        # (c): flow_pv_to_grid
        # (d): flow_battery_to_load
        # (e): flow_grid_to_load
        # (f): flow_battery_to_grid

        # Relevant invariants:
        # - (a), (b), (c) are possible in any combination.
        # - (a), (d), (e) are possible in any combination.
        # - (b) and (d) are mutually exclusive: The battery can only
        #   either charge or discharge.
        # - (c) and (e) are mutually exclusive: either power is imported
        #   or exported, not both.
        # - All values except (f) are always positive. when power flows
        #   form the grid into the battery, then (f) will be negative.
        #   This is not happening in regular operation, but limited to
        #   force load of the battery and similar situations.

        if not "load_power_hybrid" in self.data:
            return False
        if not "total_dc_power" in self.data:
            return False
        if not "battery_power_wide_range" in self.data:
            return False
        if not "export_power_hybrid" in self.data:
            return False

        # Load, always positive.
        load_power_hybrid = self.data["load_power_hybrid"]

        # PV power, always positive.
        total_dc_power = self.data["total_dc_power"]

        # Battery power can be positive (charging) or negative (discharging).
        # The inverter delivers this value in different registers.
        #battery_power = data["battery_power"]
        battery_power = self.data["battery_power_wide_range"]

        # Grid can be positive (export) or negative (import)
        export_power_hybrid = self.data["export_power_hybrid"]

        # Load will be taken with maximum priority from the PV System. The
        # power flow from PV to load is limited by total_dc_power.

        flow_pv_to_load = min(load_power_hybrid, total_dc_power)
        self.data["flow_pv_to_load"] = flow_pv_to_load

        # DC power unused by the load is used to load the battery with second
        # highest priority. This value cannot be higher that the battery power.

        flow_pv_to_battery = min(total_dc_power - flow_pv_to_load, battery_power)
        self.data["flow_pv_to_battery"] = flow_pv_to_battery

        # DC power is fed into the grid with lowest priority. This value is DC
        # power reduced by load and battery charge. The value cannot be higher
        # than the power reported at the grid connection.

        flow_pv_to_grid = min(total_dc_power - flow_pv_to_battery - flow_pv_to_load, export_power_hybrid)
        self.data["flow_pv_to_grid"] = flow_pv_to_grid

        # Load not covere4d by DC power is with first priority retrieved form
        # the battery. The value cannot be higher that the battery power. (The
        # battery could be empty or the required power may be limited by a
        # maximum discharge power.)

        flow_battery_to_load = min(load_power_hybrid - flow_pv_to_load, battery_power)
        self.data["flow_battery_to_load"] = flow_battery_to_load

        # If the load is still higher than DC power and battery discharge, the
        # gap is taken from the grid. The power taken from the grid cannot be
        # hogher than the power measured at the grid connection.

        flow_grid_to_load = min(load_power_hybrid - flow_pv_to_load - flow_battery_to_load, export_power_hybrid)
        self.data["flow_grid_to_load"] = flow_grid_to_load

        # The remaining power flow between battery and grid can happen when
        # calibrating or force loading the battery form the grid.

        # flow_battery_to_grid = flow_grid_to_load - flow_pv_to_grid - export_power_hybrid
        flow_battery_to_grid = flow_grid_to_load - flow_pv_to_grid - export_power_hybrid
        self.data["flow_battery_to_grid"] = flow_battery_to_grid

        return True
