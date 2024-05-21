"""
Tools for crafting models.
"""

from dataclasses import dataclass, field
from HARK.distribution import Distribution
from inspect import signature
import numpy as np
from typing import Any, Callable, Mapping, List, Union


class Aggregate:
    """
    Used to designate a shock as an aggregate shock.
    If so designated, draws from the shock will be scalar rather
    than array valued.
    """

    def __init__(self, dist: Distribution):
        self.dist = dist


class Control:
    """
    Used to designate a variabel that is a control variable.

    Parameters
    ----------
    args : list of str
        The labels of the variables that are in the information set of this control.
    """

    def __init__(self, args):
        pass


def simulate_dynamics(
    dynamics: Mapping[str, Union[Callable, Control]],
    pre: Mapping[str, Any],
    dr: Mapping[str, Callable],
):
    """
    From the beginning-of-period state (pre), follow the dynamics,
    including any decision rules, to compute the end-of-period state.

    Parameters
    ------------

    dynamics: Mapping[str, Callable]
        Maps variable names to functions from variables to values.
        Can include Controls
        ## TODO: Make collection of equations into a named type


    pre : Mapping[str, Any]
        Bound values for all variables that must be known before beginning the period's dynamics.


    dr : Mapping[str, Callable]
        Decision rules for all the Control variables in the dynamics.
    """
    vals = pre.copy()

    for varn in dynamics:
        # Using the fact that Python dictionaries are ordered

        feq = dynamics[varn]

        if isinstance(feq, Control):
            # This tests if the decision rule is age varying.
            # If it is, this will be a vector with the decision rule for each agent.
            if isinstance(dr[varn], np.ndarray):
                ## Now we have to loop through each agent, and apply the decision rule.
                ## This is quite slow.
                for i in range(dr[varn].size):
                    vals_i = {
                        var: vals[var][i]
                        if isinstance(vals[var], np.ndarray)
                        else vals[var]
                        for var in vals
                    }
                    vals[varn][i] = dr[varn][i](
                        *[vals_i[var] for var in signature(dr[varn][i]).parameters]
                    )
            else:
                vals[varn] = dr[varn](
                    *[vals[var] for var in signature(dr[varn]).parameters]
                )  # TODO: test for signature match with Control
        else:
            vals[varn] = feq(*[vals[var] for var in signature(feq).parameters])

    return vals


@dataclass
class DBlock:
    """
    Represents a 'block' of model behavior.
    It prioritizes a representation of the dynamics of the block.
    Control variables are designated by the appropriate dynamic rule.

    Parameters
    ----------
    ...
    """

    name: str = ""
    description: str = ""
    shocks: dict = field(default_factory=dict)
    dynamics: dict = field(default_factory=dict)
    reward: dict = field(default_factory=dict)

    def get_shocks(self):
        return self.shocks

    def get_dynamics(self):
        return self.dynamics

    def get_vars(self):
        return list(self.shocks.keys()) + list(self.dynamics.keys())

    def transition(self, pre, dr):
        """
        Returns variable values given previous values and decision rule for all controls.
        """
        return simulate_dynamics(self.dynamics, pre, dr)

    def calc_reward(self, vals):
        """
        Computes the reward for a given set of variable values
        """
        rvals = {}

        for varn in self.reward:
            feq = self.reward[varn]
            rvals[varn] = feq(*[vals[var] for var in signature(feq).parameters])

        return rvals

    def state_action_value_function_from_continuation(self, continuation):
        def state_action_value(pre, dr):
            vals = self.transition(pre, dr)
            r = list(self.calc_reward(vals).values())[0]  # a hack; to be improved
            cv = continuation(
                *[vals[var] for var in signature(continuation).parameters]
            )

            return r + cv

        return state_action_value

    def decision_value_function(self, dr, continuation):
        savf = self.state_action_value_function_from_continuation(continuation)

        def decision_value_function(pre):
            return savf(pre, dr)

        return decision_value_function

    # def arrival_value_function(self, dr, continuation):
    #    """
    #    Value of arrival states, prior to shocks, given a decision rule and continuation.
    #    """
    #    def arrival_value(arvs):
    #        dvf = self.decision_value_function(dr, continuation)
    #
    #        ##TOD: Take expectation over shocks!!!
    #        return EXPECTATION(dvf, shock_vals, arrv)


@dataclass
class RBlock:
    """
    A recursive block.

    Parameters
    ----------
    ...
    """

    name: str = ""
    description: str = ""
    blocks: List[DBlock] = field(default_factory=list)

    def get_shocks(self):
        ### TODO: Bug in here is causing AttributeError: 'set' object has no attribute 'draw'

        super_shocks = {}  # uses set to avoid duplicates

        for b in self.blocks:
            for k, v in b.get_shocks().items():  # use d.iteritems() in python 2
                super_shocks[k] = v

        return super_shocks

    def get_dynamics(self):
        super_dyn = {}  # uses set to avoid duplicates

        for b in self.blocks:
            for k, v in b.get_dynamics().items():  # use d.iteritems() in python 2
                super_dyn[k] = v

        return super_dyn

    def get_vars(self):
        return list(self.get_shocks().keys()) + list(self.get_dynamics().keys())
