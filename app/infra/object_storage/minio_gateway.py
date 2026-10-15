from minio import Minio

from app.infra.config.providers import infra_config
from app.shared.clients import get_minio_client, minio_utils


class MinioGateway:


    """获取 MinIO 桶名"""
    @property
    def bucket_name(self) -> str:
        return infra_config.minio_config.bucket_name


    """获取MinIO存储图片的目录路径"""
    @property
    def image_dir(self)->str:
        return infra_config.minio_config.minio_img_dir


    """获取客户端的实例"""
    @property
    def client(self)->Minio:
        return minio_utils.get_minio_client()

    """构建访问地址"""
    def build_image_url(self,stem:str,image_name:str)->str:
        is_https_or_http = "https" if infra_config.minio_config.minio_secure else "http"
        return (f"{is_https_or_http}://{infra_config.minio_config.endpoint}/{self.bucket_name}{self.image_dir}/{stem}/{image_name}")

minio_gateway = MinioGateway()