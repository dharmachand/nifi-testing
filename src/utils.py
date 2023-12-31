#!/usr/bin/python3
#  Copyright (c).
#  All rights reserved.
#  This file is part of Nifi Flow Unit Testing Framework,
#  and is released under the "Apache license 2.0 Agreement". Please see the LICENSE file
#  that should have been included as part of this package.

# This utils script has all the convenience helper / util functions

import os
import shutil
import subprocess
import base64
import hvac
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from git import Repo
from jsonpath_ng import parse

WINDOWS_LINE_ENDING = '\r\n'
UNIX_LINE_ENDING = '\n'


class FileContentType(Enum):
    TEXT = "r"
    BINARY = "rb"


# this object keeps data related to a test and its specific settings/context
@dataclass
class TestContext:
    json_data: dict
    is_binary_file: bool = False
    is_skip_replace_text_in: bool = False
    is_skip_check_out_content: bool = False

    def __init__(self, json_data):
        self.json_data = json_data
        if 'settings' in json_data:
            self.is_binary_file = 'binary' == get_value_or_default(json_data,
                                                                   '$.settings.load_file_type', "text").lower()
            self.is_skip_replace_text_in = 'true' == get_value_or_default(json_data,
                                                                          '$.settings.skip_replace_text_in',
                                                                          "false").lower()
            self.is_skip_check_out_content = 'true' == get_value_or_default(json_data,
                                                                            '$.settings.skip_check_out_content',
                                                                            "false").lower()
            self.subprocess = self.Subprocess(get_value_or_default(json_data, '$.settings.subprocess', ''))
        else:
            self.subprocess = self.Subprocess({})

    # create subprocess inner class
    class Subprocess(object):
        before_command: str = ''
        after_command: str = ''

        def __init__(self, json_settings):
            if json_settings:
                self.before_command = get_value_or_default(json_settings, '$.before', '')
                self.after_command = get_value_or_default(json_settings, '$.after', '')


def git_clone(git_url, repo_dir):
    if os.path.exists(repo_dir) and os.path.isdir(repo_dir):
        shutil.rmtree(repo_dir)
    Repo.clone_from(git_url, repo_dir)


def read_file_content(file_name, mode=FileContentType.TEXT):
    # Type checking
    if not isinstance(mode, FileContentType):
        raise TypeError('mode must be an instance of FileContentType Enum')
    open_mode = str(mode.value)

    with open(file_name, mode=open_mode) as f:
        content = f.read()

    if mode == FileContentType.TEXT:
        # Windows ➡ Unix
        content = content.replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
    return content


def get_value_or_default(json_data, path, default):
    parsed = parse(path).find(json_data)
    return parsed[0].value if parsed else default


def file_name_with_path(p_dir, p_file):
    return p_dir + "/" + p_file


def extract_flow_name(file_path, start):
    dif = Path(os.path.relpath(os.path.abspath(file_path), os.path.abspath(start))).as_posix()
    index = dif.find("/")
    if index > 0:
        return dif[:index]
    return dif


def csv_to_list (csv_string):
    return list(filter(None, [x.strip() for x in csv_string.split(',')]))


def run_subprocess(command):
    """Run command  wait for command to complete or
    timeout, then returns the and return a CompletedProcess instance.

    It raises a CalledProcessError if the command returns a return code not zero or if stderr is not empty
    """
    if len(command) > 0:
        completed_process = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        if completed_process.returncode != 0:
            print("run script error: "+completed_process.stderr)


def encrypt_data(vault_url, transit_path, key_name, token, plaintext):
    client = hvac.Client(url=vault_url, token=token)

    encrypt_data_response = client.secrets.transit.encrypt_data(
        name=key_name,
        plaintext=base64.b64encode(plaintext.encode()).decode(),
        mount_point=transit_path,
    )

    ciphertext = encrypt_data_response['data']['ciphertext']
    print('Encrypted ciphertext is: {cipher}'.format(cipher=ciphertext))
    return ciphertext


def decrypt_data(vault_url, transit_path, key_name, token, ciphertext):
    client = hvac.Client(url=vault_url, token=token)

    decrypt_data_response = client.secrets.transit.decrypt_data(
        name=key_name,
        ciphertext=ciphertext,
        mount_point=transit_path,
    )
    plaintext_encoded = decrypt_data_response['data']['plaintext']
    plaintext = base64.b64decode(plaintext_encoded).decode()
    print('Decrypted plaintext is: {text}'.format(text=plaintext))
    return plaintext


# Testing
# vault_host = 'http://localhost:8200'
# token = '00000000-0000-0000-0000-000000000000'
# cipher = encrypt_data(vault_host, '/nifi', 'non-prod', token, 'Password123!')
# decrypt_data(vault_host, '/nifi', 'non-prod', token, cipher)
