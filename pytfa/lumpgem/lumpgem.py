#!/usr/bin/env python
# -*- coding: utf-8 -*-

from io.base import import_matlab_model, load_thermoDB

from optim.variables import BinaryVariable
from thermo.tmodel import ThermoModel

CPLEX = 'optlang-cplex'
GUROBI = 'optlang-gurobi'
GLPK = 'optlang-glpk'


class LumpGEM:
    """
    A class encapsulating the LumpGEM algorithm
    """
    def __init__(self, GEM, biomass_rxns, core_subsystems, carbon_uptake, growth_rate,  thermo_data_path):
        """
        : param GEM: the GEM 
        : type GEM: cobra model

        : param biomass_rxns: list of biomass reactions
        : type biomass_rxns: [GEM.biomass_rxn.id]

        : param core_subsystems: list of Core subsystems
        : type core_subsytems: [[model.reactions]]

        : param carbon_intake: the amount of carbon atoms the cell intakes from its surrounding
        : type carbon_intake: float

        : param thermo_data_path: the path to the .thermodb database
        : type thermo_data_path : string
        """

        self._GEM = GEM

        # Extracting all reactions that lead to BBB
        self._rBBB = set([rxn for rxn in GEM.reactions if rxn.id in biomass_rxns])

        # Set containing every core reaction
        self._rcore = set([])
        # Set containing every core metabolite
        self._mcore = set([])
        for subsystem in core_subsystems:
            for rxn in subsystem:
                # Add rxn to core reactions
                self._rcore.add(rxn)
                # Add involved metabolites to core metabolites
                for met in rxn.metabolites:
                    self._mcore.add(met)

        # Non core reactions
        self._rncore = set([rxn for rxn in GEM.reactions if not (rxn in self._rcore or rxn in self._rBBB)])

        # Carbon uptake
        self._C_uptake = carbon_uptake
        # Growth rate
        self._growth_rate = growth_rate

        # TODO : solver choice
        self._solver = 'optlang-cplex'

        # TODO put correct path here
        self._cobra_model = import_matlab_model("..")
        # Build thermo model
        self._tfa_model = self._apply_thermo_constraints(thermo_data_path, self._cobra_model)

        self._bin_vars = self._generate_binary_variables()
        self._generate_constraints()

    def _generate_binary_variables(self):
        """
        Generate binary variables for each non-core reaction
        """
        # TODO Check the correct construction of variables
        return {rxn: BinaryVariable(name=rxn.id, type='binary') for rxn in self._rncore}

    def _generate_constraints(self):
        """
        Generate carbon intake related constraints for each non-core reaction and 
        growth rate related constraints for each BBB reaction
        """
        # Carbon intake constraints
        for rxn in self._rncore:
            # rxn constrained according to the carbon uptake
            rxn_const = self._tfa_model.problem.Constraint(rxn.forward_variable +
                                                           rxn.reverse_variable +
                                                           self._C_uptake * self._bin_vars[rxn], ub=self._C_uptake)
            self._tfa_model.add_cons_vars(rxn_const)

        # Growth rate constraints
        for bio_rxn in self._rBBB:
            bio_rxn.lower_bound = self._growth_rate

    def _apply_thermo_constraints(self, thermo_data_path, cobra_model):
        """
        Apply thermodynamics constraints defined in thermoDB to Mcore & Rcore
        """
        thermo_data = load_thermoDB(thermo_data_path)
        tfa_model = ThermoModel(thermo_data, cobra_model)
        tfa_model.name = 'Lumped Model'

        # TODO : Check what are these operations for
        # self.read_lexicon = read_lexicon()
        # compartment_data = read_compartment_data()
        # annotate_from_lexicon(tfa_model, lexicon)
        # apply_compartment_data(tfa_model, compartment_data)

        # TODO : Correct use of model.objective ? How to choose coeff (here 1.0) ?
        # The objective is to max all BBB reactions, right ?
        tfa_model.objective = {bbb_rxn: 1.0 for bbb_rxn in self._rBBB}

        return tfa_model

    def run_optimisation(self):
        self._tfa_model.prepare()

        # Deactivate tfa computation for non-core reactions
        for ncrxn in self._rncore:
            ncrxn.thermo['computed'] = False

        self._tfa_model.convert()

        tfa_solution = self._tfa_model.optimize()
        return tfa_solution