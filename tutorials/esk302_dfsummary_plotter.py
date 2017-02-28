# **********************************************************************************
# * Project: Eskapade - A python-based package for data analysis                   *
# * Macro  : esk302_dfsummary_plotter                                              *
# * Created: 2017/02/23                                                            *
# * Description:                                                                   *
# *      Macro shows how to plot the content of a dataframe in a nice summary
# *      pdf file.
# *      (Example similar to tutorial_1)
# *                                                                                *
# *                                                                                *
# * Redistribution and use in source and binary forms, with or without             *
# * modification, are permitted according to the terms listed in the file          *
# * LICENSE.                                                                       *
# **********************************************************************************

import logging
log = logging.getLogger('macro.esk302_dfsummary_plotter')

import tempfile
from eskapade import ConfigObject, ProcessManager
from eskapade import core_ops, analysis, visualization
import pandas as pd

log.debug('Now parsing configuration file esk302_dfsummary_plotter')

#########################################################################################
# --- minimal analysis information

settings = ProcessManager().service(ConfigObject)
settings['analysisName'] = 'esk302_dfsummary_plotter'
settings['version'] = 0

#########################################################################################
# --- Analysis values, settings, helper functions, configuration flags.

msg = r"""

The plots and latex files produced by link df_summary can be found in dir:
%s
""" % (settings['resultsDir'] + '/' + settings['analysisName'] + '/data/v0/report/')
log.info(msg)

COLUMNS = ['var_a', 'var_b', 'var_c']
SIZE = 10000
VAR_LABELS = dict(var_a='Variable A', var_b='Variable B', var_c='Variable C')
VAR_UNITS = dict(var_b='m/s')
GEN_CONF = dict(var_b=dict(mean=42., std=2.), var_c=dict(mean=42, std=2, dtype=int))

#########################################################################################
# --- now set up the chains and links based on configuration flags

# create process manager
proc_mgr = ProcessManager()

# create chains
proc_mgr.add_chain('Data')
proc_mgr.add_chain('Summary')

# add data-generator link to "Data" chain
generator = analysis.BasicGenerator(name='Generate_data',
                                    key='data',
                                    columns=COLUMNS,
                                    size=SIZE,
                                    gen_config=GEN_CONF)
proc_mgr.get_chain('Data').add_link(generator)

# add data-frame summary link to "Summary" chain
# can provide labels and units for the variables in the dataset
summarizer = visualization.DfSummary(name='Create_stats_overview',
                                     read_key=generator.key,
                                     var_labels=VAR_LABELS,
                                     var_units=VAR_UNITS)
proc_mgr.get_chain('Summary').add_link(summarizer)

#########################################################################################

log.debug('Done parsing configuration file esk302_dfsummary_plotter')
