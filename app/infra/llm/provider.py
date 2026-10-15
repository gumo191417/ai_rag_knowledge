from app.infra.config.providers import infra_config
from app.shared.model.embedding_utils import generate_embeddings
from app.shared.model.lm_utils import get_llm_client

class LLMProvider:
    def chat(self,model:str|None = None,json_model:bool = False):
        return get_llm_client(model=model,json_mode=json_model)

    def vision_chat(self,model:str | None = None):
        if not model:
            model = infra_config.llm_config.lv_model
        return get_llm_client(model=model,json_mode=False)

llm_provider = LLMProvider()