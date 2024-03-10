#!/usr/bin/python3

import logging

from datetime import datetime
from datetime import date

"""
    fm = FieldPostProcessor(config_filename="xf.yaml")
    #fm = FieldPostProcessor(config=[{'field': 'load_doubled', 'expression': 'load_power_hybrid * 2'}])

    fm.evaluate({'export_to_grid': 1000, 'meter_power': 100, 'total_active_power': 200, 'work_state_1': 'Run', 'start_stop': 'False', 'year': 2024, 'month': 2, 'day': 23, 'hour': 10, 'minute': 12, 'second': 44})
    time.sleep(10)

    fm.evaluate({'export_to_grid': 1000, 'meter_power': 100, 'total_active_power': 200, 'work_state_1': 'Run', 'start_stop': 'Fe'})
    time.sleep(10)

    fm.evaluate({'export_to_grid': 1000, 'meter_power': 100, 'total_active_power': 200})
    time.sleep(10)
"""


class AbstractCode:
    # This class is the common ancestor for all classes representing
    # expressions and statements.  It should not be instantiated.

    def __init__(self, name, source, unit=None):
        # All kinds of AbstractCode objects have a name. The name is always
        # used as a field name.
        self.name = name

        # The source of the code fragment.
        self.source = source

        # The compiled code fragment - or None if compiling failed. The code
        # will be compiled on initialization, so it is possible to log any
        # errors early on startup, not later, when data is retrieved. Also
        # using precompiled code executes much faster - although this should
        # not be an issue with a few custom field definitions ...
        self.code = self.compile(self.source, self.name)

        # Strictly optional and not used in this module, the unit is a String
        # indicating how to interpret the value of the field, for example "kWh"
        # or "seconds".
        self.unit = unit

    def evaluate(self, values):
        # Evaluate the expression or statement represented by the receiver. Any
        # variables referenced by the source must be provided in the values
        # dictionary.

        # Return the result of the evaluation if any, None if evaluation fails.

        # Calls to evaluate() can safely be made, even if the compilation
        # failed. This will not cause errors, however it will of course not
        # yield any results.
        if self.code is None:
            return None

        try:
            return self.do_evaluate(values)
        except Exception as error:
            # Typically a NameError, when a field is not available in the
            # values dictionary. This is not considered an error, rather a
            # warning, because not all fields are always required to be
            # available in the result.  every time. So this is logged at level
            # INFO.
            logging.warning(f"Entry ´{self.name}` not evaluated: {error}.")
            return self.do_fallback(values)
        return None

    def do_evaluate(self, values):
        # The behavior is defined by subclasses.
        pass

    def do_fallback(self, values):
        # Do whatever should happen as a fallback if and only if do_evaluate()
        # fails with an exception. By default return None, intended to be
        # overwritten by subclasses.
        return None

    def get_source_kind(self):
        # Return either "eval" or "exec" to indicate whether the source is an
        # expression or statement respectively. The behavior is defined by
        # subclasses.
        pass

    def as_list_entry(self):
        entry = {"name": self.name}
        if self.unit is not None:
            entry["unit"] = self.unit
        return entry

    def compile(self, source, name):
        # Compile the source and return the compiled code object.  The name
        # parameter is used for logging only. Any excection during compilation
        # is logged including the stack trace. This is the easiest way to debug
        # syntactically wrong statements.
        res = None
        try:
            res = compile(source, "<string>", self.get_source_kind())
            logging.debug(f"Compiled ´{source}` for entry ´{name}`.")
        except Exception:
            # SyntaxError: The source was syntactically wrong. ValueError: The
            # source may contain null bytes. TypeError: Also possible.
            logging.exception(f"Failed compiling ´{source}` for entry ´{name}`.")
        return res


class FieldStatement(AbstractCode):
    # This class represents a block of arbitrary code - technically a statement
    # (in contrast to an expression). It is intended to store one or more custom
    # field values into the results, but the scope is not limited to this.

    def __init__(self, name, statement, unit=None):
        super().__init__(name, statement, unit=unit)

        # This dictionary may be used in statements to store key value pairs
        # which are available in a later evaluation. Its values are preserved
        # between calls. This variable is added to the global scope of the
        # exec() call with the name ´previous_results`.
        self.previous_results = {}

    def get_source_kind(self):
        return "exec"

    def do_evaluate(self, values):
        # The values dictionary is added to the global scope with the name
        # ´results`. The code fragment is responsible to store any relevant
        # results into this dictionary.

        # Add some libraries in addition to the builtins (which are
        # automatically added) into the global dictionary.

        return exec(
            self.code,
            {
                "results": values,
                "previous_results": self.previous_results,
                "datetime": datetime,
                **values,
            },
        )


class SimpleExpression(AbstractCode):
    def get_source_kind(self):
        return "eval"

    # Simply evaluate the expression and return the result.
    def do_evaluate(self, values):
        return eval(
            self.code,
            {
                "datetime": datetime,
                **values,
            },
        )


class FieldExpression(SimpleExpression):
    # This class represents a python expression for calculating a named custom
    # field. The source is required to return a value. FieldExpression
    # instances use the name attribute to store the entries in the values
    # dictionary after evaluation.

    # A FieldExpression has access to the current values of the data retrieved
    # from the inverter during the last read operation.

    def __init__(
        self,
        field,
        expression,
        guard_expression=None,
        write_mode=None,
        fallback_expression=None,
        unit=None,
    ):
        super().__init__(field, expression, unit=unit)

        # A write_mode of "replace_only" will only write a value, if a value
        # with that name already exists. The write_mode of "new_only" will
        # write a result only, if a value with that name does not yet exist. A
        # write_mode of None will write the result in any case. None is
        # the default.
        self.write_mode = write_mode

        self.guard = None
        if guard_expression is not None:
            self.guard = GuardExpression(field, guard_expression)

        self.fallback = None
        if fallback_expression is not None:
            self.fallback = SimpleExpression(field, fallback_expression)

    def write_mode_allows_writing(self, values):
        # Return True if the receiver should evaluate and write a result.
        if self.write_mode is None:
            return True
        if self.write_mode == "replace_only":
            # True if the value already exists:
            return values.get(self.name) is not None
        if self.write_mode == "new_only":
            # True if the value does not yet exist:
            return values.get(self.name) is None
        return False

    def do_evaluate(self, values):
        if self.guard and not self.guard.evaluate(values):
            return None
        if self.write_mode_allows_writing(values):
            result = eval(
                self.code,
                {
                    "datetime": datetime,
                    **values,
                },
            )
            values[self.name] = result
            return result
        return None

    def do_fallback(self, values):
        if self.fallback is not None:
            logging.debug(f"evaluating fallback for ´{self.name}` ...")
            fallback_result = self.fallback.evaluate(values)
            if fallback_result is not None:
                values[self.name] = fallback_result
                return fallback_result
        else:
            logging.debug(f"no fallback for ´{self.name}` ...")
        return None


class AggregatingFieldExpression(FieldExpression):
    # This class will add the values calculated by its expression to a running
    # total. This can optionally be reset on a daily basis resulting in daily
    # aggregated values. If the running value is not reset, it results in an
    # aggregation in total.  Rationale: The inverter delivers many energy
    # values for either the current day or as a total value by default. To
    # mimic this behavior for own fields these will as well either be
    # aggregated on a daily basis or in total.

    # Limitations: This class can only handle numeric values. Also it only
    # aggregates, other mathematical operations (like a running average etc.)
    # are not possible.

    def __init__(
        self,
        field,
        expression,
        aggregation_mode,
        guard_expression=None,
        write_mode=None,
        fallback_expression=None,
        unit=None,
    ):
        super().__init__(
            field,
            expression,
            guard_expression=guard_expression,
            write_mode=write_mode,
            fallback_expression=fallback_expression,
            unit=unit,
        )

        # Remember the previous value to make it available when evaluating the
        # receiver. This is always a numeric value, the default is 0.
        self.previous_value = 0

        # The timestamp of the last update of the previous value. This allows
        # to build integral values by integrating over time. To guarantee that
        # this is always a valid value on initialization it is assumed to be
        # 0:00:00 on the current day.
        self.last_update = datetime.combine(date.today(), datetime.min.time())

        # Indicate whether the previous value will be reset to 0 on a daily
        # basis.
        self.reset_daily = aggregation_mode == "daily"

    def seconds_since_last_update(self):
        # Return the number of seconds since self.last_update. This method is
        # made available to the local scope in evaluation of the receiver, so
        # that expressions can use it.
        return (datetime.now() - self.last_update).total_seconds()

    def do_evaluate(self, values):
        # reset self.previous_value to 0 if the last update was yesterday and
        # daily reset is configured.
        if self.guard and not self.guard.evaluate(values):
            return None
        self.reset_previous_value_if_required()
        # Now evaluate the receiver
        result = eval(
            self.code,
            {
                "datetime": datetime,
                **values,
            },
            {
                "seconds_since_last_update": self.seconds_since_last_update,
            },
        )
        # store result by adding to the previous result:
        values[self.name] = self.previous_value + result
        # remember value and timestamp for next evaluation:
        self.previous_value = self.previous_value + result
        self.last_update = datetime.now()

    def reset_previous_value_if_required(self):
        last_update_was_yesterday = datetime.now().date() > self.last_update.date()
        if self.reset_daily and last_update_was_yesterday:
            self.previous_value = 0


class GuardExpression(SimpleExpression):
    # This class is an extension of SimpleExpression and will return False on
    # evaluation instead of None even if the execution fails, thereby providing
    # a fail safe behavior.

    def do_evaluate(self, values):
        try:
            return eval(
                self.code,
                {
                    "datetime": datetime,
                    **values,
                },
            )
        except Exception as error:
            logging.warning(f"Guard expression ´{self.name}` not evaluated: {error}.")
            return False


class CodeObjectFactory:
    # The responsibility of this class is to create an instance of a suitable
    # class for a custom field definition entry. It has only one class method.
    # Instantiation of this class is not required.

    def __init__(self):
        pass

    @classmethod
    def create(cls, config):
        name = config.get("name")
        expr = config.get("expression")
        stmt = config.get("statement")
        guard = config.get("guard")
        aggr = config.get("aggregate")
        wrtm = config.get("write_mode")
        flbk = config.get("fallback")
        unit = config.get("unit")
        ignore_msg = f"Ingnored config entry ´{config}`: "
        if name is None:
            logging.error(ignore_msg + "name is required.")
            return None
        if stmt:
            if guard or wrtm or aggr or expr or flbk:
                logging.error(
                    ignore_msg
                    + "guard, expression, aggregate, write_mode, fallback not allowed in combination with statement."
                )
                return None
            else:
                return FieldStatement(
                    name,
                    stmt,
                    unit=unit,
                )
        elif expr:
            if aggr and aggr not in ["daily", "total"]:
                logging.error(
                    ignore_msg + "aggregation must be one of ´daily` or ´total`."
                )
                return None
            if wrtm and wrtm not in ["replace_only", "new_only"]:
                logging.error(
                    ignore_msg + " write_mode must be ´replace_only` or ´new_only`."
                )
                return None
            if aggr:
                return AggregatingFieldExpression(
                    name,
                    expr,
                    aggr,
                    guard_expression=guard,
                    write_mode=wrtm,
                    fallback_expression=flbk,
                    unit=unit,
                )
            else:
                return FieldExpression(
                    name,
                    expr,
                    guard_expression=guard,
                    write_mode=wrtm,
                    fallback_expression=flbk,
                    unit=unit,
                )
        else:
            logging.error(ignore_msg + "expression or statement required.")
            return None


class FieldPostProcessor:
    def __init__(self, cf_definitions):
        self.expressions = []
        if cf_definitions is not None:
            # Initialize list of code objects to evaluate.
            for cf in cf_definitions:
                co = CodeObjectFactory.create(cf)
                if co is not None:
                    self.expressions.append(co)
        if len(self.expressions) == 0:
            logging.info("No custom fields configured.")

    def evaluate(self, values):
        # Calculate all expressions using the values and storing the results in values.
        logging.info("Start evaluating custom field definitions ...")
        for e in self.expressions:
            e.evaluate(values)
        logging.info("... finished evaluating custom field definitions.")
        logging.debug(f"values after evaluating custom field definitions: {values}")

    def get_field_list(self):
        the_list = []
        for e in self.expressions:
            the_list.append(e.as_list_entry())
        return the_list
