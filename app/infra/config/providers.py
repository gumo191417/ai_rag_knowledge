"""
配置聚合模块，负责将旧配置对象统一收口到新的基础设施出口。
"""

from app.shared.config.embedding_config import embedding_config,EmbeddingConfig
from app.shared.config.lm_config import lm_config,LLMConfig
from app.shared.config.bailian_mcp_config import mcp_config,McpConfig
from app.shared.config.milvus_config import milvus_config,MilvusConfig
from app.shared.config.mineru_config import mineru_config,MinerUConfig
from app.shared.config.minio_config import minio_config,MinIOConfig
from app.shared.config.reranker_config import reranker_config,RerankerConfig
from app.shared.config.settings_config import settings,AppSettings


from dataclasses import dataclass,field

@dataclass
class InfraConfig:
    embedding_config:EmbeddingConfig =field(default_factory=lambda : embedding_config)
    llm_config: LLMConfig = field(default_factory=lambda: lm_config)
    mcp_config: McpConfig = field(default_factory=lambda: mcp_config)
    milvus_config: MilvusConfig = field(default_factory=milvus_config)
    mineru_config: MinerUConfig = field(default_factory=mineru_config)
    minio_config: MinIOConfig = field(default_factory=minio_config)
    reranker_config: RerankerConfig = field(default_factory=reranker_config)
    settings: AppSettings = field(default_factory=settings)


infra_config = InfraConfig()