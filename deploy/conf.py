"""Beacon Configuration."""

#
# Beacon general info
#
import os
import logging

beacon_id = 'pt.biodata.beacon'  # ID of the Beacon
beacon_name = 'Beaconv2 at Biodata.pt in Portugal'  # Name of the Beacon service
api_version = 'v2.0.0'  # Version of the Beacon implementation
uri = 'https://beacon.biodata.pt/api/'  # URI of the Beacon service

#
# Beacon granularity
#
default_beacon_granularity = "record"
max_beacon_granularity = "record"

#
#  Organization info
#
org_id = 'BioData.pt'  # Id of the organization
org_name = 'BioData.pt'  # Full name
org_description = ('BioData.pt is the Portuguese distributed e-infrastructure for biological data and the Portuguese node of ELIXIR. It supports the national scientific system through best practices in data management and state of the art data analysis.')
org_adress = ('Associação BIP4DAB'
              'Rua da Quinta Grande, 6.'
              '2780-156 Oeiras, Portugal')
org_welcome_url = 'https://biodata.pt'
org_contact_url = 'mailto:info@biodata.pt'
org_logo_url = r'https://biodata.pt/sites/default/files/BioData%20Logo_colour%20corrected_transp%20bg_2.png'
org_info = ''

#
# Project info
#
description = (r"This <a href='https://beacon-project.io/'>Beacon</a> "
               r"is based on the GA4GH Beacon "
               r"<a href='https://github.com/ga4gh-beacon/specification-v2/blob/master/beacon.yaml'>v2.0</a>")
version = 'v2.0'
welcome_url = 'https://beacon.biodata.pt/'
alternative_url = 'https://beacon.biodata.pt/api/'
create_datetime = '2021-11-29T12:00:00.000000'
update_datetime = ''
# update_datetime will be created when initializing the beacon, using the ISO 8601 format

#
# Service
#
service_type = 'org.ga4gh:beacon:1.0.0'  # service type
service_url = 'https://beacon.biodata.pt/api/service-info'
entry_point = False
is_open = True
documentation_url = 'https://github.com/BioData-PT/beacon2-ri-api'  # Documentation of the service
environment = 'development'  # Environment (production, development or testing/staging deployments)

# GA4GH
ga4gh_service_type_group = 'org.ga4gh'
ga4gh_service_type_artifact = 'beacon'
ga4gh_service_type_version = '1.0'

# Beacon handovers
beacon_handovers = [
    {
        'handoverType': {
            'id': 'CUSTOM',
            'label': 'Project description'
        },
        'note': 'Project description',
        'url': 'https://www.nist.gov/programs-projects/genome-bottle'
    }
]

#
# Database connection
#


database_password = os.getenv('DB_PASSWD')

if database_password is None:
    database_password = 'example'
    print("WARNING: YOU SHOULD DEFINE A 'DB_PASSWD' ENV VARIABLE IN 'deploy/.env' LIKE IN THE EXAMPLE TO USE A CUSTOM PASSWORD, CURRENTLY USING THE DEFAULT PASSWORD (INSECURE)!")
    logging.warning("warning: default passwd for DB in use")
else:
    logging.info("Imported db passwd successfully!")
    print("Imported DB_PASSWD successfully!")

database_host = 'mongo'
database_port = 27017
database_user = 'root'

database_name = 'beacon'
database_auth_source = 'admin'
# database_schema = 'public' # comma-separated list of schemas
# database_app_name = 'beacon-appname' # Useful to track connections

#
# Web server configuration
# Note: a Unix Socket path is used when behind a server, not host:port
#
beacon_host = '0.0.0.0'
beacon_port = 5050
beacon_tls_enabled = False
beacon_tls_client = False
beacon_cert = '/etc/ega/server.cert'
beacon_key = '/etc/ega/server.key'
CA_cert = '/etc/ega/CA.cert'

#
# Permissions server configuration
#
permissions_url = 'http://beacon-permissions'

#
# IdP endpoints (OpenID Connect/Oauth2)
#
# or use Elixir AAI (see https://elixir-europe.org/services/compute/aai)
#
idp_client_id = 'beacon'
idp_client_secret = 'b26ca0f9-1137-4bee-b453-ee51eefbe7ba'  # same as in the test IdP
idp_scope = 'profile openid'

idp_authorize = 'http://idp/auth/realms/Beacon/protocol/openid-connect/auth'
idp_access_token = 'http://idp/auth/realms/Beacon/protocol/openid-connect/token'
idp_introspection = 'http://idp/auth/realms/Beacon/protocol/openid-connect/token/introspect'
idp_user_info = 'http://idp/auth/realms/Beacon/protocol/openid-connect/userinfo'
idp_logout = 'http://idp/auth/realms/Beacon/protocol/openid-connect/logout'

idp_redirect_uri = 'http://beacon:5050/login'

#
# UI
#
autocomplete_limit = 16
autocomplete_ellipsis = '...'

#
# Ontologies
#
ontologies_folder = "ontologies"
