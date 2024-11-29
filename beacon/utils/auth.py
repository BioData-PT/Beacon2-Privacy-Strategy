import logging
from typing import List, Tuple

import yaml

from aiohttp import ClientSession, web

import asyncio

from beacon.db.datasets import filter_public_datasets
from ..conf import permissions_url

LOG = logging.getLogger(__name__)

async def resolve_token(token, requested_datasets_ids):
    raise KeyError("This function should not be used anymore")
    # If the user is not authenticated (ie no token)
    # we pass (requested_datasets, False) to the database function: it will filter out the datasets list, with the public ones
    if token is None:
        public_datasets = [ d["name"] for d in filter_public_datasets(requested_datasets_ids) ]
        return public_datasets, False
    
    new_requested_datasets_ids=[]
    for dataset in requested_datasets_ids:
        dataset=str(dataset)
        new_requested_datasets_ids.append(dataset)
        requested_datasets_ids=new_requested_datasets_ids

    # Otherwise, we have a token and resolve the datasets with the permissions server
    # The permissions server will:
    # * filter out the datasets list, with the ones the user has access to
    # * return _all_ the datasets the user has access to, in case the datasets list is empty
    async with ClientSession() as session:
        async with session.post(
                'http://beacon-permissions:5051/',
                headers={'Authorization': 'Bearer ' + token,
                         'Accept': 'application/json'},
                json={'datasets': requested_datasets_ids},  # will set the Content-Type to application/json
        ) as resp:
            if resp.status > 200:
                LOG.error('Permissions server error %d', resp.status)
                error = await resp.text()
                LOG.error('Error: %s', error)
                raise web.HTTPUnauthorized(body=error)
            content = await resp.content.read()
            authorized_datasets = content.decode('utf-8')
            authorized_datasets_list = authorized_datasets.split('"')
            auth_datasets = []
            for auth_dataset in authorized_datasets_list:
                if ',' not in auth_dataset:
                    if '[' not in auth_dataset:
                        if ']' not in auth_dataset:
                            auth_datasets.append(auth_dataset)
            LOG.debug(auth_datasets)
            return auth_datasets, True

# async job to request permissions server for
# specifically authorized datasets from user and handle authentication
# returns [accessible_datasets, is_authenticated, is_registered]
async def request_permissions(token) -> Tuple[List[str], bool, bool]:
    
    if token is None:
        LOG.debug("Token is none")
        return [], False, False
    
    LOG.debug("About to ask permissions server...")
    # The permissions server will:
    # * filter out the datasets list, with the ones the user has access to
    # * return _all_ the datasets the user has access to, in case the datasets list is empty
    async with ClientSession() as session:
        async with session.post(
                'http://beacon-permissions:5051/',
                headers={#'Authorization': 'Bearer ' + token,
                         'Authorization': token,
                         'Accept': 'application/json'} # will set the Content-Type to application/json
        ) as resp:
            
            if resp.status > 200:
                LOG.error('Permissions server error %d', resp.status)
                error = await resp.text()
                LOG.error('Error: %s', error)
                return [], False, False
                #raise web.HTTPUnauthorized(body=error)
            
            """
            content = await resp.content.read()
            authorized_datasets = content.decode('utf-8')
            LOG.debug(f"authorized_datasets decoded = {authorized_datasets}")
            authorized_datasets_list = authorized_datasets.split('"')
            auth_datasets = []
            for auth_dataset in authorized_datasets_list:
                if ',' not in auth_dataset:
                    if '[' not in auth_dataset:
                        if ']' not in auth_dataset:
                            auth_datasets.append(auth_dataset)
            """
            
            try:
                content = await resp.json()
                auth_datasets = content["datasets"]
                is_registered = content["is_registered"]
            except Exception as e:
                LOG.error(f"Error while getting results from permission server: {e}")
                return [], False, False
            
            LOG.debug(auth_datasets)
            return auth_datasets, True, is_registered

# returns datasets that are accessible by user
# TODO if requested_datasets is given, filters them by perms
# otherwise returns all accessible
async def get_accessible_datasets(token, requested_datasets=None) -> List[str]:
    
    accessible_datasets:List[str] = []
    
    # Start async task to request datasets from permissions server
    task_permissions = asyncio.create_task(request_permissions(token))
    
    # get public datasets
    public_datasets = []
    with open("/beacon/beacon/request/public_datasets.yml", 'r') as stream:
        public_datasets = yaml.safe_load(stream)['public_datasets']
        LOG.debug(f"pub datasets = {public_datasets}")    
    
    # get registered datasets
    registered_datasets = []
    with open("/beacon/beacon/request/registered_datasets.yml", 'r') as stream:
        registered_datasets = yaml.safe_load(stream)['registered_datasets']
        LOG.debug(f"registered datasets = {registered_datasets}")
        
    # get the result from task
    controlled_datasets, is_authenticated, is_registered = await task_permissions
    
    LOG.info(f"User controlled datasets = {controlled_datasets}")
    # Not authenticated, just give access to public datasets
    if not is_authenticated:
        accessible_datasets = public_datasets
    # authenticated but not researcher status, give access to public and controlled
    elif not is_registered:
        accessible_datasets = public_datasets + controlled_datasets
    # authenticated and registered, give access to everything
    else:
        accessible_datasets += public_datasets + registered_datasets + controlled_datasets
    
    # filter by requested datasets (if applicable)
    if requested_datasets:
        accessible_datasets = list(set(accessible_datasets).intersection(set(requested_datasets)))
    
    # remove duplicates and return result
    return list(set(accessible_datasets)), is_authenticated, is_registered
    
    
