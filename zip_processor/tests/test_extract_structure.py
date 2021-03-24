#!/usr/bin/env python

import os.path
import json

from moto import mock_s3
from moto import mock_ssm
from six import string_types
import pytest

from base_processor.tests import init_ssm
from base_processor.tests import setup_processor

from zip_processor import ZipStructureProcessor


test_processor_data = [
    'zip_5MB.zip',
    'BundleLogs-1560885454655.zip',
    'jq-1.6.tar',
    'jq-1.6.tar.gz'
]


@pytest.mark.parametrize("filename", test_processor_data)
def test_extract_structure_as_json(filename):
    inputs = {'file': os.path.join('/test-resources', filename)}

    mock_ssm().start()
    mock_s3().start()

    init_ssm()

    task = ZipStructureProcessor(inputs=inputs)
    setup_processor(task)
    task.run()

    # Verify the payload JSON is written out:
    assert task.payload_output_path and \
        os.path.exists(task.payload_output_path)
    with open(task.payload_output_path, 'r') as f:
        payload = json.load(f)
        assert len(payload) > 0
        entry = payload[0]
        assert 'path' in entry and isinstance(entry['path'], list)
        assert 'path_key' in entry and isinstance(entry['path_key'], string_types)
        assert 'name' in entry and isinstance(entry['name'], string_types)
        assert 'metadata' in entry and isinstance(entry['metadata'], list)

    # Verify the asset JSON is written out:
    assert task.asset_output_path and os.path.exists(task.asset_output_path)
    with open(task.asset_output_path, 'r') as f:
        asset_info = json.load(f)
        print(asset_info)
