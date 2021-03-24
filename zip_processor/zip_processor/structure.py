import os.path
import json
import boto3
import tarfile
import zipfile

from botocore.client import Config

from base_processor import BaseProcessor


class ZipCustomEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for zip file info entries.
    """
    def default(self, obj):
        if isinstance(obj, TreeNode):
            return obj.as_dict()
        else:
            try:
                return json.JSONEncoder.default(self, obj)
            except json.JSONDecodeError:
                return "<#Invalid#>"


class TreeNode(object):
    """
    TreeNode used to construct a directory tree listing of files in the
    zip file.
    """
    def __init__(self, name, path, archive_entry, flattened=False):
        """
        Parameters
        ----------
        name : str
            TreeNode name
        path : List[str]
            The path of the TreeNode in the tree
        archive_entry : zipfile.ZipInfo
            The zip file info entry object
        flattened : bool
            If true, the TreeNode will be presented in a "flattened" form
        """
        self.name = name
        self.path = path
        self.archive_entry = archive_entry
        self._children = []
        self.flattened = flattened

    @property
    def path_key(self):
        return '/'.join(self.path)

    @property
    def parent_path_key(self):
        if len(self.path) <= 1:
            return '/'
        else:
            return '/'.join(self.path[:-1])

    @property
    def children(self):
        return self._children

    def add_child(self, child):
        self._children.append(child)
        return self

    def __len__(self):
        return len(self._children)

    def __repr__(self):
        return self.path_key

    def as_dict(self):
        """
        Return the TreeNode as a dict of the form

            {
              "name": "<NAME>",
              "path": ["path1", "path2", ..., "pathN"],
              "path_key": "path1/path2/.../pathN",
              "metadata: [
                {
                  "key": "size",
                  "value": "1024"
                }
              ]
            }
        """
        d = dict(name=self.name, path=self.path, path_key=self.path_key)
        if not self.flattened:
            d['children'] = self.children
        d['metadata'] = []
        if self.archive_entry:
            d['metadata'].append(dict(key="size",
                                      value=self.archive_entry.size()))
        return d


class ArchiveEntry(object):
    def file_name(self):
        raise NotImplementedError

    def size(self):
        raise NotImplementedError

    def is_dir(self):
        return False

    def get_path_components(self):
        return [component for component in self.file_name().split('/')
                if len(component) != 0]


class ZipEntry(ArchiveEntry):
    def __init__(self, entry):
        super(ZipEntry, self).__init__()
        self._entry = entry

    def file_name(self):
        return self._entry.filename

    def size(self):
        return self._entry.file_size


class TarballEntry(ArchiveEntry):
    def __init__(self, entry):
        super(TarballEntry, self).__init__()
        self._entry = entry

    def file_name(self):
        return self._entry.name

    def is_dir(self):
        return self._entry.isdir()

    def size(self):
        return self._entry.size


def read_archive(file_name):
    """
    Parameters
    ----------
    file_name : str
        The name of the archive to open.

    Returns
    -------
    List[ArchiveEntry]
    """
    try:
        zip_file = zipfile.ZipFile(file_name, 'r')
        return map(ZipEntry, zip_file.infolist())
    except Exception as e:
        tarball_file = tarfile.open(file_name, 'r')
        return map(TarballEntry, tarball_file.getmembers())


def extract(file_name, flatten=False):
    """
    Given a zip filename, extract the structure of the zip file, returning
    the structure as a tree or flattened list.

    Parameters
    ----------
    file_name : str
        The zip file to inspect
    flatten : bool
        If True, the returned struct will be a list of TreeNodes, otherwise a
        list of TreeNode instances without children will be returned.

    Returns
    -------
    TreeNode|List[TreeNode]
    """
    entries = read_archive(file_name)
    linearized_nodes = []
    path_to_node = {}

    if flatten:
        for entry in entries:
            components = entry.get_path_components()
            component = components[-1]
            linearized_nodes.append(TreeNode(name=component,
                                             path=components,
                                             archive_entry=entry,
                                             flattened=flatten))
        return linearized_nodes

    root = TreeNode(name="/", path="/", archive_entry=None)
    for entry in entries:
        components = entry.get_path_components()
        prev_node = root
        for i in range(1, len(components) + 1):
            path_prefix = components[:i]
            component = components[-1]
            path_prefix_key = '/'.join(path_prefix)
            if path_prefix_key not in path_to_node:
                path_to_node[path_prefix_key] = \
                        TreeNode(name=component,
                                 path=components,
                                 archive_entry=entry,
                                 flattened=flatten)
                node = path_to_node[path_prefix_key]
                prev_node.add_child(node)
            else:
                node = path_to_node[path_prefix_key]
            prev_node = node
    return root.children


def extract_as_json(file_name, flatten=False):
    """
    Extract the structure of the zip file as JSON.

    Parameters
    ----------
    file_name : str
        The zip file to inspect
    flatten : bool
        If True, the returned struct will be a list of TreeNodes, otherwise a
        list of TreeNode instances without children will be returned.

    Returns
    -------
    str
    """
    return json.dumps(extract(file_name, flatten=flatten),
                      cls=ZipCustomEncoder)


class ZipStructureProcessor(BaseProcessor):
    required_inputs = ["file"]

    def __init__(self, *args, **kwargs):
        super(ZipStructureProcessor, self).__init__(*args, **kwargs)
        self.session = boto3.session.Session()
        self.s3_client = \
            self.session.client('s3',
                                config=Config(signature_version='s3v4'),
                                endpoint_url=self.settings.s3_endpoint)
        self.file = self.inputs.get('file')

        # structure JSON file:
        self.payload_upload_key = None
        self.payload_output_path = None

        # asset JSON file:
        self.asset_upload_key = None
        self.asset_output_path = None

    def get_file_size(self, key):
        self.LOGGER.info('Getting file size of {key}'.format(key=key))
        response = self.s3_client.head_object(
            Bucket=self.settings.storage_bucket, Key=key
        )
        file_size = response['ContentLength']
        self.LOGGER.info('{key}: size in bytes: {size}'.format(key=key,
                                                               size=file_size))
        return file_size

    def task(self):
        # write out the structure as JSON:
        output_file_name = "{job}-{name}.json".format(
            job=self.settings.aws_batch_job_id,
            name=os.path.basename(self.file))

        # build the upload key for the structure JSON file:
        self.payload_upload_key = os.path.join(self.settings.storage_directory,
                                               output_file_name)

        # write the local structure JSON file out:
        local_payload_dest = os.path.join(self.settings.scratch_dir,
                                          output_file_name)

        self.LOGGER.info('writing out local payload = {dest}'
                         .format(dest=local_payload_dest))

        with open(local_payload_dest, 'w') as f:
            self.LOGGER.info("Writing out {local_payload_dest}"
                             .format(local_payload_dest=local_payload_dest))
            f.write(extract_as_json(self.file, flatten=True))
            self.payload_output_path = local_payload_dest

        # upload the structure JSON file:
        self.LOGGER.info('upload payload = {key}'
                         .format(key=self.payload_upload_key))
        self._upload(self.payload_output_path, self.payload_upload_key)

        # get the file size of the structure JSON file:
        file_size = self.get_file_size(self.payload_upload_key)

        # build and write out the asset file:
        asset_info = {
            'bucket': self.settings.storage_bucket,
            'key': self.payload_upload_key,
            'type': 'view',
            'size': file_size
        }

        self.asset_output_path = "asset_info.json"
        self.publish_outputs("asset_info", asset_info)

        # upload the asset file:
        self.LOGGER.info('upload asset = {key}'
                         .format(key=self.asset_output_path))
        self._upload(local_payload_dest, self.asset_output_path)
