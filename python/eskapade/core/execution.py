# **********************************************************************************
# * Project: Eskapade - A python-based package for data analysis                   *
# * Created: 2016/11/08                                                            *
# * Description:                                                                   *
# *      Functions for running and resetting Eskapade machinery                    *
# *                                                                                *
# * Authors:                                                                       *
# *      KPMG Big Data team, Amstelveen, The Netherlands                           *
# *                                                                                *
# * Redistribution and use in source and binary forms, with or without             *
# * modification, are permitted according to the terms listed in the file          *
# * LICENSE.                                                                       *
# **********************************************************************************

import sys
import logging
import cProfile
import pstats
import io

import eskapade.utils
from .process_manager import ProcessManager
from .process_services import ConfigObject

proc_mgr = ProcessManager()


def reset_eskapade(skip_config=False):
    """Reset Eskapade objects

    :param bool skip_config: skip reset of configuration object
    """

    settings = proc_mgr.service(ConfigObject)
    proc_mgr.reset()
    if skip_config:
        proc_mgr.service(settings)


def run_eskapade(settings=None):
    """Run Eskapade

    This function is called in the script scripts/run_eskapade.py when run
    from the cmd line.  The working principle of Eskapade is to run chains of
    custom code chunks (so-called links).

    Each chain should have a specific purpose, for example pre-processing
    incoming data, booking and/or training predictive algorithms, validating
    these predictive algorithms, evaluating the algorithms.

    By using this principle, links can be easily reused in future projects.

    :param ConfigObject settings: analysis settings
    :return: status of the execution
    :rtype: StatusCode
    """

    # get config object from process manager
    if settings:
        # use supplied settings as config service in process manager
        proc_mgr.remove_service(ConfigObject, silent=True)
        proc_mgr.service(settings)
    settings = proc_mgr.service(ConfigObject)

    # initialize logging
    logging.basicConfig(level=settings['logLevel'], format=settings.get(
        'logFormat', '%(asctime)s %(levelname)s [%(module)s/%(funcName)s]: %(message)s'))
    log = logging.getLogger(__name__)
    log.info('\n\n * * * Welcome to Eskapade * * *\n')

    # check for batch mode
    if settings.get('batchMode'):
        # set non-interactive Matplotlib backend before plotting tools are imported
        eskapade.utils.set_matplotlib_backend(batch=True, silent=False)

    # execute configuration macro, this sets up the order of the chains and links.
    if not settings['macro']:
        raise RuntimeError('macro is not set')
    proc_mgr.execute_macro(settings['macro'])

    if 'ROOT.RooFit' in sys.modules:
        # initialize logging for RooFit
        from eskapade.root_analysis.roofit_utils import set_rf_log_level
        set_rf_log_level(settings['logLevel'])

    # check analysis name
    if not settings['analysisName']:
        raise RuntimeError('analysis name is not set')

    # standard execution from now on

    # initialize
    status = proc_mgr.initialize()
    if status.isFailure():
        return status

    if settings.get('doCodeProfiling'):
        # turn on profiling
        profiler = cProfile.Profile()
        profiler.enable()

    # run Eskapade
    status = proc_mgr.execute_all()

    if settings.get('doCodeProfiling'):
        # turn off profiling
        profiler.disable()

        # print profile output
        profile_output = io.StringIO()
        profile_stats = pstats.Stats(profiler, stream=profile_output).sort_stats(settings['doCodeProfiling'])
        profile_stats.print_stats()
        print(profile_output.getvalue())

    # check execution return code
    if status.isFailure():
        return status

    # finalization and storage()
    status = proc_mgr.finalize()
    if status.isFailure():
        return status

    log.info('\n\n * * * Leaving Eskapade. Bye! * * *\n')

    return status
