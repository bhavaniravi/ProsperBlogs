"""pandas_zkb_test.py: demo script for timing/testing pandas data transformations"""

from os import path, makedirs
import json
from datetime import datetime
import math
import warnings

from contexttimer import Timer
from plumbum import cli
import pandas as pd
import numpy as np
import requests

HERE = path.abspath(path.dirname(__file__))

DICT_KEYS = ['victim', 'position', 'zkb']
LIST_KEYS = ['attackers', 'items']
DATA_KEYS = ['killID', 'solarSystemID', 'killTime', 'moonID']

ZKB_URI = 'https://zkillboard.com/api/'
ZKB_CACHE_FILE = 'zkb_cache.json'
def fetch_zkb_data(
        zkb_query,
        kill_counts,
        zkb_uri=ZKB_URI,
        kills_per_request=200,
        dump_path=HERE
):
    """fetches raw list data from zkillboard.com

    Notes:
        See ZKB docs for query params
        https://github.com/zKillboard/zKillboard/wiki/API-(Killmails)

    Args:
        zkb_query (str): params for zkb query
        kill_counts (int): number of kills to fetch
        zkb_uri (str, optional): root URI for zkb API fetches
        kills_per_request (int, optional): help figure out pagination
        dump_path (str, optional): Path to read/write cache from

    Returns:
        (:obj:`list`): list of killmail objects

    """
    pages = math.ceil(kill_counts/kills_per_request)
    print('--checking cache')
    cache_file = path.join(dump_path, ZKB_CACHE_FILE)
    if path.isfile(cache_file):
        with open(cache_file, 'r') as zkb_fh:
            cache = json.load(zkb_fh)
        if cache['query'] == zkb_query and cache['count'] == kill_counts:
            print('--returning cached response')
            return cache['data']

    kills_list = []
    for page in cli.terminal.Progress(range(1, pages+1)):
        req = requests.get(
            '{zkb_uri}{zkb_query}page/{page}/'.format(
                zkb_uri=zkb_uri,
                zkb_query=zkb_query,
                page=page
            )
        )
        req.raise_for_status()
        data = req.json()

        kills_list.extend(data)

    print('--caching results')
    zkb_cache = {
        'query': zkb_query,
        'count': kill_counts,
        'data': kills_list
    }
    with open(cache_file, 'w') as zkb_fh:
        json.dump(zkb_cache, zkb_fh)

    return kills_list

def pivot_dict_pandas(
        raw_data,
        dict_keys=DICT_KEYS,
        ignore_keys=LIST_KEYS
):
    """pivot data -- dicts

    Note:
        Uses pandas-only approach

    Args:
        raw_data (:obj:`list`): raw zkb data to prase into frame
        dict_keys (:obj:`list`, optional): keys to pivot
        ignore_keys (:obj:`list`, optional): keys to drop

    Returns:
        (:obj:`pandas.DataFrame`): result data

    """
    print('--Parsing with Pandas')
    raw_df = pd.DataFrame(raw_data)

    print('--Dropping ignore_keys')
    raw_df = raw_df.drop(ignore_keys, 1)

    print('--Pivoting dict_keys')
    for key in dict_keys:
        temp_df = pd.DataFrame(list(raw_df[key]))
        raw_df = pd.concat([raw_df, temp_df], axis=1)

    print('--Dropping dict_keys')
    raw_df = raw_df.drop(dict_keys, 1)

    return raw_df

def pivot_dict_native(
        raw_data,
        dict_keys=DICT_KEYS,
        ignore_keys=LIST_KEYS
):
    """pivot data -- dicts

    Note:
        Native unspin

    Args:
        raw_data (:obj:`list`): raw zkb data to prase into frame
        dict_keys (:obj:`list`, optional): keys to pivot
        ignore_keys (:obj:`list`, optional): keys to drop

    Returns:
        (:obj:`pandas.DataFrame`): result data

    """
    print('--transforming raw_data')
    raw_result = []
    for row in cli.terminal.Progress(list(raw_data)):  #work from copy
        for key in dict_keys:
            row = {**row, **row[key]}   #push dict up to row
            row.pop(key)                #delete raw dict from element
        for key in ignore_keys:
            row.pop(key)                #delete raw list from element
        raw_result.append(row)

    print('--pushing data into Pandas')
    return pd.DataFrame(raw_result)

def pivot_list_pandas_stack(
        raw_data,
        pivot_column,
        index_column,
        data_columns=DATA_KEYS
):
    """pivot list element with Pandas

    Notes:
        pandas method (not pure pandas)
        can only pivot 1 column (think melt/unmelt)

    Args:
        raw_data (:obj:`list`): data to transform
        pivot_column (str): name of column to pivot
        index_column (str): which column to use for final index
        data_columns (:obj:`list`, optional): data keys to keep along with pivoted data

    Returns:
        (:obj:`pandas.DataFrame`): pivoted data

    """
    print('--Preparing data in Pandas -- concat')
    raw_df = pd.DataFrame(raw_data)
    drop_cols = list(set(raw_df.columns.values) - set(data_columns))
    drop_cols.remove(pivot_column)
    raw_df = raw_df.drop(drop_cols, 1)

    result_df = None
    max_index = 0
    for row in cli.terminal.Progress(list(raw_df.itertuples())):
        data = getattr(row, pivot_column)
        index = list(range(max_index, max_index + len(data)))
        max_index = max_index + len(data)
        row_df = pd.DataFrame(
            data,
            index=index
        )   #pivot out data
        row_df[index_column] = getattr(row, index_column)

        result_df = pd.concat([result_df, row_df], axis=0)  #append to the end

    result_df = result_df.join(
        raw_df.drop(pivot_column, 1),
        index_column,
        lsuffix='_').drop(index_column + '_', 1)
    return result_df

def pivot_list_pandas_melt(
        raw_data,
        pivot_column,
        index_column,
        data_columns=DATA_KEYS
):
    """pivot list element with Pandas

    Notes:
        pure pandas method

    Args:
        raw_data (:obj:`list`): data to transform
        pivot_column (str): name of column to pivot
        index_column (str): which column to use for final index
        data_columns (:obj:`list`, optional): data keys to keep along with pivoted data

    Returns:
        (:obj:`pandas.DataFrame`): pivoted data

    """
    print('--Preparing data in Pandas -- melt')
    raw_df = pd.DataFrame(raw_data)

    print('--Pivoting list element -- {}'.format(pivot_column))
    pivot_df = pd.DataFrame(list(raw_df[pivot_column]))             #pivot raw data
    pivot_df = pd.concat([raw_df[index_column], pivot_df], axis=1)  #add index

    print('--Melting frame into uniform shape')
    pivot_df = pd.melt(pivot_df, id_vars=[index_column])#compress data into 1 col
    pivot_df.dropna(axis=0, how='any', inplace=True)    #drop null vals

    print('--Applying Dict-pivot to data values')
    value_df = pd.DataFrame(list(pivot_df['value']))    #dict-pivot
    value_df = pd.concat([pivot_df[index_column], value_df], axis=1) #drop raw data

    print('--Joining data back into source frame')
    result_df = raw_df.join(value_df, index_column, lsuffix='_')    #merge back to source
    result_df = result_df.drop(index_column + '_', 1)   #tidy join column
    return result_df


def pivot_list_native(
        raw_data,
        pivot_column,
        data_columns=DATA_KEYS
):
    """pivot list element with raw python

    Notes:
        Native unspin
        Can only pivot 1 column (think melt/unmelt)

    Args:
        raw_data (:obj:`list`): data to transform
        pivot_column (str): name of column to pivot
        data_columns (:obj:`list`, optional): data keys to keep along with pivoted data

    Returns:
        (:obj:`pandas.DataFrame`): pivoted data

    """
    print('--transforming raw_data')
    raw_result = []
    for row in cli.terminal.Progress(list(raw_data)):
        static_row_data = {}
        for col in data_columns:
            #save static data
            static_row_data[col] = row[col]

        for pivot_row in row[pivot_column]:
            #unwind list into additional rows
            row_data = {**static_row_data, **pivot_row}
            raw_result.append(row_data)

    print('--pushing data into Pandas')
    return pd.DataFrame(raw_result)

class PandasZKBTest(cli.Application):
    """Process zKillboard data into pandas with various transformation techniques"""

    debug = cli.Flag(
        ['d', '--debug'],
        help='Enable debug mode'
    )

    query = 'w-space/losses/'
    @cli.switch(
        ['q', '--query'],
        str,
        help='zkb query -- https://github.com/zKillboard/zKillboard/wiki/API-(Killmails)')
    def override_query(self, zkb_query):
        """override zkb query"""
        self.query = zkb_query

    count = 2000
    @cli.switch(
        ['c', '--count'],
        int,
        help='Number of records to grab')
    def override_count(self, count):
        """override expected kill count"""
        self.count = count

    out_path = path.join(HERE, 'results')
    @cli.switch(
        ['o', '--out'],
        str,
        help='Path to dump csv and JSON results')
    def override_out_path(self, out_path):
        """override dump path"""
        makedirs(out_path, exist_ok=True)
        self.out_path = out_path

    def main(self):
        """project main goes here"""
        if not path.isdir(self.out_path):
            makedirs(self.out_path, exist_ok=True)
        print('Fetching raw data from zKillboard: {} records'.format(self.count))
        with Timer() as fetch_zkb_timer:
            raw_kill_list = fetch_zkb_data(
                self.query,
                self.count,
                dump_path=self.out_path
            )
            print('--Time Elapsed: {}'.format(fetch_zkb_timer))

        #################
        ## Dict Pivots ##
        #################
        print('Pivoting Data -- Dict keys with Pandas')
        with Timer() as pandas_dict_timer:
            pandas_dict_df = pivot_dict_pandas(raw_kill_list)
            print('--Time Elapsed: {}'.format(pandas_dict_timer))
        pandas_dict_df.to_csv(
            path.join(self.out_path, 'pandas_dict_df.csv'),
            index=False
        )

        print('Pivoting Data -- Dict keys with raw python')
        with Timer() as raw_dict_timer:
            raw_dict_df = pivot_dict_native(raw_kill_list)
            print('--Time Elapsed: {}'.format(raw_dict_timer))
        raw_dict_df.to_csv(
            path.join(self.out_path, 'raw_dict_df.csv'),
            index=False
        )

        #################
        ## List Pivots ##
        #################
        if self.count <= 2000 or self.debug:
            print('Pivoting Data -- List keys with Pandas (stack method)')
            print('Items')
            with Timer() as pandas_list_items_timer:
                pandas_list_items_df = pivot_list_pandas_stack(raw_kill_list, 'items', 'killID')
                print('--Time Elapsed: {}'.format(pandas_list_items_timer))
            pandas_list_items_df.to_csv(
                path.join(self.out_path, 'pandas_list_items_df-concat.csv'),
                index=False
            )
            print('Attackers')
            with Timer() as pandas_list_attackers_timer:
                pandas_list_attackers_df = pivot_list_pandas_stack(raw_kill_list, 'attackers', 'killID')
                print('--Time Elapsed: {}'.format(pandas_list_attackers_timer))
            pandas_list_attackers_df.to_csv(
                path.join(self.out_path, 'pandas_list_attackers_df-concat.csv'),
                index=False
            )
        else:
            print('************************************')
            print('**** SKIPPING PANDAS STACK TEST ****')
            print('************************************')

        print('Pivoting Data -- List keys with Pandas (melt method)')
        print('Items')
        with Timer() as pandas_list_items_timer:
            pandas_list_items_df = pivot_list_pandas_melt(raw_kill_list, 'items', 'killID')
            print('--Time Elapsed: {}'.format(pandas_list_items_timer))
        pandas_list_items_df.to_csv(
            path.join(self.out_path, 'pandas_list_items_df-melt.csv'),
            index=False
        )
        print('Attackers')
        with Timer() as pandas_list_attackers_timer:
            pandas_list_attackers_df = pivot_list_pandas_melt(raw_kill_list, 'attackers', 'killID')
            print('--Time Elapsed: {}'.format(pandas_list_attackers_timer))
        pandas_list_attackers_df.to_csv(
            path.join(self.out_path, 'pandas_list_attackers_df-melt.csv'),
            index=False
        )

        print('Pivoting Data -- List keys with raw python')
        print('Items')
        with Timer() as raw_list_items_timer:
            raw_list_items_df = pivot_list_native(raw_kill_list, 'items')
            print('--Time Elapsed: {}'.format(raw_list_items_timer))
        raw_list_items_df.to_csv(
            path.join(self.out_path, 'raw_list_items_df.csv'),
            index=False
        )
        print('Attackers')
        with Timer() as raw_list_attackers_timer:
            raw_list_attackers_df = pivot_list_native(raw_kill_list, 'attackers')
            print('--Time Elapsed: {}'.format(raw_list_attackers_timer))
        raw_list_attackers_df.to_csv(
            path.join(self.out_path, 'raw_list_attackers_df.csv'),
            index=False
        )

        print('Processing complete -- Have a nice day!')

if __name__ == '__main__':
    PandasZKBTest.run()
