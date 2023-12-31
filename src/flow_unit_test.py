#!/usr/bin/python3

#  Copyright (c).
#  All rights reserved.
#  This file is part of Nifi Flow Unit Testing Framework,
#  and is released under the "Apache license 2.0 Agreement". Please see the LICENSE file
#  that should have been included as part of this package.

# This is the main script that runs flow unit tests as per test cases defined in test-data directory.
# Each flow unit test has 3 phases -
# Setup Phase:
#   Get target test process group flow from registry
#   Create & Start StandardHttpContextMap controller service that is needed to run below processors
#   Define HandleHttpRequest and HandleHttpResponse processors
#   Deploy target test process group flow
#   Start controller services recursively for the Process Group
#   Get input and output ports
# Test Phase:
#   Get input data & expected output attributes and data and generate nifi expression for assertions
#   Create / Update processors with above data and attributes and recreate connections
#   Run API Tests against test endpoint exposed by HandleHttpResponse processor and do assertions
# Teardown Phase:
#   Disable all controller services recursively enabled for target test process group that is deployed
#   Disable controller services enabled for HandleHttpRequest and HandleHttpResponse processors
#   Stop target test process group and HandleHttpRequest & HandleHttpResponse processors
#   Delete test process group and HandleHttpRequest & HandleHttpResponse processors
#   Delete all controller services enabled for test process group
#   Delete parameter context

import json
import os
import time
from pathlib import Path
from random import randrange

import dateutil.relativedelta
import requests
from jsonpath_ng import parse
from config import Config as Env
from jproperties import Properties
import itertools
from utils import git_clone, read_file_content, file_name_with_path, FileContentType, TestContext, extract_flow_name, \
    run_subprocess, csv_to_list
from flow_utils import create_enable_ctx_map_controller, create_processors, create_run_input_port, \
    create_run_output_port, generate_attrib_assert_nifi_expression, add_registry_client, \
    get_cs_referencing_components, disable_controller_services, enable_controller_services, update_sensitive_properties
from nipyapi import config, security, versioning, canvas, templates, nifi, parameters

TEST_PROPERTIES = '../config/test.properties'
TEST_CASE_PREFIX = 'tc'
TEST_CASE_FILE_EXTENSION = '.json'
HTTPS = 'https://'
HTTP = 'http://'
NIFI = 'nifi'
REGISTRY = 'registry'
SECS = 'secs'
PASSED = 'PASSED'
FAILED = 'FAILED'
TEST_PG = 'Routing'
MAIN_FLOW = 'integration-platform'


# --------------------------------- Functions --------------------------------- #
# Configure Nifi, Nifi Registry and test data
def configure():
    global config, test_bucket_name, test_data_dir, input_attribs_jsonpath, expected_out_attribs_jsonpath, \
        input_file_name_jsonpath, expected_out_file_name_jsonpath, skip_test_dirs, skip_tests, nifi_test_api, \
        test_api_port, registry_base_url, repo_base_dir, flow_version_dictionary, sensitive_props, include_only

    # Read env vars from env loaded by AppConfig
    config.nifi_config.host = HTTPS + Env.NIFI_HOSTNAME + ':' + str(Env.NIFI_PORT) + '/nifi-api'
    config.nifi_config.verify_ssl = Env.VERIFY_SSL
    config.nifi_config.cert_file = Env.NIFI_CERT_FILE
    config.nifi_config.key_file = Env.NIFI_KEY_FILE
    config.registry_config.cert_file = Env.NIFI_CERT_FILE
    config.registry_config.key_file = Env.NIFI_KEY_FILE
    config.nifi_config.username = Env.NIFI_USERNAME
    config.nifi_config.password = Env.NIFI_PASSWORD
    registry_base_url = HTTPS + Env.NIFI_REGISTRY_HOSTNAME + ':' + str(Env.NIFI_REGISTRY_PORT)
    config.registry_config.host = registry_base_url + '/nifi-registry-api'

    # Read flow unit test properties from a properties file
    props = Properties()
    with open(TEST_PROPERTIES, 'rb') as prop_file:
        props.load(prop_file)
    test_bucket_name = props.get("test_bucket_name").data
    repo_base_dir = props.get("repo_base_dir").data
    test_data_dir = props.get("test_data_dir").data
    input_attribs_jsonpath = props.get("input_attribs_jsonpath").data
    expected_out_attribs_jsonpath = props.get("expected_output_attribs_jsonpath").data
    input_file_name_jsonpath = props.get("input_file_name_jsonpath").data
    expected_out_file_name_jsonpath = props.get("expected_output_file_name_jsonpath").data
    skip_test_dirs = csv_to_list(props.get("skip_test_dirs").data)
    skip_tests = csv_to_list(props.get("skip_tests").data)
    test_api_port = props.get('nifi_test_api_port').data
    nifi_test_api = HTTP + NIFI + ':' + test_api_port + '/test'
    flow_version_mapping = props.get('flow_version_mapping').data
    flow_version_dictionary = json.loads(flow_version_mapping)
    include_only = csv_to_list(props.get("include_only").data)

    # Import input and expected output data from an external repo if needed
    git_url_tuple = props.get("external_repo_git_url")
    if git_url_tuple is not None:
        git_url = git_url_tuple.data
        git_clone(git_url, repo_base_dir)

    # Set ssl context and do service login for Nifi
    security.set_service_ssl_context(NIFI, config.nifi_config.cert_file, config.nifi_config.key_file)
    is_login_success = security.service_login(NIFI, config.nifi_config.username, config.nifi_config.password, True)
    print('is_login_success: ', is_login_success)

    # Set ssl context and do service login for Nifi Registry
    security.set_service_ssl_context(REGISTRY, config.registry_config.cert_file, config.registry_config.key_file)

    with open("../config/sensitive_props.json", 'r') as json_file:
        sensitive_props = json.load(json_file)


def setup_flow(flow_name):
    global test_cases, teardown_duration, total_duration, parent_pg, parent_pg_id, context_map, deployed_pg, \
        ref_comp_list, input_port, output_port, setup_duration

    print('===== SetUp Phase:', flow_name, "======")
    print(' ')

    # Declare Unit Test Case Stats
    test_cases = {}
    teardown_duration = 0
    total_duration = 0
    setup_start_time = time.time()

    # Get target test flow from test bucket to be deployed for testing
    flow_id = versioning.get_flow_in_bucket(bucket_id, flow_name, 'name', False).identifier

    # Create Unit Test Container PG
    flow_unit_test_pg = flow_name + '-test-pg'
    print('Creating Unit Test Container process group:', flow_unit_test_pg, '...')
    flow_unit_test_version = flow_version_dictionary.get(flow_name)
    print('Achieving flow:', flow_name, " with version:", flow_unit_test_version)

    if not flow_unit_test_version:
        raise Exception("Unable to find flow ", flow_name, " with version:", flow_unit_test_version)

    location = (randrange(0, 4000), randrange(0, 4000))
    parent_pg = canvas.create_process_group(root_pg, flow_unit_test_pg, location)
    parent_pg_id = parent_pg.id

    # Create and Enable Context Map controller service
    # print('Creating and Enabling StandardHttpContextMap controller service...')
    context_map = create_enable_ctx_map_controller(parent_pg)

    # Get PG from registry and Deploy in Nifi
    print('Getting target unit test process group from Registry and Deploying...')
    deployed_pg = versioning.deploy_flow_version(
        parent_pg_id, (500, 1000), bucket_id, flow_id, registry_id, flow_unit_test_version)

    # In case of integration platform, as main flow can't be deployed because of multiple dependencies - Kafka
    # Kerberos, STS etc. we are extracting the child flow(Routing), deploying and running test cases
    # TODO: Figure out how to start Kafka related controller services and components
    # TODO: Import latest flow into Nifi unit test framework
    if flow_name == MAIN_FLOW:
        try:
            routing_pg = canvas.get_process_group(TEST_PG, "name", False)
            if not routing_pg:
                raise Exception("Unable to find process group:", TEST_PG)
            template = templates.create_template(routing_pg.id, "routing", "routing template")
            template_id = template.template.id
            templates.deploy_template(parent_pg_id, template_id, 500, 1000)
            templates.delete_template(template_id)
            canvas.delete_process_group(deployed_pg, True, True)
            deployed_pg = routing_pg
        except Exception as e:
            print("Error errors when searching underneath process group:", e)

    # Get all controller services within Parent PG
    controller_service_list = canvas.list_all_controllers(parent_pg_id, True)

    # Get referencing components i.e. controller services referred by other cs
    ref_comp_list = []
    get_cs_referencing_components(controller_service_list, ref_comp_list)

    # Enable all controller services in specific order of reference
    print('Enabling all controller services of target test process group in specific order of reference...')
    enable_controller_services(ref_comp_list)

    # Get the input ports in the deployed flow
    print('Creating & Running input port...')
    input_port = create_run_input_port(deployed_pg, flow_name)

    # Get the output ports in the deployed flow
    print('Creating & Running output port...')
    output_port = create_run_output_port(deployed_pg, flow_name)

    print('Updating sensitive properties...')
    update_sensitive_properties(deployed_pg.id, sensitive_props)

    setup_duration = round(time.time() - setup_start_time, 2)
    # End Flow Setup


def teardown_flow(flow_name):
    global teardown_duration
    teardown_start_time = time.time()

    # TODO: Review cleanup / teardown as many test cases use same flow and improve performance

    print(' ')
    print('===== TearDown Phase:', flow_name, "======")

    # Disable all controller services
    print('Disabling all controller services in specific order of reference...')
    disable_controller_services(ref_comp_list[::-1])

    # Delete Parent PG
    print('Deleting Test Container process group...')
    pg_entity = nifi.apis.process_groups_api.ProcessGroupsApi().get_process_group(id=parent_pg_id)
    canvas.delete_process_group(pg_entity, True, True)

    # Delete Parameter Context
    print('Deleting parameter context...')
    parameter_context_list = parameters.list_all_parameter_contexts()
    for parameter_context in parameter_context_list:
        parameters.delete_parameter_context(parameter_context, True)

    teardown_duration = round(time.time() - teardown_start_time, 2)
    # End TearDown


def setup_test_case(tc_dir, test_context):
    print('=== SetUp Test Case ===')

    # Reading input file content
    input_content_text = ''
    input_file_name = parse(input_file_name_jsonpath).find(test_context.json_data)[0].value
    if input_file_name != '' and not test_context.is_binary_file:
        input_content_text = read_file_content(file_name_with_path(tc_dir, input_file_name))

    processors_to_skip = []
    if input_file_name == '' or test_context.is_skip_replace_text_in:
        processors_to_skip.append('replace_text_in_processor')

    # Reading output file content
    expected_out_content_text = ''
    exp_out_file_name = parse(expected_out_file_name_jsonpath).find(test_context.json_data)[0].value
    if exp_out_file_name != '':
        expected_out_content_text = read_file_content(file_name_with_path(tc_dir, exp_out_file_name))

    # Reading input and output attributes json
    input_attribs = parse(input_attribs_jsonpath)
    expected_output_attribs = parse(expected_out_attribs_jsonpath)

    # Generating Nifi expression to compare expected and actual output attributes
    expected_out_attribs_json = expected_output_attribs.find(test_context.json_data)[0].value
    report = generate_attrib_assert_nifi_expression(expected_out_attribs_json)

    # TODO: Review if components need to be deleted instead of stopping and updating to avoid stale data from previous
    #  tests breaking subsequent tests

    # Create all the processors required for flow unit testing
    print('Creating / Updating all the processors required for flow unit testing...')
    dict_processors = create_processors(test_api_port, context_map, input_attribs.find(test_context.json_data)[0].value,
                                        input_content_text, expected_out_content_text, report, parent_pg,
                                        processors_to_skip, test_context)

    connection_list = ['http_req_processor', 'in_mapper_processor', 'replace_text_in_processor', 'input_port',
                       'output_port', 'extract_content_processor', 'check_expected_equals_content_processor', 'replace_text_out_processor',
                       'http_resp_processor']
    all_processors_dict = {**dict_processors, **{'input_port': eval('input_port'), 'output_port': eval('output_port')}}
    connection_list = [value for value in connection_list if value in all_processors_dict.keys()]

    # Wire up processors
    print('Creating connections between flow unit test processors...')
    for from_con, to_con in itertools.pairwise(connection_list):
        if from_con != 'input_port':
            canvas.create_connection(all_processors_dict[from_con], all_processors_dict[to_con])

    # Schedule processors
    print('Starting all the processors...')
    for processor in dict_processors.values():
        #print ("scheduling "+ processor.component.name)
        canvas.schedule_processor(processor, True, True)

    # Schedule deployed process group
    print('Starting the target unit test process group...')
    canvas.schedule_process_group(deployed_pg.id, True)

    return dict_processors.values()


def teardown_test_case(processor_list):
    # Stop all processors
    print('Stopping all processors...')
    for processor in processor_list:
        canvas.schedule_processor(processor, False, True)
    # Stop target unit test process group
    print('Stopping target unit test process group...')
    canvas.schedule_process_group(deployed_pg.id, False)
    # Delete all connections
    print('Deleting connections between flow unit test processors...')
    for processor in processor_list:
        component_connections = canvas.get_component_connections(processor)
        for connection in component_connections:
            canvas.delete_connection(connection)


# Runs for each test case defined in test data. Basically it -
# sets input & expected output files to flow file, compares expected flow file with actual output file
# generates nifi expression that asserts input & expected output flow file attributes
def run_test_case(tc_dir, tc_file):
    global test_suite_result
    start_time = time.time()
    # Strip off TEST_CASE_FILE_EXTENSION from the test case file name
    tc_name = tc_file[0:-len(TEST_CASE_FILE_EXTENSION)]

    print(' ')
    print('===== BEGIN :: Test Case:', tc_name, "======")
    # Parse test case json file
    with open(file_name_with_path(tc_dir, tc_file), 'r') as json_file:
        json_data = json.load(json_file)

    try:
        # Setup Test Case
        test_context = TestContext(json_data)
        processor_list = setup_test_case(tc_dir, test_context)
        run_subprocess(test_context.subprocess.before_command)

        # Wait for everything to be started and stable
        time.sleep(3)

        # Test against the defined endpoint - verify flow output
        print(' ')
        print('Running Test Case:', tc_name)

        input_file_name = parse(input_file_name_jsonpath).find(json_data)[0].value
        if input_file_name != '' and test_context.is_binary_file:
            input_file_content = read_file_content(file_name_with_path(tc_dir, input_file_name), FileContentType.BINARY)
            resp = requests.post(url=nifi_test_api, files={'filename': input_file_content})
        else:
            resp = requests.get(nifi_test_api)

        resp_json = json.loads(resp.text)
        flow_attributes_match = resp_json['flow_attributes_match']
        flow_content_match = 'match' if test_context.is_skip_check_out_content else resp_json['flow_content_match']
        if flow_attributes_match == 'true' and flow_content_match == 'match':
            print('Test Case:', tc_name, PASSED)
            test_result = PASSED
        else:
            print('Test Case:', tc_name, FAILED)
            print('Entire Response:' + json.dumps(resp.text))
            test_result = FAILED
            test_suite_result = 'FAILURE'
        run_subprocess(test_context.subprocess.after_command)
    except Exception as err:
        print('Test Case:', tc_name, FAILED)
        print('failed with exception: ', err)
        test_result = FAILED
        test_suite_result = 'FAILURE'

    print(' ')
    print('=== TearDown Test Case ===')
    # TearDown Test Case
    teardown_test_case(processor_list)

    test_cases[tc_name] = [test_result, round(time.time() - start_time, 2)]
    print('===== END :: Test Case:', tc_name, "======")


def generate_flow_unit_test_report(flow_name):
    global total_duration

    # TODO: Improve Unit Test report
    print(' ')
    print('===== BEGIN :: Unit Test Report:', flow_name, "======")

    sd = dateutil.relativedelta.relativedelta(seconds=int(setup_duration))
    print("Flow Setup: %d hours, %d minutes and %d seconds" % (sd.hours, sd.minutes, sd.seconds))

    total_duration += setup_duration

    print(' ')

    failed_tests = []
    for test_name, stats in test_cases.items():
        total_duration += stats[1]
        if stats[0] == FAILED:
            failed_tests.append(test_name)
        print(test_name, stats[0], 'took', stats[1], SECS)

    print(' ')
    td = dateutil.relativedelta.relativedelta(seconds=int(teardown_duration))
    print("Flow TearDown: %d hours, %d minutes and %d seconds" % (td.hours, td.minutes, td.seconds))

    total_duration += teardown_duration
    total_tc_count = len(test_cases)
    failed_tc_count = len(failed_tests)

    print(' ')
    print('Tests', FAILED, ':', failed_tc_count, failed_tests)
    print('Tests', PASSED, ':', total_tc_count - failed_tc_count)
    print('Total Tests:', total_tc_count)
    ttd = dateutil.relativedelta.relativedelta(seconds=int(total_duration))
    print("Total Time: %d hours, %d minutes and %d seconds" % (ttd.hours, ttd.minutes, ttd.seconds))
    print('===== END :: Unit Test Report:', flow_name, "======")


# --------------------------------- Main ------------------------------------ #
# Configure Nifi, Nifi Registry and test data
configure()

print('========== BEGIN ================')
print(' ')

# Initialize overall test suite result
test_suite_result = 'SUCCESS'

# Adding Registry Client if not exists
print('Adding Registry Client if not exists...')
registry_id = add_registry_client(registry_base_url).id

# Get target test bucket
bucket_id = versioning.get_registry_bucket(test_bucket_name, 'name', False).identifier

# Get the root process group id for future tasks
root_id = canvas.get_root_pg_id()

# Get Root PG object
root_pg = canvas.get_process_group(root_id, 'id')

# Run all flow unit tests
#  step / flow dir name in the test-data dir should match with flow name imported in registry
#  eg: validate, http, routing, etc.,
#  test case json files, input and output files begin with step name and tc number
#  eg: validate_tc1_false_exit.json, validate_tc1_input.txt, validate_tc1_output.txt
test_data_base_dir = repo_base_dir + test_data_dir
test_dir = Path(os.path.abspath(test_data_base_dir))
allFiles = [x for x in test_dir.rglob('*' + TEST_CASE_FILE_EXTENSION) if x.is_file()]

testsByFlow = {}

for afile in allFiles:
    dn = Path(os.path.relpath(afile.parent, os.path.abspath(test_dir))).as_posix()
    if (len(include_only) == 0 and dn not in skip_test_dirs and afile.name not in skip_tests and afile.name.find('_' + TEST_CASE_PREFIX) > 0)\
            or (len(include_only) != 0 and (dn in include_only or afile.name in include_only) and afile.name.find('_' + TEST_CASE_PREFIX) > 0):
        flow = extract_flow_name(afile, test_data_base_dir)
        if flow not in testsByFlow:
            testsByFlow.update({flow: []})
        testsByFlow[flow].append(afile)

for flow_name in testsByFlow.keys():
    filesToTest = testsByFlow.get(flow_name)

    if len(filesToTest) != 0:
        # Setup
        setup_flow(flow_name)

        try:
            for file in filesToTest:
                tc_dir = Path(os.path.abspath(file.parent)).as_posix()
                run_test_case(tc_dir, file.name)
        except Exception as err:
            print("exception: " + str(err))
        finally:
            # TearDown
            teardown_flow(flow_name)

    # Generate Flow Unit Test Report
    generate_flow_unit_test_report(flow_name)

print(' ')
print('Unit Test Suite Result:', test_suite_result)
print(' ')
print('=========== END ===============')
