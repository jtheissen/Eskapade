# **********************************************************************************
# * Project: Eskapade - A python-based package for data analysis                   *
# * Class  : RecordVectorizer                                                      *
# * Created: 2016/11/08                                                            *
# * Description:                                                                   *
# *      Algorithm to perform the vectorization of an input column
# *      of an input dataframe.
# *                                                                                *
# * Authors:                                                                       *
# *      KPMG Big Data team, Amstelveen, The Netherlands                           *
# *                                                                                *
# * Redistribution and use in source and binary forms, with or without             *
# * modification, are permitted according to the terms listed in the file          *
# * LICENSE.                                                                       *
# **********************************************************************************

import pandas as pd
from pandas import DataFrame
from functools import reduce

from eskapade import ProcessManager, Link, StatusCode, DataStore


class RecordVectorizer(Link):
    """Vectorize data-frame columns

    Perform vectorization of input column of an input dataframe.  E.g. a
    columnn x with values 1, 2 is tranformed into columns x_1 and x_2, with
    values True or False assigned per record.
    """

    def __init__(self, **kwargs):
        """Initialize RecordVectorizer instance

        Store and do basic check on the attributes of link RecordVectorizer.

        :param str read_key: key to read dataframe from the data store. Dataframe of records that is to be transformed.
        :param list columns: list of columns that are to be vectorized
        :param str store_key: store key of output dataFrame. Default is read_key + '_vectorized'. (optional)
        :param dict column_compare_with: dict of unique items per column with which column values are compared.
               If not given, this is derived automatically from the column. (optional)
        :param type astype: store answer of comparison of column with value as certain type. Default is bool. (optional)
        """

        Link.__init__(self, kwargs.pop('name', 'RecordVectorizer'))

        # process and register all relevant kwargs. kwargs are added as attributes of the link.
        # second arg is default value for an attribute. key is popped from kwargs.
        self._process_kwargs(kwargs,
                             read_key='',
                             store_key=None,
                             columns=[],
                             column_compare_with={},
                             astype=bool)

        # check residual kwargs. exit if any present
        self.check_extra_kwargs(kwargs)

    def initialize(self):
        """Initialize RecordVectorizer

        Initialize and (further) check the assigned attributes of
        RecordVectorizer.
        """

        self.check_arg_types(read_key=str)
        self.check_arg_types(recurse=True, allow_none=True, columns=str)
        self.check_arg_vals('read_key')

        if self.store_key is None:
            self.store_key = self.read_key + '_vectorized'
            self.log().info('Store key was empty, has been set to "%s"', self.store_key)

        return StatusCode.Success

    def execute(self):
        """Execute RecordVectorizer

        Perform vectorization input column 'column' of input dataframe.
        Resulting dataset stored as new dataset.
        """

        ds = ProcessManager().service(DataStore)

        # basic checks on contensts of the data frame
        if self.read_key not in ds:
            raise KeyError('key "%s" not in data store' % self.read_key)
        df = ds[self.read_key]
        if not isinstance(df, DataFrame):
            raise TypeError('retrieved object not of type pandas DataFrame')
        if len(df.index) == 0:
            raise AssertionError('dataframe "%s" is empty' % self.read_key)
        for c in self.columns:
            if c not in df.columns:
                raise AssertionError('column "%s" not present in input data frame' % c)

        # checks of column_compare_with
        if isinstance(self.column_compare_with, str) and len(self.column_compare_with):
            if self.column_compare_with not in ds:
                raise KeyError('column compare with "%s" not found in data store' % self.column_compare_with)
            self.column_compare_with = df[self.column_compare_with]
        if not isinstance(self.column_compare_with, dict):
            raise RuntimeError('column compare dict not set correctly')
        for c in self.columns:
            if c not in self.column_compare_with:
                self.column_compare_with[c] = df[c].unique()
            elif not isinstance(self.column_compare_with[c], list):
                raise TypeError('column "%s" needs to be compared with list of values' % c)

        # do vectorization for all columns, then merge
        dfs = [record_vectorizer(df, c, self.column_compare_with[c], self.astype) for c in self.columns]
        df_final = reduce(lambda left, right: pd.merge(left, right, left_index=True, right_index=True), dfs)

        ds[self.store_key] = df_final

        return StatusCode.Success


def record_vectorizer(df, column_to_vectorize, column_compare_set, astype=bool):
    """Vectorize data-frame column

    Takes the new record that is already transformed and vectorizes the
    given columns.

    :param df: dataframe of the new record to vectorize
    :param str column_to_vectorize: string, column in the new record to vectorize.
    :param list column_compare_set: list of values to compare the column with.
    :returns: dataframe of the new records.
    """

    dfNew = pd.DataFrame(index=df.index)
    for val in column_compare_set:
        newcol = column_to_vectorize + '_' + str(val)
        dfNew[newcol] = (df[column_to_vectorize] == val).astype(astype)

    return dfNew
