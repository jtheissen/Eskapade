# **********************************************************************************
# * Project: Eskapade - A python-based package for data analysis                   *
# * Class  : ReadToDf                                                       *
# * Created: 2016/11/08                                                            *
# * Description:                                                                   *
# *      Algorithm to write pandas dataframes picked up from the datastore.        *
# *                                                                                *
# * Authors:                                                                       *
# *      KPMG Big Data team, Amstelveen, The Netherlands                           *
# *                                                                                *
# * Redistribution and use in source and binary forms, with or without             *
# * modification, are permitted according to the terms listed in the file          *
# * LICENSE.                                                                       *
# **********************************************************************************


import copy
import glob
import os
import pandas as pd
import numpy as np

import logging
log = logging.getLogger(__name__)

from eskapade import ProcessManager, Link, StatusCode, DataStore, ConfigObject

pd_readers = {'csv':    pd.read_csv,
              'tsv':    pd.read_csv,
              'xls':    pd.read_excel,
              'xlsx':   pd.read_excel,
              'json':   pd.read_json,
              'h5':     pd.read_hdf,
              'sql':    pd.read_sql,
              'htm':    pd.read_html,
              'html':   pd.read_html,
              'dta':    pd.read_stata,
              'pkl':    pd.read_pickle,
              'pickle': pd.read_pickle}


class ReadToDf(Link):
    """
    You give the link a path where your file is located and some kwargs that go into
    a pandas DataFrame. The kwargs are passed into the file reader.
    """

    def __init__(self, **kwargs):
        """
        Store the configuration of link ReadToDf

        :param str name: Name given to the link
        :param str path: path of your file to read into pandas DataFrame .
        :param str key: storage key for the DataStore.
        :param reader: pandas reader is determined automatically. But can be set by hand, e.g. csv, xlsx.
        :param bool itr_over_files: Iterate over individual files, default is false. If false, are files are collected in one dataframe. NB chunksize takes priority!
        :param int chunksize: Default is none. If positive integer then will always iterate. chunksize requires pd.read_csv or pd.read_table.
        :param kwargs: all other key word arguments are passed on to the pandas reader.
        """

        # initialize Link, pass name from kwargs
        Link.__init__(self, kwargs.pop('name', 'ReadToDf'))
        
        # process and register all relevant kwargs. kwargs are added as attributes of the link.
        # second arg is default value for an attribute. key is popped from kwargs.
        self._process_kwargs(kwargs, path='', key='', reader=None, itr_over_files=False, chunksize=None)
        
        # pass on remaining kwargs to pandas reader 
        self.kwargs = copy.deepcopy(kwargs)
        
        self._paths = None
        self._path_itr = None
        self._current_path = None
        self._latest_data_length = 0
        self._sum_data_length = 0
        self._iterate = False
        self._reader = None
        self._usecols = [] if 'usecols' not in self.kwargs else self.kwargs['usecols']
        
        return

    def setChunkSize(self, size):
        self.kwargs['chunksize'] = self.chunksize = size
        return

    def initialize(self):
        """ Initialize ReadToDf """

        assert isinstance(self.key, str) and len(self.key) > 0, 'output key not set.'
        assert isinstance(self._usecols, list), 'usecols not set correctly.'
        
        # construct and check list of file paths to read
        read_paths = [p for p in self.path] if not isinstance(self.path, str) else [self.path]
        if not read_paths:
            self.log().critical('no file path specified for %s instance "%s"', self.__class__.__name__, self.name)
            raise RuntimeError('no file path specified to read dataframe from file')
        if not all(isinstance(p, str) for p in read_paths):
            self.log().critical('not all paths for %s instance "%s" are strings', self.__class__.__name__, self.name)
            raise TypeError('file paths specified to read dataframe from file must be strings')

        # construct actual paths
        read_paths = [pe for p in read_paths for pe in glob.glob(p)]
        if not read_paths:
            self.log().critical('specified files not found for %s instance "%s"', self.__class__.__name__, self.name)
            raise RuntimeError('specified files not found')
        if not all(os.path.isfile(p) for p in read_paths):
            self.log().critical('not all paths for %s instance "%s" are files', self.__class__.__name__, self.name)
            raise RuntimeError('paths specified to read dataframe from file must be regular files')

        # set paths to read
        self._paths = np.array(read_paths)
        self._path_itr = np.nditer(self._paths)

        # now determine if file iterator will be used. Will iterate if:
        # 1. chunksize>0.
        if self.chunksize is not None:
            assert isinstance(self.chunksize, int) and self.chunksize > 0, 'chunksize needs to be set to positive integer.'
            self._iterate = True
        # 2. more than one file path has been set, and self.itr_over_files==True.
        elif len(self._paths)>1 and self.itr_over_files is True:
            self._iterate = True
        self.log().info('File and/or chunksize iterator is active: %s.' % self._iterate)
        if self.chunksize is not None:
            self.log().info('chunksize = %d. NB chunksize requires pd.read_csv or pd.read_table.' % self.chunksize)

        # add back chunksize if it was a kwarg, so it's picked up by pandas.
        if self.chunksize is not None:
            self.kwargs['chunksize'] = self.chunksize
            
        self.log().info('kwargs passed on to pandas reader are: %s' % self.kwargs )
        
        return StatusCode.Success

    
    def execute(self):
        """ Execute ReadToDf

        Reads the input file(s) and puts the dataframe in the datastore.
        """

        ds = ProcessManager().service(DataStore)
        settings = ProcessManager().service(ConfigObject)

        # 1. handle first the case of no iteration. Concatenate into one dataframe.
        if not self._iterate:
            self.log().debug('reading datasets from files [%s]', ', '.join('"%s"' % p for p in self._paths))
            df = pd.concat(pandasReader(p, self.reader, **self.kwargs) for p in self._paths)
            numentries = len(df.index)
        # 2. handle case where iteration has been turned on
        else:
            # try picking up new dataset from iterator
            df = next(self)
            while self.latest_data_length()==0 and not self.isFinished():
                df = next(self)

            # at end of loop
            if self.latest_data_length()==0:
                assert self.isFinished(), 'Got empty dataset but not at end of iterator. Thats weird. Exit.'
                # at end of loop, df == None.
                df = pd.DataFrame(columns = self._usecols)

            # do we have more datasets to go?
            # pass this information to the (possible) repeater at the end of chain
            reqstr = 'chainRepeatRequestBy_'+self.name
            settings[reqstr] = True if not self.isFinished() else False

            numentries = self.latest_data_length()
            sumentries = self.sum_data_length()
            self.log().info('Read next <%d> records; summing up to <%d>.' % (numentries,sumentries) )
            ds['n_sum_'+self.key] = sumentries
            pass
        
        # store dataframe and number of entries
        ds[self.key] = df
        ds['n_'+self.key] = numentries
        
        return StatusCode.Success

    def isFinished(self):
        """ 
        Try to assess if looper is done iterating over files. 

        Assess if looper is done or if a next dataset is still coming up.
        """
        finished = self._path_itr.finished
        if isinstance(self.chunksize,int) and self.chunksize > 0:
            finished &= (self._latest_data_length < self.chunksize)
        return finished

    def __next__(self):
        """ 
        Pass up the next dataset in the loop. 

        Next file is either a entire file or a file chunk.
        Bookkeeping is kept uptodate.
        """
        data = self._next()

        # bookkeeping
        try:
            self._latest_data_length = len(data.index)
        except: 
            self._latest_data_length = 0
        self._sum_data_length += self._latest_data_length
            
        return data

    def latest_data_length(self):
        """ Return length of current dataset """
        return self._latest_data_length
    
    def sum_data_length(self):
        """ Return sum length of all datasets processed sofar """
        return self._sum_data_length

    def _next(self):
        """ 
        Pass up the next dataset in the loop. 

        This is either a entire file or a file chunk.
        """
        data = None

        # 1. input file has already been set (in previous cycle),
        #    and this is still used for chunking.
        if self._reader!=None and isinstance(self._reader,pd.io.parsers.TextFileReader):        
            try:
                data = next(self._reader)
                return data
            except StopIteration:
                # TextFileReader throws stopiterator exception at end
                data = None
            except:
                #import sys
                #print 'Unexpected error' #: %s" % sys.exc_info()[0]
                raise 'Unexpected error: cannot process next dataset iteration. Exit.'
            pass

        # 2. trying next file
        # data is still None, setting up a new reader
        if not self._path_itr.finished:
            path = str(self._path_itr[0])
            self._path_itr.iternext()
            try:
                self._reader = pandasReader(path, self.reader, **self.kwargs) 
            except:
                self.log().critical('Could not read from new path <%s>' % path)
                raise 
            self._current_path = path
            self.log().info('Opened new file [%s]' % self._current_path)
        else:
            # no new files left to open
            # (data is still None)
            return data

        # 3. new reader has been set up
        # trying the new reader 
        if isinstance(self._reader,pd.core.frame.DataFrame):
            # chunksize not provided, so not chunking.
            data = self._reader
            # resetting the reader for next itr
            self._reader = None
        elif isinstance(self._reader,pd.io.parsers.TextFileReader):        
            try:
                data = next(self._reader)
            except StopIteration:
                # TextFileReader throws stopiterator exception at end
                data = None
            except:
                raise 'Unexpected error: cannot process next dataset iteration. Exit.'
            pass
            
        return data
    

def pandasReader(path, reader, *args, **kwargs):
    """ 
    Pick the correct pandas reader.

    Based on provided reader setting, or based on file extension.
    """
    if not reader:
        reader = pd_readers.get(os.path.splitext(path)[1].strip('.'), None)
    if not reader:
        log.critical('no suitable reader found for file "%s"', path)
        raise RuntimeError('unable to find suitable Pandas reader')
    log.debug('using Pandas reader "%s"', str(reader))
    # If the reader is input as 'csv' by hand, use the lookup, else use the specified reader (as pd.read_X)
    reader = pd_readers.get(reader) if isinstance(reader, str) else reader
    return reader(path, *args, **kwargs)
