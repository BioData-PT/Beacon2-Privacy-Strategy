import json
import asyncio
import copy
import logging
import math
from typing import Dict, List, Tuple

import numpy as np
from aiohttp import web
from aiohttp.web_request import Request
from bson import json_util
from beacon import conf
from beacon.db import client
from pymongo import ReturnDocument
import yaml
import math

from beacon.request import ontologies
from beacon.request.model import AlphanumericFilter, Granularity, RequestParams
from beacon.response.build_response import (
    build_beacon_resultset_response,
    build_beacon_collection_response,
    build_beacon_boolean_response,
    build_beacon_count_response,
    build_filtering_terms_response,
    build_beacon_resultset_response_by_dataset,
    build_generic_response
)
from beacon.utils.stream import json_stream
from beacon.db.datasets import get_datasets, get_public_datasets
from beacon.utils.auth import get_accessible_datasets, resolve_token

LOG = logging.getLogger(__name__)


def collection_handler(db_fn, request=None):
    async def wrapper(request: Request):
        LOG.info("-- Collection handler --")
        # Get params
        json_body = await request.json() if request.method == "POST" and request.has_body and request.can_read_body else {}
        qparams = RequestParams(**json_body).from_request(request)
        LOG.debug(f"Query Params = {qparams}")
        entry_id = request.match_info["id"] if "id" in request.match_info else None
        
        # backup qparams before db_fn modifies it
        qparams_backup = copy.deepcopy(qparams)
        
        # find permissions for user
        
        
        # add qparam to filter datasets by permissions
        
        # Get response
        entity_schema, count, records = db_fn(entry_id, qparams)
        response_converted = (
            [r for r in records] if records else []
        )
        
        # restore qparams
        qparams = qparams_backup
        
        response = build_beacon_collection_response(
            response_converted, count, qparams, lambda x, y: x, entity_schema
        )
        return await json_stream(request, response)

    return wrapper

# support functions for the budget strategy

# update the budget of a specific individual for a user in the budget collection
def update_individual_budget(user_id, individual_id, amount):
    try:
        budget_collection = client.beacon['budget']
        #LOG.debug(f"Updating budget for individual_id={individual_id} by amount={amount}")

        # Find the document and update it, returning the updated document
        updated_document = budget_collection.find_one_and_update(
            {"individualId": individual_id, "userId": user_id},
            {"$inc": {"budget": -amount}},
            return_document=ReturnDocument.AFTER  # Return the updated document
        )

        return updated_document

    except Exception as e:
        LOG.error(f"Error updating budget: {str(e)}")
        return None

def pvalue_strategy(access_token, records, qparams):
    helper = []
    total_cases = 0
    removed_individuals = []
    removed = False

    for record in records:
        individual_ids = set()
        individuals_to_remove = set()

        # step 4: compute the risk for that query: ri = -log(1 - Di)
        allele_frequency = record.get('alleleFrequency')
        N = client.beacon.get_collection('individuals').count_documents({})  # total number of individuals !! if user requestes dataset, N = individuals in that dataset
        Di = (1 - allele_frequency) ** (2 * N)
        ri = -(math.log10(1 - Di))
        LOG.debug(f"O CUSTO DESTA QUERY É ESTE = {ri}")

        # fetch individualId from the biosample collection
        case_level_data = record.get('caseLevelData', [])
        for case in case_level_data:
            individual_id = case.get('biosampleId')  # biosampleId = individualId
            individual_ids.add(individual_id)

        for individualId in individual_ids:
            
            search_criteria = {
                "userId": access_token,
                "individualId": individualId
            }

            # Step 2: check if query has been asked before
            response_history = client.beacon['history'].find_one({"userId": access_token, "query": qparams.summary()})
            if response_history is not None:
                LOG.debug(f"Query was previously done by the same user")
                return response_history["response"], helper, total_cases, removed, removed_individuals  # Return stored answer if query was asked before by the same user

            # Step 3: check if there are records with bj > ri
            budget_info = client.beacon['budget'].find_one(search_criteria)
            if not budget_info:
                p_value = 0.5 # upper bound on test errors
                bj = -(math.log10(p_value))  # initial budget
                budget_info = {
                    "userId": access_token,
                    "individualId": individualId,
                    "budget": bj
                }
                client.beacon['budget'].insert_one(budget_info)

            # re-fetch the budget_info to ensure we have the latest data
            budget_info = client.beacon['budget'].find_one(search_criteria)

            if budget_info and budget_info['budget'] < ri:
                
                individuals_to_remove.add(individualId)
            else:
                if budget_info['budget'] >= ri:
                    # Step 7: reduce their budgets by ri
                    update_individual_budget(access_token, individualId, ri)
                    budget_info = client.beacon['budget'].find_one(search_criteria)

        if individuals_to_remove:
            # filter the individuals from the record
            removed = True
            removed_individuals = individuals_to_remove
            LOG.debug(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            LOG.debug(f"Removed individuals: {list(individuals_to_remove)}") # signal to know which individuals have no more budget
            LOG.debug(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            record['caseLevelData'] = [case for case in record['caseLevelData'] if case.get('biosampleId') not in individuals_to_remove]
            if  record['caseLevelData'] != []:
                helper.append(record)
        else:
            helper.append(record)
        
        total_cases += len(record['caseLevelData'])        

    return None, helper, total_cases, removed, removed_individuals



# handler with authentication & REMS
# mostly from BioData.pt
def generic_handler(db_fn, request=None):

    async def wrapper(request: Request):
        LOG.info("-- Generic handler --")

        # Get params
        entry_id = request.match_info.get('id', None)
        json_body = await request.json() if request.method == "POST" and request.has_body and request.can_read_body else {}
        qparams: RequestParams = RequestParams(**json_body).from_request(request)

        LOG.debug(f"Query Params = {qparams}")

        LOG.debug(f"Headers = {request.headers}")

        access_token_header = request.headers.get('Authorization')
        access_token_cookies = request.cookies.get("Authorization")
        LOG.debug(f"Access token header = {access_token_header}")
        LOG.debug(f"Access token cookies = {access_token_cookies}")

        registered = False
        public = False

        # set access_token as the one we receive in the header
        # if not in header, get the one from cookies
        if access_token_header:
            access_token = access_token_header
        else:
            access_token = access_token_cookies

        # get specified datasets
        requested_datasets = qparams.query.request_parameters.get("datasets", None)
        LOG.debug(f"requested_datasets = {requested_datasets}")

        # Start async task to request datasets from permissions server
        task_permissions = asyncio.create_task(get_accessible_datasets(access_token, requested_datasets))

        # if no datasets were specified, use all in DB
        if requested_datasets is None:
            # get list of all datasets in DB
            _, _, all_dataset_docs = get_datasets(None, RequestParams())
            all_dataset_ids = [doc["id"] for doc in all_dataset_docs]
            target_datasets = all_dataset_ids
        # else, query only the ones specified
        else:
            target_datasets = requested_datasets

        # TODO query all datasets in parallel
        tasks_dataset_queries = []
        # { dataset_id:(count, records) }
        datasets_query_results:Dict[str, Tuple[int,List[dict]]] = {}

        db_fn_submodule = str(db_fn.__module__).split(".")[-1]
        LOG.debug(f"db_fn submodule = {db_fn_submodule}")

        # get response of permissions server
        accessible_datasets: List[str] = []  # array of dataset ids
        accessible_datasets, public, registered = await task_permissions

        # TODO do this asynchronously
        for dataset_id in target_datasets:
            qparams_dataset = copy.deepcopy(qparams)
            LOG.debug("")
            LOG.debug(f"=========================")
            LOG.debug(f"dataset_id = {dataset_id}")
            LOG.debug(f"=========================")
            # change field for genomicVariations
            if db_fn_submodule == "g_variants":
                filter_dataset_id = {
                    "id": "_info.datasetId",
                    "value": dataset_id
                }
            else:
                filter_dataset_id = {
                    "id": "datasetId",
                    "value": dataset_id
                }

            qparams_dataset.query.filters.append(filter_dataset_id)
            LOG.debug(f"Dataset Qparams = {qparams_dataset}")
            entity_schema, count, records = db_fn(entry_id, qparams_dataset)

            ######################## P-VALUE ########################

            # apply the p-value strategy if user is authenticated but not registered and only if submodule is genomic variations
            LOG.debug(f"PUBLIC = {public}")
            LOG.debug(f"REGISTERED = {registered}")
            if not public and not registered and db_fn_submodule == "g_variants":
                history, records, total_cases, removed, removed_individuals = pvalue_strategy(access_token, records, qparams)
                dataset_result = (len(list(records)), list(records))
                LOG.debug(f"DATASET RESULTS = {dataset_result}")
                datasets_query_results[dataset_id] = (dataset_result)
                
                if history is not None:
                    LOG.debug(f"Query was stored in the database")
                    LOG.debug(history)
                    return await json_stream(request, history)

        LOG.debug(f"schema = {entity_schema}")

        # get the max authorized granularity
        requested_granularity = qparams.query.requested_granularity
        max_granularity = Granularity(conf.max_beacon_granularity)
        response_granularity = Granularity.get_lower(requested_granularity, max_granularity)

        # build response
        response, store = build_generic_response(
            results_by_dataset=datasets_query_results,
            accessible_datasets=accessible_datasets,
            granularity=response_granularity,
            qparams=qparams,
            entity_schema=entity_schema,
            registered=registered,
            public=public
        )
        LOG.debug(f"STOREEEE = {store}")
        

        document = {
            "userId": access_token,
            "query": qparams.summary(),
            "response": response
        }

        if store:
            client.beacon['history'].insert_one(document)
        
        LOG.debug(f"response = {response}")

        return await json_stream(request, response)

    return wrapper

    
    
    
# handler with authentication
# mostly from CRG

def generic_handler_crg(db_fn, request=None):
    
    async def wrapper(request: Request):
        LOG.info("-- Generic handler --")
        # Get params
        json_body = await request.json() if request.method == "POST" and request.has_body and request.can_read_body else {}
        qparams:RequestParams = RequestParams(**json_body).from_request(request)

        LOG.debug(f"Query Params = {qparams}")
        
        search_datasets = []
        authenticated=False
        
        access_token_header = request.headers.get('Authorization')
        access_token_cookies = request.cookies.get("Authorization")
        LOG.debug(f"Access token header = {access_token_header}")
        LOG.debug(f"Access token cookies = {access_token_cookies}")
        
        # set access_token as the one we recieve in the header
        # if not in header, get the one from cookies
        if access_token_header:
            access_token = access_token_header
        else:
            access_token = access_token_cookies
        
        if access_token is not None:
            with open("/beacon/beacon/request/public_datasets.yml", 'r') as stream:
                public_datasets = yaml.safe_load(stream)
            list_of_public_datasets= public_datasets['public_datasets']
            try:
                specific_datasets = qparams.query.request_parameters['datasets']
            except Exception:
                specific_datasets = []
            access_token = access_token[7:]  # cut out 7 characters: len('Bearer ')
            
            authorized_datasets, authenticated = await resolve_token(access_token, search_datasets)
            LOG.debug(authorized_datasets)
            #LOG.debug('all datasets:  %s', all_datasets)
            LOG.info('resolved datasets:  %s', authorized_datasets)
            LOG.debug(authenticated)
            LOG.debug(specific_datasets)


            specific_datasets_unauthorized = []
            specific_datasets_unauthorized_and_found = []
            bio_list = []
            search_and_authorized_datasets = []
            specific_search_datasets = []
            for public_dataset in list_of_public_datasets:
                authorized_datasets.append(public_dataset)
            # Get response
            if specific_datasets != []:
                for element in authorized_datasets:
                    if element in specific_datasets:
                        search_and_authorized_datasets.append(element)
                for elemento in specific_datasets:
                    if elemento not in search_and_authorized_datasets:
                        specific_datasets_unauthorized.append(elemento)
                qparams.query.request_parameters = {}
                qparams.query.request_parameters['datasets'] = '*******'
                _, _, datasets = get_datasets(None, qparams)
                beacon_datasets = [ r for r in datasets ]
                all_datasets = [r['id'] for r in beacon_datasets]
                
                response_datasets = [ r['id'] for r in beacon_datasets if r['id'] in search_and_authorized_datasets]
                LOG.debug(specific_search_datasets)
                LOG.debug(response_datasets)

                list_of_dataset_dicts=[]

                for data_r in response_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_r
                    dict_dataset['ids']=[ r['ids'] for r in beacon_datasets if r['id'] == data_r ]
                    list_of_dataset_dicts.append(dict_dataset)

                for dataset_searched in specific_datasets_unauthorized:
                    if dataset_searched not in all_datasets:
                        dict_dataset = {}
                        dict_dataset['dataset']=dataset_searched
                        dict_dataset['ids'] = ['Dataset not found']
                        LOG.debug(dict_dataset['dataset'])
                        list_of_dataset_dicts.append(dict_dataset)
                
                for data_s in specific_datasets_unauthorized_and_found:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_s
                    dict_dataset['ids'] = ['Unauthorized dataset']
                    list_of_dataset_dicts.append(dict_dataset)

                LOG.debug(specific_datasets_unauthorized_and_found)
                LOG.debug(specific_datasets_unauthorized)
                LOG.debug(f"list of datasets = {[e['dataset'] for e in list_of_dataset_dicts]}")

            # if specific_datasets = []
            else:
                qparams.query.request_parameters = {}
                qparams.query.request_parameters['datasets'] = '*******'
                _, _, datasets = get_datasets(None, qparams)
                beacon_datasets = [ r for r in datasets ]
                specific_datasets = [ r['id'] for r in beacon_datasets if r['id'] not in authorized_datasets]
                response_datasets = [ r['id'] for r in beacon_datasets if r['id'] in authorized_datasets]
                LOG.debug(specific_datasets)
                LOG.debug(response_datasets)
                specific_datasets_unauthorized.append(specific_datasets)
                for unauth in specific_datasets_unauthorized:
                    for unauth_spec in unauth:
                        biosample_ids = [ r['ids'] for r in beacon_datasets if r['id'] == unauth_spec ]
                        bio_list.append(biosample_ids)
                
                list_of_dataset_dicts=[]

                for data_r in response_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_r
                    dict_dataset['ids']=[ r['ids'] for r in beacon_datasets if r['id'] == data_r ]
                    list_of_dataset_dicts.append(dict_dataset)
                
                for data_s in specific_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_s
                    dict_dataset['ids'] = ['Unauthorized dataset']
                    list_of_dataset_dicts.append(dict_dataset)
                LOG.debug(f"list of datasets = {[e['dataset'] for e in list_of_dataset_dicts]}")
            
            # -- end of if Authorized acess --
        
        else:
            #write here code for public datasets
            list_of_dataset_dicts=[]
            qparams.query.request_parameters = {}
            qparams.query.request_parameters['datasets'] = '*******'
            _, _, datasets = get_datasets(None, qparams)
            beacon_datasets = [ r for r in datasets ]
            with open("/beacon/beacon/request/public_datasets.yml", 'r') as stream:
                public_datasets = yaml.safe_load(stream)
            list_of_public_datasets= public_datasets['public_datasets']
            LOG.debug(f"Pub datasets = {list_of_public_datasets}")
            for data_r in list_of_public_datasets:
                dict_dataset = {}
                dict_dataset['dataset']=data_r
                dict_dataset['ids']=[ r['ids'] for r in beacon_datasets if r['id'] == data_r ]
                list_of_dataset_dicts.append(dict_dataset)
            LOG.debug(f"list of datasets = {[e['dataset'] for e in list_of_dataset_dicts]}")

            

        qparams = RequestParams(**json_body).from_request(request)
        

        entry_id = request.match_info.get('id', None)
        entity_schema, count, records = db_fn(entry_id, qparams)
        LOG.debug(f"schema = {entity_schema}")
        
        recordsList = list(records[0:100])
        recordsDebug = recordsList[0:10]
        LOG.debug(f"records = {recordsDebug}")
        
        # if it had at least one record
        if recordsDebug:
            LOG.debug(f"first record = {recordsDebug[0:1]}")
        else:
            LOG.debug(f"no records found")

        response_converted = records
        
        if qparams.query.requested_granularity == Granularity.BOOLEAN:
            response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
        
        elif qparams.query.requested_granularity == Granularity.COUNT:
            if conf.max_beacon_granularity == Granularity.BOOLEAN:
                response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            else:
                response = build_beacon_count_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
        
        # if requested_granularity == Granularity.RECORD:
        else:

            if conf.max_beacon_granularity == Granularity.BOOLEAN:
                response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            elif conf.max_beacon_granularity == Granularity.COUNT:
                response = build_beacon_count_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            else:
                response = build_beacon_resultset_response_by_dataset(response_converted, list_of_dataset_dicts, count, qparams, lambda x, y: x, entity_schema)
                
        return await json_stream(request, response)

    return wrapper




def filtering_terms_handler(db_fn, request=None):
    async def wrapper(request: Request):
        # Get params
        json_body = await request.json() if request.method == "POST" and request.has_body and request.can_read_body else {}
        qparams = RequestParams(**json_body).from_request(request)
        entry_id = request.match_info.get('id', None)

        # Get response
        #_, _, records = db_fn(entry_id, qparams)
        #resources = ontologies.get_resources()
        #response = build_filtering_terms_response(records, resources, qparams)
        entity_schema, count, records = db_fn(entry_id, qparams)
        response = build_filtering_terms_response(records, count, qparams, lambda x, y: x, entity_schema)
        return await json_stream(request, response)

    return wrapper


# I don't know why this function was changed to look like this
# So I replaced it with an older version of it, the one above this
def filtering_terms_handler_auth(db_fn, request=None):
    async def wrapper(request: Request):
        # Get params
        json_body = await request.json() if request.method == "POST" and request.has_body and request.can_read_body else {}
        qparams = RequestParams(**json_body).from_request(request)

        LOG.debug(qparams)
        
        search_datasets = []
        authenticated=False

        if access_token is not None:
            try:
                specific_datasets = qparams.query.request_parameters['datasets']
            except Exception:
                specific_datasets = []
            access_token = access_token[7:]  # cut out 7 characters: len('Bearer ')
            
            authorized_datasets, authenticated = await resolve_token(access_token, search_datasets)
            LOG.debug(authorized_datasets)
            #LOG.debug('all datasets:  %s', all_datasets)
            LOG.info('resolved datasets:  %s', authorized_datasets)
            LOG.debug(authenticated)
            LOG.debug(specific_datasets)

            specific_datasets_unauthorized = []
            specific_datasets_unauthorized_and_found = []
            bio_list = []
            search_and_authorized_datasets = []
            specific_search_datasets = []
            # Get response
            if specific_datasets != []:
                for element in authorized_datasets:
                    if element in specific_datasets:
                        search_and_authorized_datasets.append(element)
                for elemento in specific_datasets:
                    if elemento not in search_and_authorized_datasets:
                        specific_datasets_unauthorized.append(elemento)
                qparams.query.request_parameters = {}
                qparams.query.request_parameters['datasets'] = '*******'
                _, _, datasets = get_datasets(None, qparams)
                beacon_datasets = [ r for r in datasets ]
                all_datasets = [r['id'] for r in beacon_datasets]
                
                response_datasets = [ r['id'] for r in beacon_datasets if r['id'] in search_and_authorized_datasets]
                LOG.debug(specific_search_datasets)
                LOG.debug(response_datasets)

                list_of_dataset_dicts=[]

                for data_r in response_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_r
                    dict_dataset['ids']=[ r['ids'] for r in beacon_datasets if r['id'] == data_r ]
                    list_of_dataset_dicts.append(dict_dataset)

                for dataset_searched in specific_datasets_unauthorized:
                    if dataset_searched not in all_datasets:
                        dict_dataset = {}
                        dict_dataset['dataset']=dataset_searched
                        dict_dataset['ids'] = ['Dataset not found']
                        LOG.debug(dict_dataset['dataset'])
                        LOG.debug(dict_dataset['ids'])
                        list_of_dataset_dicts.append(dict_dataset)
                
                for data_s in specific_datasets_unauthorized_and_found:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_s
                    dict_dataset['ids'] = ['Unauthorized dataset']
                    list_of_dataset_dicts.append(dict_dataset)

                LOG.debug(specific_datasets_unauthorized_and_found)
                LOG.debug(specific_datasets_unauthorized)

            else:
                qparams.query.request_parameters = {}
                qparams.query.request_parameters['datasets'] = '*******'
                _, _, datasets = get_datasets(None, qparams)
                beacon_datasets = [ r for r in datasets ]
                specific_datasets = [ r['id'] for r in beacon_datasets if r['id'] not in authorized_datasets]
                response_datasets = [ r['id'] for r in beacon_datasets if r['id'] in authorized_datasets]
                LOG.debug(specific_datasets)
                LOG.debug(response_datasets)
                specific_datasets_unauthorized.append(specific_datasets)
                for unauth in specific_datasets_unauthorized:
                    for unauth_spec in unauth:
                        biosample_ids = [ r['ids'] for r in beacon_datasets if r['id'] == unauth_spec ]
                        bio_list.append(biosample_ids)
                
                list_of_dataset_dicts=[]

                for data_r in response_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_r
                    dict_dataset['ids']=[ r['ids'] for r in beacon_datasets if r['id'] == data_r ]
                    list_of_dataset_dicts.append(dict_dataset)
                
                for data_s in specific_datasets:
                    dict_dataset = {}
                    dict_dataset['dataset']=data_s
                    dict_dataset['ids'] = ['Unauthorized dataset']
                    list_of_dataset_dicts.append(dict_dataset)
                LOG.debug(list_of_dataset_dicts)
        else:
            list_of_dataset_dicts=[]

        qparams = RequestParams(**json_body).from_request(request)
        

        entry_id = request.match_info.get('id', None)
        entity_schema, count, records = db_fn(entry_id, qparams)

        response_converted = records
        
        if qparams.query.requested_granularity == Granularity.BOOLEAN:
            response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
        
        elif qparams.query.requested_granularity == Granularity.COUNT:
            if conf.max_beacon_granularity == Granularity.BOOLEAN:
                response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            else:
                response = build_beacon_count_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
        
        # qparams.query.requested_granularity == Granularity.RECORD:
        else:

            if conf.max_beacon_granularity == Granularity.BOOLEAN:
                response = build_beacon_boolean_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            elif conf.max_beacon_granularity == Granularity.COUNT:
                response = build_beacon_count_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
            else:
                response = build_filtering_terms_response(response_converted, count, qparams, lambda x, y: x, entity_schema)
                
        return await json_stream(request, response)

    return wrapper

