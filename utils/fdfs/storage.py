from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client
from dailyfresh import settings


class FDFSStorage(Storage):
    """自定义存储类"""
    def __init__(self, client_conf=None, base_url=None):
        if client_conf is None:
            client_conf = settings.FDFS_CLIENT_CONF
        self.client_conf = client_conf

        if base_url is None:
            base_url = settings.FDFS_URL
        self.base_url = base_url

    def _open(self, name, mode='rw'):
        """打开文件时使用"""
        pass

    def _save(self, name, content):
        """保存文件时使用
        name: 你选择上传文件的名字
        content: 包含你上传文件内容的File对象
        """
        # 这里的路径是相对于根目录而言，如果不是，程序运行会报错
        client = Fdfs_client(self.client_conf)

        # upload_appender_by_buffer()根据文件缓存来存取文件
        res = client.upload_appender_by_buffer(content.read())

        # return dict
        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }

        if res.get('Status') != 'Upload successed.':
            raise Exception('文件上传到fast dfs失败')

        # 要将filename从bytes转换为str
        filename = res.get('Remote file_id').decode()
        return filename

    def exists(self, name):
        """Django存文件时判断文件名是否可用，如果存在文件名，则返回True，不存在，则返回False
        因为名字名是由storage取的，所以这里肯定是文件名不存在的
        """
        return False

    def url(self, name):
        """返回访问文件的url路径"""
        return self.base_url + name
