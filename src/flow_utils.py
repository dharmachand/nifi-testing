#!/usr/bin/python3

#  Copyright (c).
#  All rights reserved.
#  This file is part of Nifi Flow Unit Testing Framework,
#  and is released under the "Apache license 2.0 Agreement". Please see the LICENSE file
#  that should have been included as part of this package.

# This flow utils script has all the helper / util functions specific to Nifi Flow

import json
from random import randrange

from jsonpath_ng import parse
from nipyapi import canvas, versioning, nifi

PROCESSORS_CONFIG_JSON = '../config/processors.json'


# Create & Enable StandardHttpContextMap Controller Service to provide context that is shared by
# HandleHttpRequest & HandleHttpResponse processors
def create_enable_ctx_map_controller(parent_pg):
    context_map_name = 'org.apache.nifi.http.StandardHttpContextMap'
    context_map_service_type = canvas.get_controller_type(context_map_name)
    ctx_map = canvas.create_controller(parent_pg, context_map_service_type, 'testing map')
    canvas.schedule_controller(ctx_map, True, True)
    return ctx_map


# Creates or Updates processor with spec defined in PROCESSORS_CONFIG_JSON
def create_processor(parent_pg, p_name, p_type, p_location, p_config):
    processor = canvas.get_processor(p_name, 'name', False)
    processor_type = canvas.get_processor_type(p_type, 'name', False)

    if not processor:
        processor = canvas.create_processor(parent_pg, processor_type, p_location, p_name, p_config)
    else:
        #UpdateAttribute cached the old attributes which needs to be recreated to reset.
        if processor_type.type == 'org.apache.nifi.processors.attributes.UpdateAttribute':
            canvas.delete_processor(processor, True, True)
            processor = canvas.create_processor(parent_pg, processor_type, p_location, p_name, p_config)
        else:
            processor = canvas.update_processor(processor, nifi.ProcessorConfigDTO(properties=p_config.get('properties')))

    return processor


# Creates or Updates processors defined in PROCESSORS_CONFIG_JSON
# variables passed to the function are needed for eval() used for create_processor()
def create_processors(test_api_port, ctx_map, in_attribs, in_content_txt, exp_out_content_txt, report_json,  # NOSONAR
                      parent_pg, skip, test_context):

    if len(exp_out_content_txt) > 0:
        in_attribs['test.expected'] = exp_out_content_txt

    # Parse processors config json file
    with open(PROCESSORS_CONFIG_JSON, 'r') as processors_json:
        processors_json_data = json.load(processors_json)

    dict_processors = {}
    for processor in processors_json_data:
        p_name = parse('$.name').find(processor)[0].value
        p_type = parse('$.type').find(processor)[0].value
        p_location = parse('$.location').find(processor)[0].value
        p_config = parse('$.config').find(processor)[0].value

        if p_name not in skip:
            # eval does the variable substitutions in json strings with function parameter values
            proc = create_processor(parent_pg, p_name, p_type, eval(p_location), eval(p_config))
            dict_processors[p_name] = proc

    return dict_processors


# Creates input port that connects test processors to deployed target test process group
def create_run_input_port(process_group, flow_name):
    input_port_list = canvas.list_all_input_ports(process_group.id)
    if len(input_port_list) == 0:
        canvas.create_port(process_group.id, 'INPUT_PORT', 'input-port-to-' + flow_name,
                           'RUNNING', (randrange(0, 4000), randrange(0, 4000)))
        input_port_list = canvas.list_all_input_ports(process_group.id)
    in_port = input_port_list.pop()
    return in_port


# Creates output port that connects deployed target test process group to test processors
def create_run_output_port(process_group, flow_name):
    output_port_list = canvas.list_all_output_ports(process_group.id)
    if len(output_port_list) == 0:
        canvas.create_port(process_group.id, 'OUTPUT_PORT', 'output-port-from-' + flow_name,
                           'RUNNING', (randrange(0, 4000), randrange(0, 4000)))
        output_port_list = canvas.list_all_output_ports(process_group.id)
    out_port = output_port_list.pop()
    return out_port


# Generates Nifi expression that asserts expected output and actual attributes on flow file
def generate_attrib_assert_nifi_expression(expected_out_attribs_json):
    global all_attribs_match_expr, flow_file_attributes
    if len(expected_out_attribs_json) > 0:
        all_attribs_match_expr = '${'
        flow_file_attributes = {}
        cur = 0
        for key in expected_out_attribs_json:
            cur = cur + 1
            value = expected_out_attribs_json[key]
            flow_file_attributes[key] = "${" + key + "}"
            if cur <= 1:
                all_attribs_match_expr += key + ":equals('"
                all_attribs_match_expr += value + "')"
            else:
                all_attribs_match_expr += ":and(${"
                all_attribs_match_expr += key + ":equals('"
                all_attribs_match_expr += value + "')"
                all_attribs_match_expr += "})"
        all_attribs_match_expr += "}"
    report = {'flow_attributes_match': all_attribs_match_expr, 'flow_file_attributes': flow_file_attributes,
              'flow_content_match': "${test.expected:isEmpty():ifElse('match',${RouteOnAttribute.Route})}"}
    return report


# Adds Registry Client if not exists
def add_registry_client(registry_base_url):
    registry_list = versioning.list_registry_clients().registries
    if len(registry_list) == 0:
        versioning.create_registry_client('NifiRegistry', registry_base_url, 'Nifi Registry')
        registry_list = versioning.list_registry_clients().registries
    return registry_list.pop()


# This recursive function gets controller services referred by others
def get_referred_controller_services(cs_dto, ref_cs_list):
    for rec_cs in cs_dto:
        if rec_cs.component.reference_type != "ControllerService":
            return
        if rec_cs.component.name in ref_cs_list:
            ref_cs_list.remove(rec_cs.component.name)
            ref_cs_list.append(rec_cs.component.name)
        else:
            ref_cs_list.append(rec_cs.component.name)
        if hasattr(rec_cs, 'referencing_components') and len(rec_cs.referencing_components) > 0:
            get_referred_controller_services(rec_cs.component, ref_cs_list)


# Gets controller services referencing other components
def get_cs_referencing_components(controller_services, ref_component_list):
    for controller_service in controller_services:
        if controller_service.component.name not in ref_component_list:
            ref_component_list.append(controller_service.component.name)
        if len(controller_service.component.referencing_components) > 0:
            get_referred_controller_services(controller_service.component.referencing_components, ref_component_list)


# Enables Controller Services
def enable_controller_services(ref_component_list):
    for ref_comp in ref_component_list:
        cs_entity = canvas.get_controller(ref_comp, 'name', True)
        if isinstance(cs_entity, list):
            for inner_ref_comp in cs_entity:
                print("Enabling controller service:", inner_ref_comp.component.name)
                canvas.schedule_controller(inner_ref_comp, True, True)
        else:
            print("Enabling controller service:", ref_comp)
            canvas.schedule_controller(cs_entity, True, True)


# Disables Controller Services
def disable_controller_services(ref_component_list):
    for ref_comp in ref_component_list:
        del_cs_entity = canvas.get_controller(ref_comp, 'name', True)
        if isinstance(del_cs_entity, list):
            for inner_ref_comp in del_cs_entity:
                print("Disabling controller service:", inner_ref_comp.component.name)
                canvas.schedule_controller(inner_ref_comp, False, True)
        else:
            print("Disabling controller service:", ref_comp)
            canvas.schedule_controller(del_cs_entity, False, True)


def update_sensitive_properties(pg_id, update_data):
    if not update_data:
        return

    sens_procs = canvas.list_sensitive_processors(pg_id)
    if not sens_procs:
        return

    for sens_proc in sens_procs:
        for obj in update_data:
            if obj['processor_name'] and obj['processor_name'] == sens_proc.component.name or obj['processor_type'] \
                    and obj['processor_type'] == sens_proc.component.type:
                #print(str(obj['properties']))
                proc_props=sens_proc.component.config.properties
                proc_props.update(obj['properties'])
                update = nifi.ProcessorConfigDTO(properties=proc_props)
                canvas.update_processor(sens_proc, update, False)

